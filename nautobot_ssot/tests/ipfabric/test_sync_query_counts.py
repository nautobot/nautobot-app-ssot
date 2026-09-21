"""Tests for how much database work syncing one object costs.

An IP Fabric estate of a few thousand Devices carries a hundred thousand Interfaces and about as
many IP Addresses, so anything a single object write repeats is multiplied by that. These tests
count the writes each object costs rather than the total queries, since the totals move with
Nautobot's own validation while the repeated writes are what this integration controls.
"""

import datetime
import re
import unittest.mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from nautobot.apps.change_logging import JobChangeContext, change_logging
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Cable, Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import ObjectChange, Role, Status, Tag
from nautobot.ipam.models import IPAddress, Prefix, get_default_namespace

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import (
    NautobotDiffSync,
    delete_objects,
    delete_objects_one_at_a_time,
)
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import (
    InterfaceAddress as InterfaceAddressModel,
)
from nautobot_ssot.integrations.ipfabric.utilities import cables, nbutils
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache


# The trailing boundary keeps these off tables whose names merely start with the one asked for,
# such as the tagged VLAN join table.
def write_to(table):
    """Match an INSERT or UPDATE against `table`, however the backend quotes identifiers.

    PostgreSQL quotes with `"` and MySQL with a backtick, and this app supports both, so a pattern
    that admits only one of them silently matches nothing on the other and the count comes out zero.
    """
    return re.compile(rf'^(INSERT INTO|UPDATE)\s+[`"]?{table}[`"]?(\s|$)', re.IGNORECASE)


WRITE_TO_INTERFACE = write_to("dcim_interface")
WRITE_TO_IP_ADDRESS = write_to("ipam_ipaddress")
# `dcim_cable` alone: the boundary keeps this off `dcim_cabletermination`, which a Cable also writes.
WRITE_TO_CABLE = write_to("dcim_cable")


class _CostTestCase(TestCase):
    """A tagged Device at a Location, both SSoT Tags, and an adapter to drive them with.

    Every class below needs the same fixture; each adds only what its own subject requires.
    """

    def setUp(self):
        populate_status_choices()
        # Cached ORM objects must not outlive this test's transaction; see test_cables.py.
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active_status = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        interface_ct = ContentType.objects.get_for_model(Interface)
        self.ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced from IPFabric"},
        )
        self.ssot_tag.content_types.add(device_ct, interface_ct)
        self.safe_delete_tag, _ = Tag.objects.get_or_create(
            name="SSoT Safe Delete", defaults={"color": ColorChoices.COLOR_RED, "description": "Safe delete"}
        )
        self.safe_delete_tag.content_types.add(device_ct, interface_ct)
        role = Role.objects.create(name="cost-role")
        role.content_types.add(device_ct)
        self.location_type, _ = LocationType.objects.get_or_create(name="cost-site")
        self.location_type.content_types.add(device_ct)
        self.location = Location.objects.create(
            name="cost-site1", location_type=self.location_type, status=self.active_status
        )
        manufacturer = Manufacturer.objects.create(name="cost-vendor")
        device_type = DeviceType.objects.create(model="cost-model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="cost-device",
            status=self.active_status,
            role=role,
            location=self.location,
            device_type=device_type,
            serial="serial",
        )
        self.device.tags.add(self.ssot_tag)
        self.adapter = self.make_adapter()

    @staticmethod
    def make_adapter(location_filter=None):
        """Return an adapter with a mocked job, which is all these tests need of one."""
        job = unittest.mock.MagicMock()
        job.debug = False
        return NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=location_filter,
        )

    def interfaces(self, count, prefix):
        """Return `count` newly created Interfaces on this test's Device."""
        return [
            Interface.objects.create(
                device=self.device, name=f"{prefix}{index}", status=self.active_status, type="1000base-t"
            )
            for index in range(count)
        ]

    def interface_model(self, name):
        """Return a DiffSync Interface bound to this test's adapter."""
        model = InterfaceModel(name=name, device_name=self.device.name, status="Active")
        model.adapter = self.adapter
        return model

    def create_address(self, interface_name, host, mask_length=24):
        """Run the DiffSync create for one address on an Interface of this test's Device."""
        return InterfaceAddressModel.create(
            self.adapter,
            ids={"device_name": self.device.name, "interface_name": interface_name, "host": host},
            attrs={"mask_length": mask_length, "is_primary": False, "status": "Active"},
        )


