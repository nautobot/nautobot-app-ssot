"""Unit tests for the IPFabric DiffSync adapter class."""

import ipaddress
import json
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ipfabric.models.device import Device
from nautobot.apps.testing import TestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import (
    IPFabricDiffSync,
    containing_prefix_length,
    host_route_length,
    prefix_lengths_by_address,
    primary_addresses_of,
)
from nautobot_ssot.integrations.ipfabric.jobs import IpFabricDataSource
from nautobot_ssot.integrations.ipfabric.strict_mode import StrictObjects
from nautobot_ssot.integrations.ipfabric.sync_scope import (
    UNSYNCED_LOCATION_ATTRS,
    UNSYNCED_LOCATION_FLAGS,
    SyncScope,
)
from nautobot_ssot.tests.ipfabric.supporting_objects import addresses_of


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


SITE_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_sites.json")
DEVICE_INVENTORY_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_device_inventory.json")
VLAN_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_vlans.json")
INTERFACE_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_interface_inventory.json")
# `intName` is what attaches an address to its Interface; IP Fabric returns it as a column.
NETWORKS_FIXTURE = [{"net": "10.10.0.0/24", "sn": "a000a02", "ip": "10.10.0.10", "intName": "Gi4"}]
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
    # Stubbed empty rather than left as mocks, so a test that means to exercise them has to say so.
    ipfabric_client.technology.addressing.managed_ip_ipv6.all.return_value = []
    ipfabric_client.technology.fhrp.group_members.all.return_value = []
    ipfabric_client.technology.platforms.stacks_members.all.return_value = STACKS_FIXTURE
    ipfabric_client.technology.interfaces.connectivity_matrix.all.return_value = CONNECTIVITY_MATRIX_FIXTURE
    return ipfabric_client


def build_adapter(client=None, logger=None, strict=("ip_addresses",), **scope_kwargs):
    """Return a loaded IPFabricDiffSync over the JSON fixtures, scoped by `scope_kwargs`.

    `strict` names the object types the run may not create, defaulting to the form's own default.
    """
    job = IpFabricDataSource()
    job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
    if logger is not None:
        job.logger = logger
    adapter = IPFabricDiffSync(
        job=job,
        sync=None,
        client=client if client is not None else mock_ipfabric_client(),
        location_filter=None,
        scope=SyncScope.from_job_kwargs(scope_kwargs),
        strict=StrictObjects(strict),
    )
    adapter.load()
    return adapter


