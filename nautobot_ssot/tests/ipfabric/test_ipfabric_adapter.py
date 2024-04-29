"""Unit tests for the IPFabric DiffSync adapter class."""

import json
from unittest import TestCase
from unittest.mock import MagicMock, patch

from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import IPFabricDiffSync
from nautobot_ssot.integrations.ipfabric.jobs import IpFabricDataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


SITE_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_sites.json")
DEVICE_INVENTORY_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_device_inventory.json")
VLAN_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_vlans.json")
INTERFACE_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_interface_inventory.json")
NETWORKS_FIXTURE = [{"net": "10.255.254.0/23", "siteName": "site1"}, {"net": "172.18.0.0/24", "siteName": "site2"}]
STACKS_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_stack_members.json")


class IPFabricDiffSyncTestCase(TestCase):
    """Test the IPFabricDiffSync adapter class."""

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def setUp(self):
        # Create a mock client
        ipfabric_client = MagicMock()
        ipfabric_client.inventory.sites.all.return_value = SITE_FIXTURE
        ipfabric_client.inventory.devices.all.return_value = DEVICE_INVENTORY_FIXTURE
        ipfabric_client.fetch_all = MagicMock(
            side_effect=(lambda x: VLAN_FIXTURE if x == "tables/vlan/site-summary" else "")
        )
        ipfabric_client.inventory.interfaces.all.return_value = INTERFACE_FIXTURE
        ipfabric_client.technology.managed_networks.networks.all.return_value = NETWORKS_FIXTURE
        ipfabric_client.technology.platforms.stacks_members.all.side_effect = [[] for site in SITE_FIXTURE[:-1]] + [
            STACKS_FIXTURE
        ]

        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        self.ipfabric = IPFabricDiffSync(job=job, sync=None, client=ipfabric_client)
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
            {f"{vlan['vlanName']}__{vlan['siteName']}" for vlan in VLAN_FIXTURE},
            {vlan.get_unique_id() for vlan in self.ipfabric.get_all("vlan")},
        )

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
            # Test mask from NETWORKS_FIXTURE is used
            if interface.name == "pseudo_mgmt":
                self.assertEqual(interface.subnet_mask, "255.255.255.0")
            # Test network not in NETWORKS_FIXTURE uses default of /32
            elif interface.name == "GigabitEthernet4":
                self.assertEqual(interface.subnet_mask, "255.255.255.255")
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
