"""Unit tests for the IPFabric DiffSync adapter class."""

import json
from collections import defaultdict
from unittest.mock import MagicMock, patch

from ipfabric.models.device import Device
from nautobot.apps.testing import TestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import IPFabricDiffSync
from nautobot_ssot.integrations.ipfabric.jobs import IpFabricDataSource
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


SITE_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_sites.json")
DEVICE_INVENTORY_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_device_inventory.json")
VLAN_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_vlans.json")
INTERFACE_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_interface_inventory.json")
NETWORKS_FIXTURE = [{"net": "10.10.0.0/24", "sn": "a000a02", "ip": "10.10.0.10"}]
STACKS_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_stack_members.json")
CONNECTIVITY_MATRIX_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_connectivity_matrix.json")


def mock_ipfabric_client():
    """Return a mock IPFClient serving the JSON fixtures."""
    ipfabric_client = MagicMock()
    ipfabric_client.inventory.sites.all.return_value = SITE_FIXTURE
    ipfabric_client.devices.by_site = defaultdict(list)
    for dev in DEVICE_INVENTORY_FIXTURE:
        ipfabric_client.devices.by_site[dev["siteName"]].append(Device(**dev))  # pylint: disable=no-member
    ipfabric_client.fetch_all = MagicMock(
        side_effect=(lambda x: VLAN_FIXTURE if x == "tables/vlan/site-summary" else "")
    )
    ipfabric_client.inventory.interfaces.all.return_value = INTERFACE_FIXTURE
    ipfabric_client.technology.addressing.managed_ip_ipv4.all.return_value = NETWORKS_FIXTURE
    ipfabric_client.technology.platforms.stacks_members.all.return_value = STACKS_FIXTURE
    ipfabric_client.technology.interfaces.connectivity_matrix.all.return_value = CONNECTIVITY_MATRIX_FIXTURE
    return ipfabric_client