class IPFabricDiffSyncTestCase(TestCase):
    """Test the IPFabricDiffSync adapter class."""

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def setUp(self):
        self.ipfabric = build_adapter()

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
            self.assertTrue(hasattr(interface, "type"))
            loaded = addresses_of(self.ipfabric, interface.device_name, interface.name)
            # A NAT management address belongs to no subnet, so a host route is the whole of it
            if interface.name == "pseudo_mgmt":
                self.assertEqual(list(loaded.values()), [32], f"{interface.device_name}: {loaded}")
            # The length from NETWORKS_FIXTURE is used
            elif interface.name == "GigabitEthernet4":
                self.assertEqual(loaded, {"10.10.0.10": 24})
            # A network not in NETWORKS_FIXTURE reports no address rather than a host route
            elif interface.name == "Ethernet1":
                self.assertEqual(loaded, {})
            interface_names.add(interface.name)

        # Test that subnet masks tests were ran
        self.assertTrue("pseudo_mgmt" in interface_names)
        self.assertTrue("GigabitEthernet4" in interface_names)
        self.assertTrue("Ethernet1" in interface_names)

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
        return build_adapter(**kwargs)

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

        self.assertNotEqual(adapter.get_all("interface"), [])
        self.assertEqual(adapter.get_all("interface_address"), [])

    def test_ip_addresses_out_of_scope_drops_the_pseudo_interface(self):
        """The pseudo interface exists only to carry a NAT address, so it has no reason to load."""
        adapter = self._load(sync_ip_addresses=False)

        self.assertNotIn("pseudo_mgmt", {interface.name for interface in adapter.get_all("interface")})

    def test_primary_ip_out_of_scope_keeps_the_addresses(self):
        """Only the primary assignment is withheld; the addresses themselves are still synced."""
        adapter = self._load(sync_primary_ip=False)

        addresses = adapter.get_all("interface_address")
        self.assertNotEqual(addresses, [], "Addresses should still load.")
        for address in addresses:
            self.assertFalse(address.is_primary, address.host)

    def test_locations_out_of_scope_are_still_loaded_as_tree_nodes(self):
        """Locations keep being read, since Devices hang off them, but carry no writable attributes."""
        adapter = self._load(sync_locations=False)

        locations = adapter.get_all("location")
        self.assertNotEqual(locations, [])
        for location in locations:
            self.assertEqual(location.site_id, UNSYNCED_LOCATION_ATTRS["site_id"], location.name)
            self.assertEqual(location.status, UNSYNCED_LOCATION_ATTRS["status"], location.name)
            self.assertTrue(location.model_flags & UNSYNCED_LOCATION_FLAGS, location.name)
        self.assertNotEqual(adapter.get_all("device"), [], "Devices should still load.")

    def test_locations_in_scope_carry_the_ip_fabric_site_id(self):
        """The default: the site ID is loaded, so it can be written to the Location custom field."""
        adapter = self._load()

        for location in adapter.get_all("location"):
            self.assertEqual(location.status, "Active", location.name)
            self.assertFalse(location.model_flags & UNSYNCED_LOCATION_FLAGS, location.name)
        self.assertTrue(any(location.site_id for location in adapter.get_all("location")))

    def test_out_of_scope_tables_are_not_fetched(self):
        """The tables are the largest requests the job makes, so a narrowed run must not ask for them."""
        client = mock_ipfabric_client()
        build_adapter(client=client, sync_interfaces=False, sync_vlans=False)

        client.inventory.interfaces.all.assert_not_called()
        client.fetch_all.assert_not_called()
        client.technology.addressing.managed_ip_ipv4.all.assert_not_called()
        client.technology.platforms.stacks_members.all.assert_called_once()

    def test_in_scope_tables_are_fetched(self):
        """The counterpart, so the guards cannot silently starve a default run."""
        client = mock_ipfabric_client()
        build_adapter(client=client)

        client.inventory.interfaces.all.assert_called_once()
        client.technology.addressing.managed_ip_ipv4.all.assert_called_once()
        client.fetch_all.assert_called_once_with("tables/vlan/site-summary")

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
        self.ipfabric = build_adapter(client=client, sync_cables=True)

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