class InterfaceWriteCostTestCase(_CostTestCase):
    """Count the writes a single Interface sync makes to the Interface table."""

    def setUp(self):
        super().setUp()
        self.existing = self.interfaces(1, "eth")[0]

    def count_interface_writes(self, operation):
        """Return how many INSERTs and UPDATEs `operation` makes against the Interface table."""
        with CaptureQueriesContext(connection) as queries:
            operation()
        writes = [query["sql"] for query in queries.captured_queries if WRITE_TO_INTERFACE.match(query["sql"].strip())]
        # Only the verb is kept, so a failure reports how many writes happened rather than pages of SQL.
        return [write.split(None, 3)[0].upper() for write in writes]

    def test_creating_an_interface_writes_it_once(self):
        """One INSERT carrying the stamp, and no second save to apply it.

        Each write is a full `validated_save()`, so one more doubles what an Interface costs.
        """
        writes = self.count_interface_writes(
            lambda: InterfaceModel.create(
                self.adapter,
                ids={"name": "eth1", "device_name": self.device.name},
                attrs={"status": "Active", "type": "1000base-t"},
            )
        )
        self.assertEqual(len(writes), 1, f"Expected one write to the Interface table, got {writes}")
        # The address is its own model, so it costs the Interface table nothing.
        self.create_address("eth1", "10.0.0.1")
        self.assertEqual(Interface.objects.get(name="eth1").ip_addresses.count(), 1)

    def test_creating_an_address_does_not_save_it_a_second_time(self):
        """The stamp rides the INSERT, rather than a second save applying it afterwards.

        Each write is a full `validated_save()`, and `IPAddress.save()` calls `clean()` itself, so a
        redundant one is worth about eleven queries on every address a first sync creates.

        Measured as writes following the INSERT, because creating the parent Prefix makes Nautobot
        reparent the addresses it now contains, which writes to the same table beforehand.
        """
        InterfaceModel.create(
            self.adapter,
            ids={"name": "eth2", "device_name": self.device.name},
            attrs={"status": "Active", "type": "1000base-t"},
        )
        with CaptureQueriesContext(connection) as queries:
            self.create_address("eth2", "10.0.0.2")
        writes = [
            query["sql"].split(None, 3)[0].upper()
            for query in queries.captured_queries
            if WRITE_TO_IP_ADDRESS.match(query["sql"].strip())
        ]

        self.assertIn("INSERT", writes, f"Expected the address to be inserted, got {writes}")
        after_insert = writes[writes.index("INSERT") + 1 :]
        self.assertEqual(after_insert, [], f"Expected no further write after the INSERT, got {after_insert}")

        address = IPAddress.objects.get(host="10.0.0.2")
        self.assertEqual(address.cf["system_of_record"], "IPFabric")
        self.assertTrue(address.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_updating_an_interface_writes_it_once(self):
        """Only `update` tags the Interface, so the tag rides the same write."""
        writes = self.count_interface_writes(lambda: self.interface_model("eth0").update({"description": "changed"}))
        self.assertEqual(len(writes), 1, f"Expected one write to the Interface table, got {writes}")
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.description, "changed")

    def test_adding_an_address_never_writes_its_interface(self):
        """The address is its own model, so it costs the Interface table nothing at all."""
        writes = self.count_interface_writes(lambda: self.create_address("eth0", "10.0.0.2"))

        self.assertEqual(writes, [], f"Expected no write to the Interface table, got {writes}")
        self.assertEqual([str(ip.host) for ip in self.existing.ip_addresses.all()], ["10.0.0.2"])

    def test_a_synced_interface_is_still_tagged_and_stamped(self):
        """Removing the duplicate tagging must not leave the Interface untagged."""
        InterfaceModel.create(
            self.adapter,
            ids={"name": "eth2", "device_name": self.device.name},
            attrs={"status": "Active", "type": "1000base-t"},
        )
        created = Interface.objects.get(name="eth2")
        self.assertTrue(created.tags.filter(name="SSoT Synced from IPFabric").exists())
        self.assertEqual(created.cf["system_of_record"], "IPFabric")
        self.assertIsNotNone(created.cf["last_synced_from_sor"])

    def test_the_address_is_tagged_and_stamped(self):
        """`create_ip` still tags the IP Address it makes, which is the tag it is responsible for."""
        InterfaceModel.create(
            self.adapter,
            ids={"name": "eth3", "device_name": self.device.name},
            attrs={"status": "Active", "type": "1000base-t"},
        )
        self.create_address("eth3", "10.0.0.4")

        address = Interface.objects.get(name="eth3").ip_addresses.get()
        self.assertTrue(address.tags.filter(name="SSoT Synced from IPFabric").exists())
        self.assertEqual(address.cf["system_of_record"], "IPFabric")


