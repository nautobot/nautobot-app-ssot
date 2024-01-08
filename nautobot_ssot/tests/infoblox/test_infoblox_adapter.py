"""Unit tests for the Infoblox DiffSync adapter class."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.models.infoblox import InfobloxNetwork
from nautobot_ssot.integrations.infoblox.jobs import InfobloxDataSource
from nautobot_ssot.integrations.infoblox.constant import PLUGIN_CFG


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


CONTAINER_FIXTURE = load_json("./nautobot_ssot/tests/infoblox/fixtures/get_network_containers.json")
SUBNET_FIXTURE = load_json("./nautobot_ssot/tests/infoblox/fixtures/get_all_subnets.json")
# DEVICE_INVENTORY_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_device_inventory.json")
# VLAN_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_vlans.json")
# INTERFACE_FIXTURE = load_json("./nautobot_ssot/tests/ipfabric/fixtures/get_interface_inventory.json")


class InfobloxDiffSyncTestCase(TestCase):
    """Test the InfobloxDiffSync adapter class."""

    # def setUp(self) -> None:
    #     # Create a mock client
    #     self.conn = MagicMock()

    #     self.job = InfobloxDataSource()
    #     self.job.job_result = JobResult.objects.create(
    #         name=self.job.class_path, task_name="fake task", worker="default"
    #     )
    #     self.infoblox = InfobloxAdapter(job=self.job, sync=None, conn=self.conn)
    #     return super().setUp()

    @patch("PLUGIN_CFG", {"infoblox_import_subnets": False})
    def test_load_prefixes(self):
        """Test the load_prefixes function."""
        self.conn = MagicMock()

        self.job = InfobloxDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.infoblox = InfobloxAdapter(job=self.job, sync=None, conn=self.conn)
        self.conn.get_all_subnets.return_value = SUBNET_FIXTURE
        self.conn.get_network_containers.return_value = CONTAINER_FIXTURE
        # print(self.conn.get_network_containers())
        # with patch.object(InfobloxApi, "get_all_subnets", self.conn.get_all_subnets):
        #     with patch.object(InfobloxApi, "get_network_containers", self.conn.get_network_containers):
        # with patch.object(PLUGIN_CFG, {"infoblox_import_subnets": False}):
        self.infoblox.load_prefixes()
        # # print(self.infoblox.get(InfobloxNetwork, {"network": "10.61.15.0/24"}))
        # self.assertEqual(True, False)

        # self.ipfabric.load()
        # self.assertEqual(
        #     {site["siteName"] for site in SITE_FIXTURE},
        #     {site.get_unique_id() for site in ipfabric.get_all("location")},
        # )
        # self.assertEqual(
        #     {dev["hostname"] for dev in DEVICE_INVENTORY_FIXTURE},
        #     {dev.get_unique_id() for dev in ipfabric.get_all("device")},
        # )
        # self.assertEqual(
        #     {f"{vlan['vlanName']}__{vlan['siteName']}" for vlan in VLAN_FIXTURE},
        #     {vlan.get_unique_id() for vlan in ipfabric.get_all("vlan")},
        # )

        # # Assert each site has a device tied to it.
        # for site in ipfabric.get_all("location"):
        #     self.assertEqual(len(site.devices), 1, f"{site} does not have the expected single device tied to it.")
        #     self.assertTrue(hasattr(site, "vlans"))

        # # Assert each device has the necessary attributes
        # for device in ipfabric.get_all("device"):
        #     self.assertTrue(hasattr(device, "location_name"))
        #     self.assertTrue(hasattr(device, "model"))
        #     self.assertTrue(hasattr(device, "vendor"))
        #     self.assertTrue(hasattr(device, "serial_number"))
        #     self.assertTrue(hasattr(device, "interfaces"))

        # # Assert each vlan has the necessary attributes
        # for vlan in ipfabric.get_all("vlan"):
        #     self.assertTrue(hasattr(vlan, "name"))
        #     self.assertTrue(hasattr(vlan, "vid"))
        #     self.assertTrue(hasattr(vlan, "status"))
        #     self.assertTrue(hasattr(vlan, "location"))
        #     self.assertTrue(hasattr(vlan, "description"))

        # # Assert each interface has the necessary attributes
        # for interface in ipfabric.get_all("interface"):
        #     self.assertTrue(hasattr(interface, "name"))
        #     self.assertTrue(hasattr(interface, "device_name"))
        #     self.assertTrue(hasattr(interface, "mac_address"))
        #     self.assertTrue(hasattr(interface, "mtu"))
        #     self.assertTrue(hasattr(interface, "ip_address"))
        #     self.assertTrue(hasattr(interface, "subnet_mask"))
        #     self.assertTrue(hasattr(interface, "type"))
