"""Unit tests for the IPFabric DiffSync adapter class."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
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


class IPFabricDiffSyncTestCase(TestCase):
    """Test the IPFabricDiffSync adapter class."""

    def test_data_loading(self):
        """Test the load() function."""

        # Create a mock client
        ipfabric_client = MagicMock()
        ipfabric_client.inventory.sites.all.return_value = SITE_FIXTURE
        ipfabric_client.inventory.devices.all.return_value = DEVICE_INVENTORY_FIXTURE
        ipfabric_client.fetch_all = MagicMock(
            side_effect=(lambda x: VLAN_FIXTURE if x == "tables/vlan/site-summary" else "")
        )
        ipfabric_client.inventory.interfaces.all.return_value = INTERFACE_FIXTURE

        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        ipfabric = IPFabricDiffSync(job=job, sync=None, client=ipfabric_client)
        ipfabric.load()
        self.assertEqual(
            {site["siteName"] for site in SITE_FIXTURE},
            {site.get_unique_id() for site in ipfabric.get_all("location")},
        )
        self.assertEqual(
            {dev["hostname"] for dev in DEVICE_INVENTORY_FIXTURE},
            {dev.get_unique_id() for dev in ipfabric.get_all("device")},
        )
        self.assertEqual(
            {f"{vlan['vlanName']}__{vlan['siteName']}" for vlan in VLAN_FIXTURE},
            {vlan.get_unique_id() for vlan in ipfabric.get_all("vlan")},
        )

        # Assert each site has a device tied to it.
        for site in ipfabric.get_all("location"):
            self.assertEqual(len(site.devices), 1, f"{site} does not have the expected single device tied to it.")
            self.assertTrue(hasattr(site, "vlans"))

        # Assert each device has the necessary attributes
        for device in ipfabric.get_all("device"):
            self.assertTrue(hasattr(device, "location_name"))
            self.assertTrue(hasattr(device, "model"))
            self.assertTrue(hasattr(device, "vendor"))
            self.assertTrue(hasattr(device, "serial_number"))
            self.assertTrue(hasattr(device, "interfaces"))

        # Assert each vlan has the necessary attributes
        for vlan in ipfabric.get_all("vlan"):
            self.assertTrue(hasattr(vlan, "name"))
            self.assertTrue(hasattr(vlan, "vid"))
            self.assertTrue(hasattr(vlan, "status"))
            self.assertTrue(hasattr(vlan, "location"))
            self.assertTrue(hasattr(vlan, "description"))

        # Assert each interface has the necessary attributes
        for interface in ipfabric.get_all("interface"):
            self.assertTrue(hasattr(interface, "name"))
            self.assertTrue(hasattr(interface, "device_name"))
            self.assertTrue(hasattr(interface, "mac_address"))
            self.assertTrue(hasattr(interface, "mtu"))
            self.assertTrue(hasattr(interface, "ip_address"))
            self.assertTrue(hasattr(interface, "subnet_mask"))
            self.assertTrue(hasattr(interface, "type"))

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def test_data_loading_elongate_interface_names(self):
        """Test the load() function with using long form interface names."""

        # Create a mock client
        ipfabric_client = MagicMock()
        ipfabric_client.inventory.sites.all.return_value = SITE_FIXTURE
        ipfabric_client.inventory.devices.all.return_value = DEVICE_INVENTORY_FIXTURE
        ipfabric_client.fetch_all = MagicMock(
            side_effect=(lambda x: VLAN_FIXTURE if x == "tables/vlan/site-summary" else "")
        )
        ipfabric_client.inventory.interfaces.all.return_value = INTERFACE_FIXTURE

        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        ipfabric = IPFabricDiffSync(job=job, sync=None, client=ipfabric_client)
        ipfabric.load()

        # Validate long interface names were created by not raising an exception
        # when performing `DiffSync.get()`
        ipfabric.get("interface", {"name": "ipip", "device_name": "nyc-rtr-01"})
        ipfabric.get("interface", {"name": "Ethernet15", "device_name": "nyc-leaf-01"})
        ipfabric.get("interface", {"name": "GigabitEthernet4", "device_name": "jcy-rtr-02"})
        ipfabric.get("interface", {"name": "Ethernet1", "device_name": "nyc-rtr-01"})