class IPFabricDiffSyncTestCase(TestCase):
    """Test the IPFabricDiffSync adapter class."""

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def setUp(self):
        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        self.ipfabric = IPFabricDiffSync(job=job, sync=None, client=mock_ipfabric_client(), location_filter=None)
        self.ipfabric.load()

    def test_data_loading(self):
        """Test the load() function."""
        self.assertEqual(
            {site["siteName"] for site in SITE_FIXTURE},
            {site.get_unique_id() for site in self.ipfabric.get_all("location")},
        )
        self.assertEqual(
            {dev["hostname"] for dev in DEVICE_INVENTORY_FIXTURE if dev["siteName"] != "stack"},
            {dev.get_unique_id() for dev in self.ipfabric.get_all("device") if dev.location_name != "stack"},
        )
        self.assertEqual(
            {f"{vlan['vlanName']}__{vlan['siteName']}" for vlan in VLAN_FIXTURE if "badvlan" not in vlan["vlanName"]},
            {vlan.get_unique_id() for vlan in self.ipfabric.get_all("vlan")},
        )

        # Assert invalid VLANs were not loaded
        all_vlans = {vlan.get_unique_id() for vlan in self.ipfabric.get_all("vlan")}
        self.assertEqual(len(all_vlans), 13)
        self.assertNotIn("badvlan0001__JCY-SPINE-01.INFRA.NTC.COM_1", all_vlans)
        self.assertNotIn("badvlan0002__JCY-SPINE-01.INFRA.NTC.COM_1", all_vlans)

        # Assert each site has a device tied to it.
        for site in self.ipfabric.get_all("location"):
            if site.name != "stack":
                self.assertEqual(len(site.devices), 1, f"{site} does not have the expected single device tied to it.")
                self.assertTrue(hasattr(site, "vlans"))

        # Assert each device has the necessary attributes
        for device in self.ipfabric.get_all("device"):
            self.assertTrue(hasattr(device, "location_name"))
            self.assertTrue(hasattr(device, "model"))
            self.assertTrue(hasattr(device, "vendor"))
            self.assertTrue(hasattr(device, "serial_number"))
            self.assertTrue(hasattr(device, "interfaces"))
            self.assertTrue(hasattr(device, "platform"))
            self.assertTrue(hasattr(device, "mgmt_address"))

        # Assert each vlan has the necessary attributes
        for vlan in self.ipfabric.get_all("vlan"):
            self.assertTrue(hasattr(vlan, "name"))
            self.assertTrue(hasattr(vlan, "vid"))
            self.assertTrue(hasattr(vlan, "status"))
            self.assertTrue(hasattr(vlan, "location"))
            self.assertTrue(hasattr(vlan, "description"))

        # Assert each interface has the necessary attributes
        interface_names = set()
        for interface in self.ipfabric.get_all("interface"):
            self.assertTrue(hasattr(interface, "name"))
            self.assertTrue(hasattr(interface, "device_name"))
            self.assertTrue(hasattr(interface, "mac_address"))
            self.assertTrue(hasattr(interface, "mtu"))
            self.assertTrue(hasattr(interface, "ip_address"))
            self.assertTrue(hasattr(interface, "subnet_mask"))
            self.assertTrue(hasattr(interface, "type"))
            # Test network not in NETWORKS_FIXTURE uses default of /32
            if interface.name in ["pseudo_mgmt", "Ethernet1"]:
                self.assertEqual(interface.subnet_mask, "255.255.255.255")
            # Test mask from NETWORKS_FIXTURE is used
            elif interface.name == "GigabitEthernet4":
                self.assertEqual(interface.subnet_mask, "255.255.255.0")
            interface_names.add(interface.name)

        # Test that subnet masks tests were ran
        self.assertTrue("pseudo_mgmt" in interface_names)
        self.assertTrue("GigabitEthernet4" in interface_names)

    def test_data_loading_elongate_interface_names(self):
        """Test the load() function with using long form interface names."""
        # Validate long interface names were created by not raising an exception
        # when performing `DiffSync.get()`
        self.ipfabric.get("interface", {"name": "ipip", "device_name": "nyc-rtr-01"})
        self.ipfabric.get("interface", {"name": "Ethernet15", "device_name": "nyc-leaf-01"})
        self.ipfabric.get("interface", {"name": "GigabitEthernet4", "device_name": "jcy-rtr-02"})
        self.ipfabric.get("interface", {"name": "Ethernet1", "device_name": "nyc-rtr-01"})

    def test_data_loading_stacks(self):
        """Test the load() function loads stack switches."""
        stack_members = [dev for dev in self.ipfabric.get_all("device") if dev.location_name == "stack"]
        self.assertEqual(len(stack_members), 3)
        stack = self.ipfabric.get("device", {"name": "stack"})
        self.assertEqual(stack.vc_name, "stack")
        self.assertEqual(stack.vc_position, 1)
        self.assertEqual(stack.vc_priority, 1)
        self.assertEqual(stack.serial_number, "stack1")
        self.assertEqual(stack.model, "ws-3850-a")
        self.assertTrue(stack.vc_master)
        stack = self.ipfabric.get("device", {"name": "stack-member2"})
        self.assertEqual(stack.vc_name, "stack")
        self.assertEqual(stack.vc_position, 2)
        self.assertEqual(stack.vc_priority, 2)
        self.assertEqual(stack.serial_number, "stack2")
        self.assertEqual(stack.model, "ws-3850-a")
        self.assertFalse(stack.vc_master)
        stack = self.ipfabric.get("device", {"name": "stack-member4"})
        self.assertEqual(stack.vc_name, "stack")
        self.assertEqual(stack.vc_position, 4)
        self.assertEqual(stack.vc_priority, 4)
        self.assertEqual(stack.serial_number, "stack4")
        self.assertEqual(stack.model, "ws-3850-b")
        self.assertFalse(stack.vc_master)

    def test_cables_not_loaded_by_default(self):
        """Cables are opt in, so the default scope loads none even when the API returns links."""
        self.assertEqual(self.ipfabric.get_all("cable"), [])


