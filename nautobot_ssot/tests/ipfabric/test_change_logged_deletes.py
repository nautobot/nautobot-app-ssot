"""Tests for deletes made while change logging is deferred, under a real change context.

Deferred change logging is a no-op without a change context, and only a Job or a web request has
one, so a test that drives a model directly never defers anything. Every delete below ran in the
suite for months that way; under a Job, on Nautobot 3.2, each one ended the run with "... objects
need to have a primary key value before you can access their tags". These run inside
`web_request_context`, so the deferral is the one a Job gets.
"""

from collections import Counter
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import Cable, Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.choices import ObjectChangeActionChoices
from nautobot.extras.context_managers import change_context_state, web_request_context
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import ObjectChange, Role, Status

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import delete_objects
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Cable as CableModel
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import (
    change_logging_not_deferred,
    deferred_change_logging,
)
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache


class _ChangeContextTestCase(TestCase):
    """A Device with two cabled Interfaces, and a user to attribute changes to."""

    def setUp(self):
        super().setUp()
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.user = get_user_model().objects.create_user(username="sync-user")
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="ctx-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="ctx-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="ctx-site1", location_type=location_type, status=self.active)
        manufacturer = Manufacturer.objects.create(name="ctx-vendor")
        self.device = Device.objects.create(
            name="c0xr01",
            status=self.active,
            role=role,
            location=location,
            device_type=DeviceType.objects.create(model="ctx-model", manufacturer=manufacturer),
        )
        self.port = Interface.objects.create(device=self.device, name="ge-0/0/0", status=self.active, type="1000base-t")
        self.unit = Interface.objects.create(
            device=self.device, name="ge-0/0/0.0", status=self.active, type="1000base-t"
        )
        self.far = Interface.objects.create(device=self.device, name="ge-0/0/1", status=self.active, type="1000base-t")
        self.cable = Cable.objects.create(
            termination_a=self.unit, termination_b=self.far, status=Status.objects.get_for_model(Cable).first()
        )

    def cable_deletes_logged(self):
        """Return how many Cable deletions reached the change log."""
        return ObjectChange.objects.filter(
            changed_object_type=ContentType.objects.get_for_model(Cable),
            action=ObjectChangeActionChoices.ACTION_DELETE,
        ).count()


class TestDeletesUnderAJobsChangeContext(_ChangeContextTestCase):
    """Each place the sync deletes, run as a Job runs it."""

    def test_a_tunnel_units_cable_is_removed_while_its_update_is_deferred(self):
        """The manual run that found this: `Interface.update` defers, and the delete sat inside it."""
        adapter = MagicMock()
        adapter.sync_ipfabric_tagged_only = False
        adapter.safe_delete_tally = Counter()
        adapter.safe_delete_mode = False
        model = InterfaceModel(name=self.unit.name, device_name=self.device.name, status="Active")
        model.adapter = adapter

        with web_request_context(user=self.user):
            model.update({"type": InterfaceTypeChoices.TYPE_VIRTUAL, "parent_interface": "ge-0/0/0"})

        self.unit.refresh_from_db()
        self.assertIsNone(self.unit.cable)
        self.assertEqual(InterfaceTypeChoices.TYPE_VIRTUAL, self.unit.type)
        self.assertEqual(1, self.cable_deletes_logged(), "The removal must still reach the change log.")

    def test_a_cable_ip_fabric_stops_reporting_is_deleted(self):
        """`Cable.delete` with Safe Delete Mode off, which defers as every model operation does."""
        adapter = MagicMock()
        adapter.safe_delete_mode = False
        model = CableModel(
            termination_a_device=self.device.name,
            termination_a_name=self.unit.name,
            termination_b_device=self.device.name,
            termination_b_name=self.far.name,
            status="Connected",
            # Recorded by the Nautobot adapter while loading, which is how a delete finds its Cable.
            cable_pk=self.cable.pk,
        )
        model.adapter = adapter

        with web_request_context(user=self.user):
            model.delete()

        self.assertFalse(Cable.objects.filter(pk=self.cable.pk).exists())
        self.assertFalse(adapter.job.logger.error.called)
        self.assertEqual(1, self.cable_deletes_logged())

    def test_the_end_of_run_teardown_deletes_what_was_queued(self):
        """`delete_objects`, which the adapter runs once the sync is otherwise complete."""
        self.cable.delete()
        doomed = Interface.objects.create(device=self.device, name="ge-0/0/9", status=self.active, type="1000base-t")

        with web_request_context(user=self.user):
            delete_objects([(Interface, doomed.pk)], logger=MagicMock())

        self.assertFalse(Interface.objects.filter(pk=doomed.pk).exists())


class TestLoggingADeleteImmediately(_ChangeContextTestCase):
    """The helper the deletes above run under."""

    def test_the_enclosing_scope_keeps_what_it_had_collected(self):
        """Set aside and restored, so a deferred update made before the delete is still logged."""
        with web_request_context(user=self.user):
            with deferred_change_logging():
                self.port.description = "changed before the delete"
                self.port.validated_save()
                pending_before = dict(change_context_state.get().deferred_object_changes)

                with change_logging_not_deferred():
                    self.cable.delete()

                context = change_context_state.get()
                self.assertTrue(context.defer_object_changes, "Deferral must be back on for the rest of the scope.")
                self.assertEqual(pending_before.keys(), context.deferred_object_changes.keys())

        self.assertTrue(
            ObjectChange.objects.filter(
                changed_object_id=self.port.pk, action=ObjectChangeActionChoices.ACTION_UPDATE
            ).exists(),
            "The update collected before the delete must still be written when the scope ends.",
        )

    def test_it_does_nothing_where_nothing_is_deferred(self):
        """Outside a deferring scope, or with no change context at all, there is nothing to undo."""
        with change_logging_not_deferred():
            self.cable.delete()

        self.assertFalse(Cable.objects.exists())