class IPFabricDiffSyncSharedEndpointTestCase(TestCase):
    """Test a topology Nautobot's one Cable per Interface rule cannot hold.

    IP Fabric describes a cloud subnet as a link from every Interface in it to the subnet, so the
    subnet's own Interface is reported on as many links as the subnet has members.
    """

    EXTRA_INTERFACES = [
        {"hostname": "nyc-leaf-01", "sn": "5254.0029.fbf2", "intName": "Et20", "media": None, "mtu": 9214},
    ] + [
        {"hostname": "nyc-spine-02", "sn": "5254.00d3.a91d", "intName": peer, "media": None, "mtu": 9214}
        for peer in ("Et5", "Et6", "Et7")
    ]

    FAN_OUT = [
        {
            "localHost": "nyc-leaf-01",
            "localInt": "Et20",
            "localSn": "5254.0029.fbf2",
            "localMedia": "10GBase-SR",
            "protocol": "lldp",
            "remoteHost": "nyc-spine-02",
            "remoteInt": peer,
            "remoteSn": "5254.00d3.a91d",
            "remoteMedia": "10GBase-SR",
            "siteName": "NYC-LEAF-01",
        }
        for peer in ("Et5", "Et6", "Et7")
    ]

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def setUp(self):
        client = mock_ipfabric_client()
        client.inventory.interfaces.all.return_value = INTERFACE_FIXTURE + self.EXTRA_INTERFACES
        client.technology.interfaces.connectivity_matrix.all.return_value = self.FAN_OUT
        self.ipfabric = build_adapter(client=client, sync_cables=True)

    def test_a_shared_interface_yields_one_cable(self):
        self.assertEqual(len(self.ipfabric.get_all("cable")), 1)

    def test_the_link_kept_is_the_lowest_sorting_one(self):
        """Deterministic, so a re-sync settles rather than replacing the Cable the last run made."""
        cable = self.ipfabric.get_all("cable")[0]
        self.assertEqual(
            {
                (cable.termination_a_device, cable.termination_a_name),
                (cable.termination_b_device, cable.termination_b_name),
            },
            {("nyc-leaf-01", "Ethernet20"), ("nyc-spine-02", "Ethernet5")},
        )

    def test_the_same_link_is_kept_on_every_run(self):
        self.assertEqual(self.ipfabric.recordable_links(), self.ipfabric.recordable_links())

    def test_the_links_that_cannot_be_recorded_are_reported(self):
        """An operator seeing fewer Cables than IP Fabric reports needs to be told why."""
        with self.assertLogs("nautobot.jobs", level="WARNING") as logs:
            self.ipfabric.recordable_links()

        logged = " ".join(logs.output)
        self.assertIn("nyc-leaf-01:Ethernet20", logged)
        self.assertIn("2 further link", logged)


class PrefixLengthChoiceTestCase(TestCase):
    """Test choosing one prefix length for an address IP Fabric reports in more than one subnet."""

    # The address table as the adapter passes it on: a flat list of records, whichever device or
    # table each came from.
    CONTESTED = [
        {"ip": "10.0.0.1", "net": "10.0.0.0/24"},
        {"ip": "10.0.0.1", "net": "10.0.0.0/25"},
    ]

    def test_the_narrowest_reported_subnet_is_chosen(self):
        """Nautobot parents an address to the most specific Prefix containing it, so this agrees."""
        self.assertEqual(prefix_lengths_by_address(self.CONTESTED)["10.0.0.1"], 25)

    def test_the_choice_does_not_follow_the_order_reported(self):
        """IP Fabric's order is not guaranteed, and a choice that followed it would flip each run."""
        self.assertEqual(
            prefix_lengths_by_address(self.CONTESTED),
            prefix_lengths_by_address(list(reversed(self.CONTESTED))),
        )

    def test_an_address_reported_in_two_subnets_is_named(self):
        """One Interface will carry a mask it was not reported with, so the operator is told which."""
        with self.assertLogs("nautobot.jobs", level="WARNING") as logs:
            prefix_lengths_by_address(self.CONTESTED)

        self.assertIn("10.0.0.1", " ".join(logs.output))

    def test_one_device_reporting_two_subnets_is_named_too(self):
        """Folded per record rather than per device, so a device disagreeing with itself is seen."""
        reported = [
            {"sn": "sn-a", "ip": "10.0.0.1", "net": "10.0.0.0/24"},
            {"sn": "sn-a", "ip": "10.0.0.1", "net": "10.0.0.0/25"},
        ]

        with self.assertLogs("nautobot.jobs", level="WARNING") as logs:
            chosen = prefix_lengths_by_address(reported)

        self.assertEqual(chosen["10.0.0.1"], 25)
        self.assertIn("10.0.0.1", " ".join(logs.output))

    def test_an_address_reported_once_is_left_as_reported(self):
        self.assertEqual(prefix_lengths_by_address(self.CONTESTED[:1])["10.0.0.1"], 24)

    def test_a_record_without_a_subnet_is_skipped(self):
        self.assertEqual(prefix_lengths_by_address([{"ip": "10.0.0.9", "net": None}]), {})

    def test_a_record_without_an_address_is_skipped(self):
        """The column can come back empty for a row IP Fabric still returns."""
        self.assertEqual(prefix_lengths_by_address([{"ip": None, "net": "10.0.0.0/24"}]), {})

    def test_a_subnet_that_does_not_parse_is_skipped(self):
        """One unusable row must not end the load, which would lose every address that was fine."""
        reported = [
            {"ip": "10.0.0.9", "net": "not-a-subnet"},
            {"ip": "10.0.0.10", "net": "10.0.0.0/24"},
        ]

        with self.assertLogs("nautobot.jobs", level="WARNING") as logs:
            chosen = prefix_lengths_by_address(reported)

        self.assertEqual(chosen, {"10.0.0.10": 24})
        self.assertIn("not-a-subnet", " ".join(logs.output))

    def test_an_ipv6_subnet_is_usable(self):
        """A length serves either version, which is what lets a v6 address be synced at all."""
        self.assertEqual(
            prefix_lengths_by_address([{"ip": "2001:db8::1", "net": "2001:db8::/64"}]),
            {"2001:db8::1": 64},
        )

    def test_the_narrowest_choice_ignores_an_unusable_report(self):
        """A bad row must not win the comparison, nor make a good address look contested."""
        reported = [
            {"ip": "10.0.0.1", "net": "10.0.0.0/24"},
            {"ip": "10.0.0.1", "net": "garbage"},
        ]

        self.assertEqual(prefix_lengths_by_address(reported), {"10.0.0.1": 24})