class IPFabricScopeTestCase(TestCase):
    """Test that deselecting an object type keeps it out of the source adapter's load.

    Each assertion has a matching one on the Nautobot adapter. A toggle that gated only one side
    would make every existing record look absent from IP Fabric, which a sync would then delete.
    """

    def _load(self, **kwargs):
        """Load with the named object types selected."""
        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        adapter = IPFabricDiffSync(
            job=job,
            sync=None,
            client=mock_ipfabric_client(),
            location_filter=None,
            scope=SyncScope.from_job_kwargs(kwargs),
        )
        adapter.load()
        return adapter

    def test_interfaces_out_of_scope_loads_none(self):
        adapter = self._load(sync_interfaces=False)

        self.assertEqual(adapter.get_all("interface"), [])
        self.assertNotEqual(adapter.get_all("device"), [], "Devices should still load.")

    def test_vlans_out_of_scope_loads_none(self):
        adapter = self._load(sync_vlans=False)

        self.assertEqual(adapter.get_all("vlan"), [])
        self.assertNotEqual(adapter.get_all("device"), [], "Devices should still load.")

    def test_ip_addresses_out_of_scope_reports_no_address(self):
        """Every loaded Interface reports no address, rather than the Interfaces being skipped."""
        adapter = self._load(sync_ip_addresses=False)

        interfaces = adapter.get_all("interface")
        self.assertNotEqual(interfaces, [])
        for interface in interfaces:
            self.assertIsNone(interface.ip_address, interface.name)
            self.assertIsNone(interface.subnet_mask, interface.name)
            self.assertFalse(interface.ip_is_primary, interface.name)

    def test_ip_addresses_out_of_scope_drops_the_pseudo_interface(self):
        """The pseudo interface exists only to carry a NAT address, so it has no reason to load."""
        adapter = self._load(sync_ip_addresses=False)

        self.assertNotIn("pseudo_mgmt", {interface.name for interface in adapter.get_all("interface")})

    def test_primary_ip_out_of_scope_keeps_the_addresses(self):
        """Only the primary assignment is withheld; the addresses themselves are still synced."""
        adapter = self._load(sync_primary_ip=False)

        interfaces = adapter.get_all("interface")
        self.assertTrue(any(interface.ip_address for interface in interfaces), "Addresses should still load.")
        for interface in interfaces:
            self.assertFalse(interface.ip_is_primary, interface.name)

    def test_cables_require_interfaces(self):
        """Selecting Cables without Interfaces cannot work, so the scope drops it rather than failing."""
        adapter = self._load(sync_interfaces=False, sync_cables=True)

        self.assertEqual(adapter.get_all("cable"), [])


