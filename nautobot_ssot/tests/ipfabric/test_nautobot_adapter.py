"""Unit tests for the IPFabric DiffSync adapter class."""

import unittest
from uuid import uuid4

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import (
    Cable,
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
from nautobot.ipam.models import VLAN, IPAddress, Prefix, get_default_namespace

try:
    from nautobot.core.testing.utils import AssertNoRepeatedQueries
except ImportError:
    AssertNoRepeatedQueries = None

import nautobot_ssot.integrations.ipfabric.utilities.cables as tonb_cables
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache


# pylint: disable=too-many-public-methods
class TestNautobotAdapter(TestCase):
    """Test cases for InfoBlox Nautobot adapter."""

    def setUp(self):
        populate_status_choices()
        # Cached Tag lookups must not outlive a test's transaction; see test_cables.py.
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
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

    def _address_a_primary_interface(self):
        """Give the stack master's `eth0` an IP Address and make it the Device's primary."""
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
        return stack_master

    def _load_with_scope(self, **kwargs):
        """Load with the named object types selected, and return the Interfaces keyed by name."""
        self.nb_adapter.scope = SyncScope.from_job_kwargs(kwargs)
        self.nb_adapter.load_interfaces(
            device_record=self._address_a_primary_interface(), diffsync_device=unittest.mock.Mock()
        )
        return {interface.name: interface for interface in self.nb_adapter.get_all("interface")}

    def test_interfaces_out_of_scope_loads_none(self):
        """With Interfaces deselected, none are loaded, so none can diff against IP Fabric."""
        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_interfaces": False})
        self.nb_adapter.load_data()

        self.assertEqual(self.nb_adapter.get_all("interface"), [])
        self.assertNotEqual(self.nb_adapter.get_all("device"), [], "Devices should still load.")

    def test_ip_addresses_out_of_scope_reports_no_address(self):
        """Reported as absent, matching the source adapter, so the stored address is left alone."""
        loaded = self._load_with_scope(sync_ip_addresses=False)

        self.assertIsNone(loaded["eth0"].ip_address)
        self.assertIsNone(loaded["eth0"].subnet_mask)
        self.assertFalse(loaded["eth0"].ip_is_primary, "Primary IP cannot survive its address going out of scope.")

    def test_primary_ip_out_of_scope_keeps_the_address(self):
        """Only the primary assignment is withheld; the address itself is still synced."""
        loaded = self._load_with_scope(sync_primary_ip=False)

        self.assertEqual(loaded["eth0"].ip_address, "10.0.0.5")
        self.assertFalse(loaded["eth0"].ip_is_primary)

    def test_addresses_out_of_scope_still_loads_interfaces(self):
        """Interfaces stay in scope on their own, so the load prefetches them without their addresses."""
        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_ip_addresses": False})
        self.nb_adapter.load_data()

        interfaces = self.nb_adapter.get_all("interface")
        self.assertNotEqual(interfaces, [], "Interfaces should still load.")
        for interface in interfaces:
            self.assertIsNone(interface.ip_address, interface.name)

    def test_vlans_out_of_scope_loads_none(self):
        """With VLANs deselected, an existing Nautobot VLAN is not loaded and so cannot be deleted."""
        self.site1.location_type.content_types.add(ContentType.objects.get_for_model(VLAN))
        site_vlan = VLAN.objects.create(name="vlan1", vid=1, status=self.active_status)
        site_vlan.locations.add(self.site1)

        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_vlans": False})
        self.nb_adapter.load_data()

        self.assertEqual(self.nb_adapter.get_all("vlan"), [])

    def _interface(self, device_name, interface_name):
        """Create a cableable Interface on the named Device.

        The type must be physical; Nautobot refuses to cable virtual or wireless Interfaces.
        """
        return Interface.objects.create(
            name=interface_name,
            device=Device.objects.get(name=device_name),
            type="1000base-t",
            status=self.active_status,
        )

    def _cable(self, interface_a, interface_b):
        """Cable two Interfaces together."""
        cable = Cable(
            termination_a=interface_a,
            termination_b=interface_b,
            status=Status.objects.get(name="Connected"),
        )
        cable.validated_save()
        return cable

    def test_load_cables_orders_endpoints_independently_of_nautobot_sides(self):
        """The A side of the loaded model is the lower endpoint, not whichever end Nautobot cabled first."""
        int_dev1 = self._interface("dev1", "eth0")
        int_dev2 = self._interface("dev2", "eth0")
        # Cabled with dev2 as Nautobot's A side; the loaded model should still order dev1 first.
        cable = self._cable(int_dev2, int_dev1)

        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_cables": True})
        self.nb_adapter.load_data()

        cables = self.nb_adapter.get_all("cable")
        self.assertEqual(len(cables), 1)
        self.assertEqual(cables[0].get_unique_id(), "dev1__eth0__dev2__eth0")
        self.assertEqual(cables[0].status, "Connected")
        # Recorded so update/delete can re-find the Cable without walking its endpoints.
        self.assertEqual(cables[0].cable_pk, cable.pk)

    def test_cable_connects_matches_terminations_in_either_order(self):
        """`cable_connects` reads termination IDs, which must agree with the terminations themselves."""
        int_dev1 = self._interface("dev1", "eth0")
        int_dev2 = self._interface("dev2", "eth0")
        int_other = self._interface("dev2", "eth1")
        cable = self._cable(int_dev1, int_dev2)

        self.assertTrue(tonb_cables.cable_connects(cable, int_dev1, int_dev2))
        self.assertTrue(tonb_cables.cable_connects(cable, int_dev2, int_dev1))
        self.assertFalse(tonb_cables.cable_connects(cable, int_dev1, int_other))

    def test_retrieve_cable_finds_the_loaded_cable_by_pk(self):
        """A Cable model carrying `cable_pk` resolves back to the Nautobot Cable it was loaded from."""
        cable = self._cable(self._interface("dev1", "eth0"), self._interface("dev2", "eth0"))

        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_cables": True})
        self.nb_adapter.load_data()

        loaded = self.nb_adapter.get_all("cable")[0]
        self.assertEqual(loaded.retrieve_cable(), cable)

    def test_load_cables_skips_links_with_one_end_out_of_scope(self):
        """A link whose far end is outside the Location filter is left alone rather than loaded."""
        self._cable(self._interface("dev1", "eth0"), self._interface("dev3", "eth0"))

        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_cables": True})
        self.nb_adapter.location_filter = self.site1
        self.nb_adapter.load_data()

        self.assertEqual(self.nb_adapter.get_all("cable"), [])

    def test_load_cables_spanning_locations(self):
        """A link between two in-scope Locations is loaded, since Cables are not children of one."""
        self._cable(self._interface("dev1", "eth0"), self._interface("dev3", "eth0"))

        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_cables": True})
        self.nb_adapter.load_data()

        cables = self.nb_adapter.get_all("cable")
        self.assertEqual(len(cables), 1)
        self.assertEqual(cables[0].get_unique_id(), "dev1__eth0__dev3__eth0")

    def test_load_cables_not_loaded_when_disabled(self):
        """Cables are opt in, so a Cable in the database is ignored unless the scope includes them."""
        self._cable(self._interface("dev1", "eth0"), self._interface("dev2", "eth0"))

        self.nb_adapter.load_data()

        self.assertEqual(self.nb_adapter.get_all("cable"), [])

    def test_load_cables_skips_interfaces_absent_from_the_store(self):
        """An Interface returned by the query but never loaded takes its link out of scope."""
        self._cable(self._interface("dev1", "eth0"), self._interface("dev3", "eth0"))
        # Only site1 is loaded, so dev3's Interface is in the Cable query but not in the store.
        self.nb_adapter.location_filter = self.site1
        self.nb_adapter.load_data()

        self.nb_adapter.load_cables(Device.objects.all())

        self.assertEqual(self.nb_adapter.get_all("cable"), [])

    def test_load_cables_skips_cables_with_too_many_in_scope_ends(self):
        """A Cable terminating on more than two in-scope Interfaces cannot be described point to point."""
        for index in range(3):
            self._interface("dev1", f"eth{index}")
        self.nb_adapter.load_data()
        shared_cable = unittest.mock.MagicMock()
        shared_cable.pk = uuid4()
        records = []
        for index in range(3):
            record = unittest.mock.MagicMock()
            record.name = f"eth{index}"
            record.device.name = "dev1"
            record.cable = shared_cable
            records.append(record)

        with unittest.mock.patch.object(tonb_cables, "cabled_interfaces", return_value=records):
            with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as captured:
                self.nb_adapter.load_cables(Device.objects.none())

        self.assertEqual(self.nb_adapter.get_all("cable"), [])
        self.assertTrue(any("terminates on 3 in scope Interfaces" in line for line in captured.output))

    def test_load_cables_warns_on_duplicate_endpoint_pairs(self):
        """Two Cables resolving to the same endpoint pair cannot both be loaded."""
        self._interface("dev1", "eth0")
        self._interface("dev2", "eth0")
        self.nb_adapter.load_data()
        records = []
        for _ in range(2):
            cable = unittest.mock.MagicMock()
            cable.pk = uuid4()
            cable.status.name = "Connected"
            for device_name in ("dev1", "dev2"):
                record = unittest.mock.MagicMock()
                record.name = "eth0"
                record.device.name = device_name
                record.cable = cable
                records.append(record)

        with unittest.mock.patch.object(tonb_cables, "cabled_interfaces", return_value=records):
            with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as captured:
                self.nb_adapter.load_cables(Device.objects.none())

        self.assertEqual(len(self.nb_adapter.get_all("cable")), 1)
        self.assertTrue(any("Duplicate Cable discovered" in line for line in captured.output))

    def test_get_in_scope_devices_honours_tagged_only(self):
        """`sync_ipfabric_tagged_only` narrows Device scope to tagged Devices."""
        locations = Location.objects.filter(name="stack")
        self.nb_adapter.sync_ipfabric_tagged_only = False
        self.assertEqual(self.nb_adapter.get_in_scope_devices(locations).count(), 3)

        self.nb_adapter.sync_ipfabric_tagged_only = True
        self.assertEqual(self.nb_adapter.get_in_scope_devices(locations).count(), 0)

        Device.objects.get(name="stack1").tags.add(self.ssot_tag)
        self.assertEqual(self.nb_adapter.get_in_scope_devices(locations).count(), 1)

    @unittest.skipIf(AssertNoRepeatedQueries is None, "Requires Nautobot 3.1+ (AssertNoRepeatedQueries)")
    def test_load_cables_no_n_plus_one(self):
        """Reading each Cable's Status must use select_related, not a query per cabled Interface."""
        for index in range(5):
            self._cable(self._interface("dev1", f"eth{index}"), self._interface("dev2", f"eth{index}"))
        # Load the Interfaces into the store without loading Cables, so only `load_cables` is measured.
        self.nb_adapter.load_data()

        with AssertNoRepeatedQueries(self, threshold=1):
            self.nb_adapter.load_cables(Device.objects.filter(location=self.site1))