# Pinned rather than left to the deployed setting, so the Interface names asserted below do not
# depend on whether canonical naming happens to be enabled where the suite runs.
@patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
class StrictInterfacesTestCase(TestCase):
    """Test withholding the Interface the adapter invents for a NAT management address.

    `nyc-rtr-01` has a login IP matching none of its reported Interfaces, so an unstrict run
    fabricates `pseudo_mgmt` to carry it.
    """

    def test_the_placeholder_is_not_invented_when_strict(self):
        adapter = build_adapter(strict=("interfaces",))

        self.assertNotIn("pseudo_mgmt", {interface.name for interface in adapter.get_all("interface")})

    def test_the_placeholder_is_invented_when_not_strict(self):
        """The behaviour every existing install keeps, since the entry defaults to unselected."""
        adapter = build_adapter(strict=())

        self.assertIn("pseudo_mgmt", {interface.name for interface in adapter.get_all("interface")})

    def test_the_interfaces_ip_fabric_reported_still_load(self):
        """Only the invented Interface is withheld; strictness does not stop Interfaces syncing."""
        adapter = build_adapter(strict=("interfaces",))

        loaded = {interface.name for interface in adapter.get_all("interface")}
        self.assertIn("Ethernet1", loaded)
        self.assertIn("GigabitEthernet4", loaded)

    def test_the_management_address_goes_unsynced_with_the_placeholder(self):
        """The address had no Interface of its own, so withholding the Interface withholds it."""
        adapter = build_adapter(strict=("interfaces",))

        addresses = {address.host for address in adapter.get_all("interface_address")}
        self.assertNotIn("172.18.0.14", addresses)


