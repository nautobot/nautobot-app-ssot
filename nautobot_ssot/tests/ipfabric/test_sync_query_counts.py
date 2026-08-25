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

WRITE_TO_INTERFACE = re.compile(r'^(INSERT INTO|UPDATE)\s+"?dcim_interface"?', re.IGNORECASE)


class InterfaceWriteCostTestCase(TestCase):
    """Count the writes a single Interface sync makes to the Interface table."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        active_status = Status.objects.get(name="Active")
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
        location = Location.objects.create(name="query-count-site1", location_type=location_type, status=active_status)
        manufacturer = Manufacturer.objects.create(name="query-count-vendor")
        device_type = DeviceType.objects.create(model="query-count-model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="query-count-device",
            status=active_status,
            role=role,
            location=location,
            device_type=device_type,
            serial="serial",
        )
        self.device.tags.add(ssot_tag)
        self.existing = Interface.objects.create(
            device=self.device, name="eth0", status=active_status, type="1000base-t"
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