class DeleteCostTestCase(_CostTestCase):
    """Count the queries deleting a set of objects takes when safe delete mode is off."""

    def delete_query_count(self, nautobot_objects):
        """Return how many queries deleting the given objects takes."""
        with CaptureQueriesContext(connection) as queries:
            delete_objects(nautobot_objects)
        return len(queries.captured_queries)

    def test_query_count_does_not_grow_with_the_number_of_objects(self):
        """Django walks the relations once for a whole batch, so the cost must not scale with it."""
        few = self.delete_query_count(self.interfaces(2, "few"))
        many = self.delete_query_count(self.interfaces(40, "many"))
        self.assertEqual(
            few,
            many,
            f"Deleting 40 Interfaces took {many} queries against {few} for 2, so they are not "
            "being deleted as a batch.",
        )
        self.assertEqual(Interface.objects.filter(device=self.device).count(), 0)

    def test_every_object_in_a_batch_is_deleted(self):
        deleted = self.interfaces(5, "gone")
        delete_objects(deleted)
        self.assertFalse(Interface.objects.filter(pk__in=[interface.pk for interface in deleted]).exists())

    def test_objects_of_different_models_are_each_batched(self):
        """`objects_to_delete` is keyed per model, but a mixed list must not delete the wrong rows."""
        interfaces = self.interfaces(3, "mixed")
        spare_location = Location.objects.create(
            name="delete-cost-spare", location_type=self.location_type, status=self.active_status
        )
        delete_objects([*interfaces, spare_location])
        self.assertFalse(Interface.objects.filter(pk__in=[interface.pk for interface in interfaces]).exists())
        self.assertFalse(Location.objects.filter(pk=spare_location.pk).exists())

    def test_a_protected_object_does_not_stop_the_rest_of_its_batch(self):
        """The Device at a Location protects it, so that Location cannot be deleted with the others."""
        free_location = Location.objects.create(
            name="delete-cost-free", location_type=self.location_type, status=self.active_status
        )
        protected_location = self.device.location

        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
            delete_objects([protected_location, free_location])

        self.assertFalse(Location.objects.filter(pk=free_location.pk).exists())
        self.assertTrue(Location.objects.filter(pk=protected_location.pk).exists())
        self.assertTrue(
            any("protected" in message for message in logs.output),
            f"Expected the protected Location to be reported: {logs.output}",
        )

    def test_safe_delete_mode_deletes_nothing(self):
        """Nothing is queued in safe delete mode, and `sync_complete` must not delete regardless."""
        self.adapter.objects_to_delete["_interface"] = self.interfaces(3, "safe")
        self.adapter.sync_complete(unittest.mock.MagicMock(), unittest.mock.MagicMock())
        self.assertEqual(Interface.objects.filter(device=self.device).count(), 3)
        self.assertEqual(self.adapter.objects_to_delete["_interface"], [])

    def test_sync_complete_deletes_queued_ip_addresses(self):
        """Regression for #1353: the grouping was populated but never drained.

        `safe_delete` derives the grouping from the object's class name, and `sync_complete` used to
        name four of them, so IP Addresses and Cables were reported deleted, dropped from the
        DiffSync store, and left in the database.
        """
        prefix, _ = Prefix.objects.get_or_create(
            prefix="10.60.0.0/24", namespace=get_default_namespace(), status=self.active_status
        )
        address = IPAddress.objects.create(address="10.60.0.5/24", status=self.active_status, parent=prefix)
        self.adapter.objects_to_delete["_ipaddress"] = [address]
        self.adapter.safe_delete_mode = False

        self.adapter.sync_complete(unittest.mock.MagicMock(), unittest.mock.MagicMock())

        self.assertFalse(IPAddress.objects.filter(pk=address.pk).exists())
        self.assertEqual(self.adapter.objects_to_delete["_ipaddress"], [])

    def test_sync_complete_deletes_a_grouping_no_order_names(self):
        """A model added later must not silently accumulate, as `_ipaddress` did."""
        spare = Location.objects.create(
            name="unordered-spare", location_type=self.location_type, status=self.active_status
        )
        # A grouping `DELETE_ORDER` does not name, standing in for a model added later.
        self.adapter.objects_to_delete["_somethingnew"] = [spare]
        self.adapter.safe_delete_mode = False

        self.adapter.sync_complete(unittest.mock.MagicMock(), unittest.mock.MagicMock())

        self.assertFalse(Location.objects.filter(pk=spare.pk).exists())
        self.assertIn("_somethingnew", str(self.adapter.job.logger.warning.call_args))

    def test_objects_to_delete_is_not_shared_between_adapters(self):
        """A run that fails before `sync_complete` must not leave work for the next run in the worker."""
        self.adapter.objects_to_delete["_interface"].append(self.interfaces(1, "leak")[0])
        job = unittest.mock.MagicMock()
        job.debug = False
        other = NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
        )
        self.assertEqual(other.objects_to_delete["_interface"], [])

    def test_an_object_the_database_refuses_does_not_stop_the_rest_of_its_batch(self):
        """The retry a refused batch falls back to is per object, so one refusal must not end it.

        `ProtectedError` subclasses `IntegrityError`, so the protected case above arrives here too.
        This is the plain refusal, which carries no protecting object to name.
        """
        doomed, keeper = self.interfaces(2, "integrity")

        with unittest.mock.patch.object(doomed, "delete", side_effect=IntegrityError("refused")):
            with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
                delete_objects_one_at_a_time([doomed, keeper])

        self.assertTrue(Interface.objects.filter(pk=doomed.pk).exists())
        self.assertFalse(Interface.objects.filter(pk=keeper.pk).exists())
        self.assertIn("IntegrityError", " ".join(logs.output))

    def test_sync_complete_deletes_what_is_queued_when_safe_delete_mode_is_off(self):
        """The counterpart to safe delete mode: with it off, `sync_complete` is what does the deleting."""
        queued = self.interfaces(3, "swept")
        self.adapter.objects_to_delete["_interface"] = list(queued)
        # Set on the instance rather than the class, which every other adapter would otherwise read.
        self.adapter.safe_delete_mode = False

        self.adapter.sync_complete(unittest.mock.MagicMock(), unittest.mock.MagicMock())

        self.assertFalse(Interface.objects.filter(pk__in=[interface.pk for interface in queued]).exists())
        self.assertEqual(self.adapter.objects_to_delete["_interface"], [])