class UnresolvableSubnetMaskTestCase(TestCase):
    """Test what the adapter reports for an address IP Fabric gives no subnet for.

    `NETWORKS_FIXTURE` covers 10.10.0.10 only, so the address on `eth1`, loaded here under its
    canonical name `Ethernet1`, has no reported subnet.
    """

    def setUp(self):
        # Pinned rather than left to the deployed setting, since the Interface names the register
        # holds are the canonical ones the diff matches on.
        canonical_names = patch(
            "nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME",
            True,
        )
        canonical_names.start()
        self.addCleanup(canonical_names.stop)
        self.ipfabric = build_adapter()

    def test_the_interface_is_recorded_as_having_no_subnet(self):
        self.assertIn(("nyc-rtr-01", "Ethernet1", "10.10.0.11"), self.ipfabric.addresses_without_a_subnet)

    def test_an_interface_with_a_reported_subnet_is_not_recorded(self):
        self.assertNotIn(("jcy-rtr-02", "GigabitEthernet4", "10.10.0.10"), self.ipfabric.addresses_without_a_subnet)

    def test_a_nat_management_address_is_not_recorded(self):
        """A NAT address belongs to no subnet, so a host mask is the whole of it, not a fallback."""
        self.assertEqual(addresses_of(self.ipfabric, "nyc-rtr-01", "pseudo_mgmt"), {"172.18.0.14": 32})
        self.assertNotIn(("nyc-rtr-01", "pseudo_mgmt", "172.18.0.14"), self.ipfabric.addresses_without_a_subnet)

    def test_the_interface_still_loads_without_its_address(self):
        self.ipfabric.get("interface", {"name": "Ethernet1", "device_name": "nyc-rtr-01"})

        self.assertEqual(addresses_of(self.ipfabric, "nyc-rtr-01", "Ethernet1"), {})

    def test_an_interface_with_a_reported_subnet_keeps_its_address(self):
        self.assertEqual(addresses_of(self.ipfabric, "jcy-rtr-02", "GigabitEthernet4"), {"10.10.0.10": 24})

    def test_the_count_is_reported_as_a_warning(self):
        adapter = build_adapter(logger=MagicMock())

        self.assertTrue(
            any("Not syncing" in str(call) for call in adapter.job.logger.warning.call_args_list),
            adapter.job.logger.warning.call_args_list,
        )

    def test_an_unusable_subnet_is_treated_as_no_subnet(self):
        """The check is that a usable subnet was reported, not merely that a value was present."""
        client = mock_ipfabric_client()
        client.technology.addressing.managed_ip_ipv4.all.return_value = [
            {"net": "not-a-subnet", "sn": "VM60D5EE2211", "ip": "10.10.0.11"}
        ]
        adapter = build_adapter(client=client)

        self.assertIn(("nyc-rtr-01", "Ethernet1", "10.10.0.11"), adapter.addresses_without_a_subnet)

    def test_the_fallback_applies_a_host_mask_when_strictness_is_off(self):
        adapter = build_adapter(logger=MagicMock(), strict=())

        self.assertEqual(addresses_of(adapter, "nyc-rtr-01", "Ethernet1"), {"10.10.0.11": 32})
        self.assertEqual(adapter.addresses_without_a_subnet, set())

    def test_every_use_of_the_fallback_is_reported_as_a_warning(self):
        """The address has to be named, since a `/32` written for it is the wrong value."""
        adapter = build_adapter(logger=MagicMock(), strict=())

        warnings = " ".join(str(call) for call in adapter.job.logger.warning.call_args_list)
        self.assertIn("10.10.0.11", warnings)
        self.assertIn("host route", warnings)

    def test_nothing_is_reported_when_every_address_has_a_subnet(self):
        client = mock_ipfabric_client()
        client.technology.addressing.managed_ip_ipv4.all.return_value = [
            {"net": f"{interface['primaryIp']}/24", "sn": interface["sn"], "ip": interface["primaryIp"]}
            for interface in INTERFACE_FIXTURE
            if interface.get("primaryIp")
        ]
        adapter = build_adapter(client=client, logger=MagicMock())

        self.assertEqual(adapter.addresses_without_a_subnet, set())
        self.assertFalse(
            any("Not syncing" in str(call) for call in adapter.job.logger.warning.call_args_list),
            adapter.job.logger.warning.call_args_list,
        )


