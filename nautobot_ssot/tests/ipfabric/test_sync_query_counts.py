"""Tests for how much database work syncing one object costs.

An IP Fabric estate of a few thousand Devices carries a hundred thousand Interfaces and about as
many IP Addresses, so anything a single object write repeats is multiplied by that. These tests
count the writes each object costs rather than the total queries, since the totals move with
Nautobot's own validation while the repeated writes are what this integration controls.
"""

import re
import unittest.mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nautobot.apps.change_logging import JobChangeContext, change_logging
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import ObjectChange, Role, Status, Tag
from nautobot.ipam.models import IPAddress

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync, delete_objects
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
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

    def test_creating_an_interface_with_an_address_writes_it_once(self):
        """One INSERT carrying the stamp, and no second save to apply it.

        Each write is a full `validated_save()`, so one more doubles what an Interface costs.
        """
        writes = self.count_interface_writes(
            lambda: InterfaceModel.create(
                self.adapter,
                ids={"name": "eth1", "device_name": self.device.name},
                attrs={
                    "ip_address": "10.0.0.1",
                    "subnet_mask": "255.255.255.0",
                    "status": "Active",
                    "type": "1000base-t",
                },
            )
        )
        self.assertEqual(len(writes), 1, f"Expected one write to the Interface table, got {writes}")
        self.assertEqual(Interface.objects.get(name="eth1").ip_addresses.count(), 1)

    def test_creating_an_address_does_not_save_it_a_second_time(self):
        """The stamp rides the INSERT, rather than a second save applying it afterwards.

        Each write is a full `validated_save()`, and `IPAddress.save()` calls `clean()` itself, so a
        redundant one is worth about eleven queries on every address a first sync creates.

        Measured as writes following the INSERT, because creating the parent Prefix makes Nautobot
        reparent the addresses it now contains, which writes to the same table beforehand.
        """
        with CaptureQueriesContext(connection) as queries:
            InterfaceModel.create(
                self.adapter,
                ids={"name": "eth2", "device_name": self.device.name},
                attrs={
                    "ip_address": "10.0.0.2",
                    "subnet_mask": "255.255.255.0",
                    "status": "Active",
                    "type": "1000base-t",
                },
            )
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

    def test_updating_an_interface_with_an_address_writes_it_once(self):
        """Only `update` tags the Interface, so assigning an address adds no second write."""
        writes = self.count_interface_writes(
            lambda: self.interface_model("eth0").update(
                {"ip_address": "10.0.0.2", "subnet_mask": "255.255.255.0", "description": "changed"}
            )
        )
        self.assertEqual(len(writes), 1, f"Expected one write to the Interface table, got {writes}")
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.description, "changed")
        self.assertEqual([str(ip.host) for ip in self.existing.ip_addresses.all()], ["10.0.0.2"])

    def test_a_synced_interface_is_still_tagged_and_stamped(self):
        """Removing the duplicate tagging must not leave the Interface untagged."""
        InterfaceModel.create(
            self.adapter,
            ids={"name": "eth2", "device_name": self.device.name},
            attrs={
                "ip_address": "10.0.0.3",
                "subnet_mask": "255.255.255.0",
                "status": "Active",
                "type": "1000base-t",
            },
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
            attrs={
                "ip_address": "10.0.0.4",
                "subnet_mask": "255.255.255.0",
                "status": "Active",
                "type": "1000base-t",
            },
        )
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
                attrs={"ip_address": None, "subnet_mask": None, "status": "Active", "type": "1000base-t"},
            )
            created = Interface.objects.get(name="logged")
            changes = ObjectChange.objects.filter(
                changed_object_type=ContentType.objects.get_for_model(Interface),
                changed_object_id=created.pk,
            )
            self.assertEqual(changes.count(), 1, "Expected one change log entry for the created Interface.")
            # The single entry must describe the Interface as it ended up, not as first inserted.
            self.assertEqual(changes.get().object_data["custom_fields"]["system_of_record"], "IPFabric")

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
