"""Unit tests for the IPFabric DiffSync adapter class."""

import unittest

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    VirtualChassis,
)
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status, Tag
from nautobot.ipam.models import IPAddress, Prefix, get_default_namespace

try:
    from nautobot.core.testing.utils import AssertNoRepeatedQueries
except ImportError:
    AssertNoRepeatedQueries = None

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync


class TestNautobotAdapter(TestCase):
    """Test cases for InfoBlox Nautobot adapter."""

    def setUp(self):
        populate_status_choices()
        device_ct = ContentType.objects.get_for_model(Device)
        self.active_status = Status.objects.get(name="Active")
        self.ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={
                "color": ColorChoices.COLOR_LIGHT_GREEN,
                "description": "Object synced at some point from IPFabric to Nautobot",
            },
        )
        self.ssot_tag.content_types.add(device_ct)
        role = Role.objects.create(name="test")
        role.content_types.add(device_ct)
        site_lt, _ = LocationType.objects.get_or_create(name="site")
        site_lt.content_types.add(device_ct)
        self.site1 = Location.objects.create(name="site1", location_type=site_lt, status=self.active_status)
        site2 = Location.objects.create(name="site2", location_type=site_lt, status=self.active_status)
        self.stack_site = Location.objects.create(name="stack", location_type=site_lt, status=self.active_status)
        self.stack_site.tags.add(self.ssot_tag)
        man1 = Manufacturer.objects.create(name="man1")
        man2 = Manufacturer.objects.create(name="man2")
        dev_type1 = DeviceType.objects.create(model="dev_type1", manufacturer=man1)
        dev_type2 = DeviceType.objects.create(model="dev_type2", manufacturer=man2)
        platform1 = Platform.objects.create(name="platform1", manufacturer=man1)
        self.stack = VirtualChassis.objects.create(name="stack1")
        Device.objects.create(
            name="dev1",
            serial="abc",
            status=self.active_status,
            role=role,
            location=self.site1,
            device_type=dev_type1,
            platform=platform1,
        )
        Device.objects.create(
            name="dev2",
            serial="def",
            status=self.active_status,
            role=role,
            location=self.site1,
            device_type=dev_type1,
            platform=platform1,
        )
        Device.objects.create(
            name="dev3",
            serial="xyz",
            status=self.active_status,
            role=role,
            location=site2,
            device_type=dev_type2,
        )
        stack_master = Device.objects.create(
            name="stack1",
            serial="st123",
            status=self.active_status,
            role=role,
            location=self.stack_site,
            device_type=dev_type2,
            virtual_chassis=self.stack,
            vc_position=1,
            vc_priority=1,
        )
        self.stack.master = stack_master
        self.stack.validated_save()
        for i in range(0, 9):
            Interface.objects.create(name=f"eth{i}", device=stack_master, type="virtual", status=self.active_status)
        Device.objects.create(
            name="stack2",
            serial="st456",
            status=self.active_status,
            role=role,
            location=self.stack_site,
            device_type=dev_type2,
            virtual_chassis=self.stack,
            vc_position=2,
            vc_priority=2,
        )
        Device.objects.create(
            name="stack3",
            serial="st789",
            status=self.active_status,
            role=role,
            location=self.stack_site,
            device_type=dev_type2,
            virtual_chassis=self.stack,
            vc_position=3,
            vc_priority=3,
        )
        self.nb_adapter = NautobotDiffSync(
            job=unittest.mock.Mock(),
            sync=unittest.mock.Mock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.Location", autospec=True)
    @unittest.mock.patch.object(NautobotDiffSync, "load_interfaces")
    def test_load_device(self, mock_load_interfaces, mock_location):
        self.nb_adapter.load_device(Device.objects.filter(location=self.site1), mock_location)
        self.assertEqual(mock_load_interfaces.call_count, 2)
        self.assertEqual(mock_location.add_child.call_count, 2)
        loaded_devices = self.nb_adapter.get_all("device")
        self.assertEqual(len(loaded_devices), 2)
        self.assertEqual(loaded_devices[0].name, "dev1")
        self.assertEqual(loaded_devices[1].name, "dev2")
        self.assertEqual(loaded_devices[0].serial_number, "abc")
        self.assertEqual(loaded_devices[1].serial_number, "def")
        for device in loaded_devices:
            self.assertEqual(device.model, "dev_type1")
            self.assertEqual(device.role, "test")
            self.assertEqual(device.location_name, "site1")
            self.assertEqual(device.vendor, "man1")
            self.assertEqual(device.status, "Active")
            if device.name != "dev3":
                self.assertEqual(device.platform, "platform1")
            else:
                self.assertEqual(device.platform, "")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.Location", autospec=True)
    def test_load_device_stacks(self, mock_location):
        self.nb_adapter.load_device(Device.objects.filter(location=self.stack_site), mock_location)
        loaded_devices = self.nb_adapter.get_all("device")
        self.assertEqual(len(loaded_devices), 3)
        self.assertEqual(loaded_devices[0].name, "stack1")
        self.assertEqual(loaded_devices[1].name, "stack2")
        self.assertEqual(loaded_devices[2].name, "stack3")
        self.assertTrue(loaded_devices[0].vc_master)
        self.assertFalse(loaded_devices[1].vc_master)
        for device in loaded_devices:
            self.assertEqual(device.model, "dev_type2")
            self.assertEqual(device.role, "test")
            self.assertEqual(device.location_name, "stack")
            self.assertEqual(device.vendor, "man2")
            self.assertEqual(device.status, "Active")
            self.assertEqual(device.vc_priority, int(device.name[-1]))
            self.assertEqual(device.vc_position, int(device.name[-1]))

    @unittest.skipIf(AssertNoRepeatedQueries is None, "Requires Nautobot 3.1+ (AssertNoRepeatedQueries)")
    def test_load_data_no_n_plus_one(self):
        """Full `load_data()` must not produce repeated queries over the number of devices."""
        with AssertNoRepeatedQueries(self, threshold=3):
            self.nb_adapter.load_data()

    @unittest.skipIf(AssertNoRepeatedQueries is None, "Requires Nautobot 3.1+ (AssertNoRepeatedQueries)")
    def test_get_initial_location_no_n_plus_one_status(self):
        """Iterating locations to read `.status.name` must use select_related, not lazy load."""
        with AssertNoRepeatedQueries(self, threshold=1):
            locations = self.nb_adapter.get_initial_location(None)
            for location in locations:
                _ = location.status.name
            self.assertEqual(len(locations), 3, "Should get 3 Locations with no SSoT tag filter.")

    @unittest.skipIf(AssertNoRepeatedQueries is None, "Requires Nautobot 3.1+ (AssertNoRepeatedQueries)")
    def test_get_initial_location_tagged_no_n_plus_one_status(self):
        """Iterating locations to read `.status.name` must use select_related, not lazy load."""
        with AssertNoRepeatedQueries(self, threshold=1):
            self.nb_adapter.sync_ipfabric_tagged_only = True
            locations = self.nb_adapter.get_initial_location(self.ssot_tag)
            for location in locations:
                _ = location.status.name
            self.assertEqual(len(locations), 1, "Should get 1 Locations with SSoT tag filter.")

    @unittest.skipIf(AssertNoRepeatedQueries is None, "Requires Nautobot 3.1+ (AssertNoRepeatedQueries)")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.Location", autospec=True)
    def test_load_device_no_n_plus_one(self, mock_location):
        """Device loading with N stack members should not issue per-member or per-interface queries."""
        with AssertNoRepeatedQueries(self, threshold=1):
            self.nb_adapter.load_device(Device.objects.filter(location=self.stack_site), mock_location)

    def test_get_initial_location_filter_only(self):
        """`location_filter` without tagged_only returns the named location."""
        self.nb_adapter.location_filter = self.site1
        locations = list(self.nb_adapter.get_initial_location(self.ssot_tag))
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0].id, self.site1.id)

    def test_get_initial_location_tagged_and_filter_match(self):
        """`location_filter` with `sync_ipfabric_tagged_only` returns the tagged location."""
        self.nb_adapter.sync_ipfabric_tagged_only = True
        self.nb_adapter.location_filter = self.stack_site
        locations = list(self.nb_adapter.get_initial_location(self.ssot_tag))
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0].id, self.stack_site.id)

    def test_get_initial_location_tagged_and_filter_no_match_warns(self):
        """Untagged `location_filter` with `sync_ipfabric_tagged_only` returns empty + warning."""
        self.nb_adapter.sync_ipfabric_tagged_only = True
        self.nb_adapter.location_filter = self.site1
        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as captured:
            locations = list(self.nb_adapter.get_initial_location(self.ssot_tag))
        self.assertEqual(len(locations), 0)
        self.assertTrue(
            any("is not tagged" in line for line in captured.output),
            f"Expected 'is not tagged' warning, got: {captured.output}",
        )

    def test_load_interfaces_populates_ip_data(self):
        """`load_interfaces` reads the first prefetched IP and sets ip_address/subnet_mask/ip_is_primary."""
        stack_master = self.stack.master
        int_eth0 = stack_master.interfaces.get(name="eth0")

        prefix, _ = Prefix.objects.get_or_create(
            prefix="10.0.0.0/24", namespace=get_default_namespace(), status=self.active_status
        )
        ip_addr, _ = IPAddress.objects.get_or_create(address="10.0.0.5/24", status=self.active_status, parent=prefix)
        int_eth0.ip_addresses.add(ip_addr)
        stack_master.primary_ip4 = ip_addr
        stack_master.validated_save()
        stack_master.refresh_from_db()

        self.nb_adapter.load_interfaces(device_record=stack_master, diffsync_device=unittest.mock.Mock())

        loaded = {i.name: i for i in self.nb_adapter.get_all("interface")}
        # eth0 hits the `if ip_addresses:` branch (line 114)
        self.assertEqual(loaded["eth0"].ip_address, "10.0.0.5")
        self.assertEqual(loaded["eth0"].subnet_mask, "255.255.255.0")
        self.assertTrue(loaded["eth0"].ip_is_primary)
        # eth1..eth8 hit the `else` branch
        self.assertIsNone(loaded["eth1"].ip_address)
        self.assertIsNone(loaded["eth1"].subnet_mask)
        self.assertFalse(loaded["eth1"].ip_is_primary)