# `Gi4` on `jcy-rtr-02` is the Interface the address fixtures attach to; it loads under its canonical
# name because these classes pin canonical naming on.
@patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
class SeveralAddressesPerInterfaceTestCase(TestCase):
    """Test the three sources an Interface's addresses come from."""

    SERIAL = "a000a02"
    DEVICE = "jcy-rtr-02"
    INTERFACE = "GigabitEthernet4"

    def setUp(self):
        # The default estate for this class: one managed address on the Interface under test. A test
        # needing a different set re-calls `managed`.
        self.client = self.managed(self.row("10.10.0.10", "10.10.0.0/24"))

    def managed(self, *rows):
        """Point this test's client at the given managed IPv4 rows, and return it."""
        self.client = mock_ipfabric_client()
        self.client.technology.addressing.managed_ip_ipv4.all.return_value = list(rows)
        return self.client

    def row(self, ip, net):
        """Return one managed address row for this test's Interface."""
        return {"sn": self.SERIAL, "intName": "Gi4", "ip": ip, "net": net}

    def fhrp(self, **columns):
        """Serve one FHRP group member for this test's Interface, carrying the given columns."""
        self.client.technology.fhrp.group_members.all.return_value = [
            {"sn": self.SERIAL, "hostname": self.DEVICE, "intName": "Gi4", **columns}
        ]

    def test_a_secondary_address_is_synced_alongside_the_primary(self):
        """The `type eq primary` filter is gone, so a second address on the Interface is synced too.

        The column itself is not requested, so the sync does not distinguish a secondary address
        from a primary one; it carries both.
        """
        self.managed(
            self.row("10.10.0.10", "10.10.0.0/24"),
            self.row("10.10.1.10", "10.10.1.0/24"),
        )

        adapter = build_adapter(client=self.client)

        self.assertEqual(
            addresses_of(adapter, self.DEVICE, self.INTERFACE),
            {"10.10.0.10": 24, "10.10.1.10": 24},
        )

    def test_the_address_table_is_read_without_a_type_filter(self):
        """Asked of the client itself, since a filter would drop the rows before they are seen."""
        self.managed(self.row("10.10.0.10", "10.10.0.0/24"))

        build_adapter(client=self.client)

        for call in self.client.technology.addressing.managed_ip_ipv4.all.call_args_list:
            self.assertNotIn("filters", call.kwargs, "The primary-only filter is back.")

    def test_an_ipv6_address_is_synced_alongside_ipv4(self):
        """A dual stack Interface is unmodelled without this, whatever its v4 address says."""
        self.client.technology.addressing.managed_ip_ipv6.all.return_value = [
            {"sn": self.SERIAL, "intName": "Gi4", "ip": "2001:db8::10", "net": "2001:db8::/64"}
        ]

        adapter = build_adapter(client=self.client)

        self.assertEqual(
            addresses_of(adapter, self.DEVICE, self.INTERFACE),
            {"10.10.0.10": 24, "2001:db8::10": 64},
        )

    def test_an_fhrp_virtual_address_is_synced(self):
        """A virtual address renders into the device's configuration, so Nautobot needs it."""
        self.fhrp(vip="10.10.0.1")

        adapter = build_adapter(client=self.client)

        loaded = addresses_of(adapter, self.DEVICE, self.INTERFACE)
        self.assertEqual(
            loaded.get("10.10.0.1"), 24, f"The virtual address should sit in the Interface's subnet: {loaded}"
        )

    def test_an_fhrp_row_with_no_recognisable_virtual_address_is_reported(self):
        """The column differs between releases, so a miss is named rather than passed over."""
        self.fhrp(somethingElse="10.10.0.1")

        adapter = build_adapter(client=self.client, logger=MagicMock())

        reported = " ".join(str(call) for call in adapter.job.logger.warning.call_args_list)
        self.assertIn("FHRP", reported)
        self.assertEqual(addresses_of(adapter, self.DEVICE, self.INTERFACE), {"10.10.0.10": 24})

    def test_an_address_reported_by_two_sources_is_loaded_once(self):
        """A virtual address configured on the interface appears in both tables."""
        # The second row is the Interface's own address, so the record built from the Interface
        # record adds nothing.
        self.managed(self.row("10.10.0.1", "10.10.0.0/24"), self.row("10.10.0.10", "10.10.0.0/24"))
        self.fhrp(vip="10.10.0.1")

        adapter = build_adapter(client=self.client)

        self.assertEqual(addresses_of(adapter, self.DEVICE, self.INTERFACE), {"10.10.0.1": 24, "10.10.0.10": 24})

    def test_an_address_the_table_does_not_cover_does_not_inherit_a_sibling_subnet(self):
        """Only a record with no subnet of its own inherits one.

        For a managed address the table simply did not cover, the subnet is missing data, and
        inferring it from a sibling would write the address under a parent IP Fabric never reported.
        """
        self.managed(self.row("10.10.0.10", "10.10.0.0/24"), self.row("10.10.0.99", None))

        adapter = build_adapter(client=self.client)

        self.assertEqual(addresses_of(adapter, self.DEVICE, self.INTERFACE), {"10.10.0.10": 24})
        self.assertIn((self.DEVICE, self.INTERFACE, "10.10.0.99"), adapter.addresses_without_a_subnet)

    def test_an_fhrp_address_no_reported_subnet_covers_is_withheld(self):
        """Written under a guessed mask it would land under the wrong parent Prefix.

        Withheld through the same register as any other address with no usable subnet, so it is
        counted in the summary and reported at debug rather than once per Interface.
        """
        self.fhrp(vip="192.0.2.1")

        adapter = build_adapter(client=self.client, logger=MagicMock())

        self.assertEqual(addresses_of(adapter, self.DEVICE, self.INTERFACE), {"10.10.0.10": 24})
        self.assertIn((self.DEVICE, self.INTERFACE, "192.0.2.1"), adapter.addresses_without_a_subnet)

    def test_a_duplicate_interface_is_reported_and_loads_no_addresses(self):
        """The first record already carries the addresses, so the second must not add them twice."""
        self.managed(self.row("10.10.0.10", "10.10.0.0/24"))
        duplicated = [record for record in INTERFACE_FIXTURE if record["intName"] == "Gi4"]
        self.client.inventory.interfaces.all.return_value = INTERFACE_FIXTURE + duplicated

        with self.assertLogs("nautobot.jobs", level="WARNING") as logs:
            adapter = build_adapter(client=self.client)

        self.assertIn("Duplicate Interface discovered", " ".join(logs.output))
        self.assertEqual(addresses_of(adapter, self.DEVICE, self.INTERFACE), {"10.10.0.10": 24})

    def test_a_row_with_no_address_is_passed_over(self):
        """The column can come back empty for a row IP Fabric still returns."""
        self.managed(self.row("10.10.0.10", "10.10.0.0/24"), self.row(None, "10.10.2.0/24"))

        adapter = build_adapter(client=self.client)

        self.assertEqual(addresses_of(adapter, self.DEVICE, self.INTERFACE), {"10.10.0.10": 24})


