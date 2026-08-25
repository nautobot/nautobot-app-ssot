"""Tests for how much database work syncing one object costs.

An IP Fabric estate of a few thousand Devices carries a hundred thousand Interfaces and about as
many IP Addresses, so anything a single object write repeats is multiplied by that. These tests
count the writes each object costs rather than the total queries, since the totals move with
Nautobot's own validation while the repeated writes are what this integration controls.
"""

import re
import unittest.mock

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status, Tag

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

# The trailing boundary keeps this off tables whose names merely start with "dcim_interface",
# such as the tagged VLAN join table.
WRITE_TO_INTERFACE = re.compile(r'^(INSERT INTO|UPDATE)\s+"?dcim_interface"?(\s|$)', re.IGNORECASE)


class InterfaceWriteCostTestCase(TestCase):
    """Count the writes a single Interface sync makes to the Interface table."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active_status = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced from IPFabric"},
        )
        ssot_tag.content_types.add(device_ct, ContentType.objects.get_for_model(Interface))
        Tag.objects.get_or_create(
            name="SSoT Safe Delete", defaults={"color": ColorChoices.COLOR_RED, "description": "Safe delete"}
        )
        role = Role.objects.create(name="query-count-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="query-count-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(
            name="query-count-site1", location_type=location_type, status=self.active_status
        )
        manufacturer = Manufacturer.objects.create(name="query-count-vendor")
        device_type = DeviceType.objects.create(model="query-count-model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="query-count-device",
            status=self.active_status,
            role=role,
            location=location,
            device_type=device_type,
            serial="serial",
        )
        self.device.tags.add(ssot_tag)
        self.existing = Interface.objects.create(
            device=self.device, name="eth0", status=self.active_status, type="1000base-t"
        )
        job = unittest.mock.MagicMock()
        job.debug = False
        self.adapter = NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
        )

    def count_interface_writes(self, operation):
        """Return how many INSERTs and UPDATEs `operation` makes against the Interface table."""
        with CaptureQueriesContext(connection) as queries:
            operation()
        writes = [query["sql"] for query in queries.captured_queries if WRITE_TO_INTERFACE.match(query["sql"].strip())]
        # Only the verb is kept, so a failure reports how many writes happened rather than pages of SQL.
        return [write.split(None, 3)[0].upper() for write in writes]

    def interface_model(self, name):
        """Return a DiffSync Interface bound to this test's adapter."""
        model = InterfaceModel(name=name, device_name=self.device.name, status="Active")
        model.adapter = self.adapter
        return model

    def test_creating_an_interface_with_an_address_writes_it_twice(self):
        """Creating one takes an INSERT and the UPDATE that stamps it, which is the floor.

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
        self.assertEqual(len(writes), 2, f"Expected two writes to the Interface table, got {writes}")
        self.assertEqual(Interface.objects.get(name="eth1").ip_addresses.count(), 1)

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


class DeleteCostTestCase(TestCase):
    """Count the queries deleting a set of objects takes when safe delete mode is off."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active_status = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced from IPFabric"},
        )
        Tag.objects.get_or_create(
            name="SSoT Safe Delete", defaults={"color": ColorChoices.COLOR_RED, "description": "Safe delete"}
        )
        role = Role.objects.create(name="delete-cost-role")
        role.content_types.add(device_ct)
        self.location_type, _ = LocationType.objects.get_or_create(name="delete-cost-site")
        self.location_type.content_types.add(device_ct)
        location = Location.objects.create(
            name="delete-cost-site1", location_type=self.location_type, status=self.active_status
        )
        manufacturer = Manufacturer.objects.create(name="delete-cost-vendor")
        device_type = DeviceType.objects.create(model="delete-cost-model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="delete-cost-device",
            status=self.active_status,
            role=role,
            location=location,
            device_type=device_type,
            serial="serial",
        )
        job = unittest.mock.MagicMock()
        job.debug = False
        self.adapter = NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
        )

    def interfaces(self, count, prefix):
        """Return `count` newly created Interfaces on this test's Device."""
        return [
            Interface.objects.create(
                device=self.device, name=f"{prefix}{index}", status=self.active_status, type="1000base-t"
            )
            for index in range(count)
        ]

    def delete_query_count(self, nautobot_objects):
        """Return how many queries deleting the given objects takes."""
        with CaptureQueriesContext(connection) as queries:
            self.adapter.delete_objects(nautobot_objects)
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
        self.adapter.delete_objects(deleted)
        self.assertFalse(Interface.objects.filter(pk__in=[interface.pk for interface in deleted]).exists())

    def test_objects_of_different_models_are_each_batched(self):
        """`objects_to_delete` is keyed per model, but a mixed list must not delete the wrong rows."""
        interfaces = self.interfaces(3, "mixed")
        spare_location = Location.objects.create(
            name="delete-cost-spare", location_type=self.location_type, status=self.active_status
        )
        self.adapter.delete_objects([*interfaces, spare_location])
        self.assertFalse(Interface.objects.filter(pk__in=[interface.pk for interface in interfaces]).exists())
        self.assertFalse(Location.objects.filter(pk=spare_location.pk).exists())

    def test_a_protected_object_does_not_stop_the_rest_of_its_batch(self):
        """The Device at a Location protects it, so that Location cannot be deleted with the others."""
        free_location = Location.objects.create(
            name="delete-cost-free", location_type=self.location_type, status=self.active_status
        )
        protected_location = self.device.location

        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
            self.adapter.delete_objects([protected_location, free_location])

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