class IPFabricDiffSyncCableTestCase(TestCase):
    """Test loading the IP Fabric connectivity matrix as Cable models."""

    # Extra cableable ends, since the shared interface fixture only has enough for one link.
    EXTRA_INTERFACES = [
        {"hostname": "nyc-leaf-01", "sn": "5254.0029.fbf2", "intName": "Et20", "media": None, "mtu": 9214},
        {"hostname": "nyc-spine-02", "sn": "5254.00d3.a91d", "intName": "Et5", "media": None, "mtu": 9214},
    ]

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def setUp(self):
        client = mock_ipfabric_client()
        client.inventory.interfaces.all.return_value = INTERFACE_FIXTURE + self.EXTRA_INTERFACES
        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        self.ipfabric = IPFabricDiffSync(
            job=job,
            sync=None,
            client=client,
            location_filter=None,
            scope=SyncScope.from_job_kwargs({"sync_cables": True}),
        )
        self.ipfabric.load()

    def test_only_cableable_links_in_scope_are_synced(self):
        """Links are skipped unless both endpoints were loaded and are of a cableable Interface type."""
        self.assertEqual(
            {
                # Endpoints are ordered by (device, interface), not by IP Fabric's local/remote side.
                "nyc-leaf-01__Ethernet15__nyc-rtr-01__Ethernet1",
                "nyc-leaf-01__Ethernet20__nyc-spine-02__Ethernet5",
            },
            {cable.get_unique_id() for cable in self.ipfabric.get_all("cable")},
        )

    def test_links_to_virtual_interfaces_are_skipped(self):
        """Nautobot refuses to cable virtual Interfaces, so such links are dropped before syncing."""
        # jcy-rtr-02's Gi4 has a media type of "Virtual" in the interface fixture.
        self.assertEqual(
            self.ipfabric.get("interface", {"name": "GigabitEthernet4", "device_name": "jcy-rtr-02"}).type,
            "virtual",
        )
        reported = [
            entry
            for entry in CONNECTIVITY_MATRIX_FIXTURE
            if {entry["localHost"], entry["remoteHost"]} == {"nyc-rtr-01", "jcy-rtr-02"}
        ]
        self.assertEqual(len(reported), 1, "Fixture should report a link onto the virtual interface.")
        self.assertFalse(
            any(
                "jcy-rtr-02" in (cable.termination_a_device, cable.termination_b_device)
                for cable in self.ipfabric.get_all("cable")
            )
        )

    def test_endpoints_are_cableable_rejects_unloaded_interface(self):
        """An endpoint with no matching loaded Interface is not cableable."""
        self.assertFalse(self.ipfabric.endpoints_are_cableable(("nyc-rtr-01", "Ethernet99")))
        self.assertTrue(self.ipfabric.endpoints_are_cableable(("nyc-rtr-01", "Ethernet1")))

    def test_bidirectional_entries_load_a_single_cable(self):
        """The connectivity matrix reports each link twice, which must not become two Cables."""
        reported_both_ways = [
            entry
            for entry in CONNECTIVITY_MATRIX_FIXTURE
            if {entry["localHost"], entry["remoteHost"]} == {"nyc-rtr-01", "nyc-leaf-01"}
            and {entry["localInt"], entry["remoteInt"]} == {"eth1", "Et15"}
        ]
        self.assertEqual(len(reported_both_ways), 2, "Fixture should report this link from both devices.")
        matching = [
            cable
            for cable in self.ipfabric.get_all("cable")
            if {
                (cable.termination_a_device, cable.termination_a_name),
                (cable.termination_b_device, cable.termination_b_name),
            }
            == {("nyc-rtr-01", "Ethernet1"), ("nyc-leaf-01", "Ethernet15")}
        ]
        self.assertEqual(len(matching), 1)

    def test_cable_attributes(self):
        """Loaded Cables carry the configured default Status."""
        for cable in self.ipfabric.get_all("cable"):
            self.assertEqual(cable.status, "Connected")

    def test_link_endpoint_canonicalizes_interface_name(self):
        """`link_endpoint` applies the canonical interface name setting to the raw API value."""
        entry = {"localHost": "nyc-rtr-01", "localInt": "Gi0/1"}
        with patch(
            "nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME",
            True,
        ):
            self.assertEqual(self.ipfabric.link_endpoint(entry, "local"), ("nyc-rtr-01", "GigabitEthernet0/1"))
        with patch(
            "nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME",
            False,
        ):
            self.assertEqual(self.ipfabric.link_endpoint(entry, "local"), ("nyc-rtr-01", "Gi0/1"))

    def test_link_endpoint_returns_none_when_incomplete(self):
        """An entry missing either the host or the interface for a side yields no endpoint."""
        self.assertIsNone(self.ipfabric.link_endpoint({"localHost": "nyc-rtr-01", "localInt": None}, "local"))
        self.assertIsNone(self.ipfabric.link_endpoint({"localHost": None, "localInt": "eth1"}, "local"))
        self.assertIsNone(self.ipfabric.link_endpoint({}, "remote"))