class AddressLengthHelperTestCase(TestCase):
    """Test the two helpers that turn a reported value into a prefix length."""

    def test_a_host_route_covers_only_the_address(self):
        self.assertEqual(host_route_length("10.0.0.1"), 32)
        self.assertEqual(host_route_length("2001:db8::1"), 128)

    def test_a_host_route_for_an_unparseable_address_falls_back_to_ipv4(self):
        """Reached only for a value that got past the address table, so it must not raise."""
        self.assertEqual(host_route_length("not-an-address"), 32)

    def test_a_subnet_containing_the_address_is_found(self):
        self.assertEqual(containing_prefix_length("10.0.0.9", {"10.0.0.1": 24}), 24)

    def test_the_narrowest_containing_subnet_wins(self):
        """Nautobot parents an address to the most specific Prefix containing it."""
        self.assertEqual(containing_prefix_length("10.0.0.9", {"10.0.0.1": 24, "10.0.0.2": 25}), 25)

    def test_a_subnet_that_does_not_contain_the_address_is_ignored(self):
        self.assertIsNone(containing_prefix_length("192.0.2.1", {"10.0.0.1": 24}))

    def test_an_address_of_another_version_is_ignored(self):
        """A v6 address is not in a v4 subnet however the numbers compare."""
        self.assertIsNone(containing_prefix_length("2001:db8::1", {"10.0.0.1": 8}))

    def test_an_unparseable_address_has_no_containing_subnet(self):
        self.assertIsNone(containing_prefix_length("not-an-address", {"10.0.0.1": 24}))

    def test_an_unparseable_sibling_is_ignored(self):
        self.assertIsNone(containing_prefix_length("10.0.0.9", {"garbage": 24}))