class ChangeLogCostTestCase(_CostTestCase):
    """Test that the writes one synced object takes record a single change log entry."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username="change-log-tester")

    def test_creating_an_interface_records_one_change(self):
        """Deferring the change log must not alter what it records.

        Creating an Interface writes it twice, and Nautobot consolidates those into one entry either
        way. This pins that the deferral keeps both the count and the final content.
        """
        with change_logging(JobChangeContext(user=self.user)):
            InterfaceModel.create(
                self.adapter,
                ids={"name": "logged", "device_name": self.device.name},
                attrs={"status": "Active", "type": "1000base-t"},
            )
            created = Interface.objects.get(name="logged")
            changes = ObjectChange.objects.filter(
                changed_object_type=ContentType.objects.get_for_model(Interface),
                changed_object_id=created.pk,
            )
            self.assertEqual(changes.count(), 1, "Expected one change log entry for the created Interface.")
            # The single entry must describe the Interface as it ended up, not as first inserted.
            self.assertEqual(changes.get().object_data["custom_fields"]["system_of_record"], "IPFabric")

    def test_an_unchanged_interface_records_no_change(self):
        """The nightly run on a settled estate must not fill the change log with the stamp alone.

        An object IP Fabric reports exactly as Nautobot holds it has nothing to record but the date,
        and an entry saying only that the date moved buries the runs that changed something.
        """
        interface = self.interfaces(1, "quiet")[0]
        # The run that first tags and stamps it does change it, and is recorded. The one after is
        # the one under test.
        nbutils.create_interface(self.device, {"name": interface.name, "type": "1000base-t"})
        job_scoped_cache.clear_all()

        with change_logging(JobChangeContext(user=self.user)):
            nbutils.create_interface(self.device, {"name": interface.name, "type": "1000base-t"})

        changes = ObjectChange.objects.filter(
            changed_object_type=ContentType.objects.get_for_model(Interface),
            changed_object_id=interface.pk,
        )
        self.assertEqual(changes.count(), 0, "Expected no change log entry for an unchanged Interface.")
        interface.refresh_from_db()
        self.assertEqual(interface.cf["last_synced_from_sor"], datetime.date.today().isoformat())

    def test_safe_deleting_an_interface_records_one_change(self):
        """Marking an object tags it and saves it, which must still read as a single change."""
        interface = self.interfaces(1, "marked")[0]
        model = InterfaceModel(name=interface.name, device_name=self.device.name, status="Active")
        model.adapter = self.adapter

        with change_logging(JobChangeContext(user=self.user)):
            model.delete()

        changes = ObjectChange.objects.filter(
            changed_object_type=ContentType.objects.get_for_model(Interface),
            changed_object_id=interface.pk,
        )
        self.assertEqual(changes.count(), 1, "Expected one change log entry for the safe deleted Interface.")


class SafeDeleteCostTestCase(_CostTestCase):
    """Test how much work marking objects for safe deletion takes."""

    def safe_delete(self, name):
        """Run the DiffSync delete for the named Interface, which marks it in safe delete mode."""
        model = InterfaceModel(name=name, device_name=self.device.name, status="Active")
        model.adapter = self.adapter
        model.delete()

    def test_the_tag_is_looked_up_once_for_every_interface(self):
        """Asking per object whether it is already tagged is a query per object."""
        for index in range(6):
            Interface.objects.create(
                device=self.device, name=f"eth{index}", status=self.active_status, type="1000base-t"
            )
        for index in range(6):
            self.safe_delete(f"eth{index}")

        self.assertEqual(
            nbutils.get_tagged_pks.cache_info().misses,
            1,
            "The safe delete tag membership must be resolved once for the whole model, not per object.",
        )

    def test_the_devices_interfaces_are_looked_up_once(self):
        """Removing many Interfaces from a Device must not fetch them one at a time."""
        for index in range(6):
            Interface.objects.create(
                device=self.device, name=f"eth{index}", status=self.active_status, type="1000base-t"
            )
        for index in range(6):
            self.safe_delete(f"eth{index}")

        self.assertEqual(
            nbutils.get_device_interfaces_by_name.cache_info().misses,
            1,
            "The Device's Interfaces must be fetched once for the Device, not once per Interface.",
        )

    def test_an_interface_the_device_does_not_have_is_reported(self):
        """A name the Device has no Interface for is logged, not passed over in silence."""
        self.safe_delete("no-such-interface")

        logged = [str(call) for call in self.adapter.job.logger.error.call_args_list]
        self.assertTrue(
            any("Unable to find an Interface with the name no-such-interface" in line for line in logged),
            f"Expected the missing Interface to be reported: {logged}",
        )

    def test_both_tags_are_applied_in_one_operation(self):
        interface = Interface.objects.create(
            device=self.device, name="eth0", status=self.active_status, type="1000base-t"
        )
        self.safe_delete("eth0")

        interface.refresh_from_db()
        self.assertEqual(
            sorted(tag.name for tag in interface.tags.all()),
            ["SSoT Safe Delete", "SSoT Synced from IPFabric"],
        )

    def test_an_already_marked_interface_is_not_written_again(self):
        """The short circuit for an already marked object is what keeps a re-run cheap."""
        interface = Interface.objects.create(
            device=self.device, name="eth0", status=self.active_status, type="1000base-t"
        )
        interface.tags.add(self.safe_delete_tag)
        before = interface.last_updated

        job_scoped_cache.clear_all()
        self.safe_delete("eth0")

        interface.refresh_from_db()
        self.assertEqual(interface.last_updated, before, "An already marked Interface was written again.")


class ResyncCostTestCase(_CostTestCase):
    """Count what an object costs on a run that finds it exactly as IP Fabric last reported it.

    This is the run an estate makes every night, and the one almost all of the work goes into: on an
    estate of a hundred thousand addresses, nothing has changed and the only thing left to write is
    the stamp recording that the sync saw each one.
    """

    def setUp(self):
        super().setUp()
        self.interface = self.interfaces(1, "eth")[0]
        self.prefix, _ = Prefix.objects.get_or_create(
            prefix="10.70.0.0/24", namespace=get_default_namespace(), status=self.active_status
        )
        self.address = IPAddress.objects.create(address="10.70.0.5/24", status=self.active_status, parent=self.prefix)

    def test_an_unchanged_address_is_stamped_without_being_revalidated(self):
        """`validated_save()` costs about eleven queries, since `IPAddress.save()` calls `clean()`.

        Nothing about the address changed, so there is nothing to validate and nothing to write but
        the custom field data.
        """
        with unittest.mock.patch.object(IPAddress, "validated_save", autospec=True) as mock_save:
            nbutils.create_ip("10.70.0.5", 24)

        mock_save.assert_not_called()
        self.address.refresh_from_db()
        self.assertEqual(self.address.cf["system_of_record"], "IPFabric")
        self.assertEqual(self.address.cf["last_synced_from_sor"], datetime.date.today().isoformat())
        self.assertTrue(self.address.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_a_changed_mask_is_still_written_through_validation(self):
        """Validation is what settles which Prefix an address hangs under, so a change still needs it."""
        with unittest.mock.patch.object(IPAddress, "validated_save", autospec=True) as mock_save:
            nbutils.create_ip("10.70.0.5", 25)

        mock_save.assert_called_once()

    def test_an_unchanged_interface_is_stamped_without_being_revalidated(self):
        """An Interface Nautobot already holds has no field set on it, so the stamp is the whole write."""
        with unittest.mock.patch.object(Interface, "validated_save", autospec=True) as mock_save:
            nbutils.create_interface(self.device, {"name": self.interface.name, "type": "1000base-t"})

        mock_save.assert_not_called()
        self.interface.refresh_from_db()
        self.assertEqual(self.interface.cf["last_synced_from_sor"], datetime.date.today().isoformat())
        self.assertTrue(self.interface.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_an_object_already_tagged_is_not_tagged_again(self):
        """The Tag is two statements of its own, so it is asked for only where it is missing."""
        nbutils.create_interface(self.device, {"name": self.interface.name, "type": "1000base-t"})
        job_scoped_cache.clear_all()

        with CaptureQueriesContext(connection) as queries:
            nbutils.create_interface(self.device, {"name": self.interface.name, "type": "1000base-t"})

        tag_writes = [
            query["sql"]
            for query in queries.captured_queries
            if write_to("extras_taggeditem").match(query["sql"].strip())
        ]
        self.assertEqual(tag_writes, [], f"Expected no second tagging of the Interface, got {tag_writes}")
        self.assertEqual(self.interface.tags.count(), 1)


class CableWriteCostTestCase(_CostTestCase):
    """Count the writes creating one Cable makes to the Cable table."""

    def setUp(self):
        super().setUp()
        self.int_a, self.int_b = self.interfaces(2, "cabled")

    def test_creating_a_cable_writes_it_once(self):
        """The stamp rides the INSERT rather than a second save applying it afterwards.

        A Cable's `validated_save()` runs the termination checks, so a redundant one is among the
        more expensive repeats in the sync.
        """
        with CaptureQueriesContext(connection) as queries:
            cable = cables.create_cable(self.int_a, self.int_b, "Connected")

        writes = [
            query["sql"].split(None, 3)[0].upper()
            for query in queries.captured_queries
            if WRITE_TO_CABLE.match(query["sql"].strip())
        ]
        self.assertEqual(writes, ["INSERT"], f"Expected one write to the Cable table, got {writes}")
        self.assertIsNotNone(cable)
        self.assertTrue(cable.tags.filter(name="SSoT Synced from IPFabric").exists())
        self.assertEqual(cable.cf["system_of_record"], "IPFabric")
        self.assertEqual(cable.cf["last_synced_from_sor"], datetime.date.today().isoformat())

    def test_a_cable_still_at_its_reported_status_is_not_rewritten(self):
        """Every Cable on a re-sync that changes nothing, so it is worth not revalidating."""
        cable = cables.create_cable(self.int_a, self.int_b, "Connected")

        with unittest.mock.patch.object(Cable, "validated_save", autospec=True) as mock_save:
            self.assertTrue(cables.update_cable_status(cable, "Connected"))

        mock_save.assert_not_called()
        cable.refresh_from_db()
        self.assertEqual(cable.cf["last_synced_from_sor"], datetime.date.today().isoformat())