class PrimaryAddressTestCase(TestCase):
    """Test which addresses a Device is logged in on, and so which Nautobot records as primary."""

    @staticmethod
    def device(**fields):
        """Return a stand-in for the SDK Device, carrying only the login columns."""
        return SimpleNamespace(**{"login_ipv4": None, "login_ipv6": None, "login_ip": None, **fields})

    def test_both_login_versions_are_reported(self):
        """A dual stack Device names one of each, so Nautobot can carry a primary of each."""
        device = self.device(
            login_ipv4=ipaddress.ip_address("10.0.0.5"), login_ipv6=ipaddress.ip_address("2001:db8::5")
        )

        self.assertEqual(primary_addresses_of(device), {"10.0.0.5", "2001:db8::5"})

    def test_one_version_alone_is_reported(self):
        self.assertEqual(primary_addresses_of(self.device(login_ipv4=ipaddress.ip_address("10.0.0.5"))), {"10.0.0.5"})

    def test_the_older_single_column_is_read_when_the_newer_two_are_absent(self):
        """`loginIp` is what a release before the split reports, and carries a prefix length."""
        device = self.device(login_ip=ipaddress.ip_interface("10.0.0.5/24"))

        self.assertEqual(primary_addresses_of(device), {"10.0.0.5"})

    def test_the_newer_columns_win_over_the_older_one(self):
        device = self.device(
            login_ipv4=ipaddress.ip_address("10.0.0.5"), login_ip=ipaddress.ip_interface("192.0.2.1/24")
        )

        self.assertEqual(primary_addresses_of(device), {"10.0.0.5"})

    def test_a_device_with_no_login_address_reports_none(self):
        self.assertEqual(primary_addresses_of(self.device()), set())


@patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
class DualStackPrimaryTestCase(TestCase):
    """Test marking a primary address of each version on the Interface already carrying it."""

    SERIAL = "a000a02"
    DEVICE = "jcy-rtr-02"
    INTERFACE = "GigabitEthernet4"

    def load(self):
        """Load a client whose Interface carries both a v4 and a v6 address, both logged in on."""
        client = mock_ipfabric_client()
        client.technology.addressing.managed_ip_ipv4.all.return_value = [
            {"sn": self.SERIAL, "intName": "Gi4", "ip": "10.10.0.10", "net": "10.10.0.0/24"}
        ]
        client.technology.addressing.managed_ip_ipv6.all.return_value = [
            {"sn": self.SERIAL, "intName": "Gi4", "ip": "2001:db8::10", "net": "2001:db8::/64"}
        ]
        for device in client.devices.by_site["JCY-RTR-02_1"]:  # pylint: disable=no-member
            if device.hostname == self.DEVICE:
                device.login_ipv4 = ipaddress.ip_address("10.10.0.10")
                device.login_ipv6 = ipaddress.ip_address("2001:db8::10")
        return build_adapter(client=client)

    def primaries(self, adapter):
        """Return the hosts marked primary on this test's Interface."""
        return {
            address.host
            for address in adapter.get_all("interface_address")
            if address.interface_name == self.INTERFACE and address.is_primary
        }

    def test_an_address_of_each_version_is_marked_primary(self):
        adapter = self.load()

        self.assertEqual(self.primaries(adapter), {"10.10.0.10", "2001:db8::10"})

    def test_the_marked_addresses_keep_the_length_their_interface_reported(self):
        """Marking one primary resolves no address of its own; the length came from the table."""
        adapter = self.load()

        self.assertEqual(
            addresses_of(adapter, self.DEVICE, self.INTERFACE),
            {"10.10.0.10": 24, "2001:db8::10": 64},
        )
