"""Unit tests for the Device42 DiffSync adapter class."""

import json
from unittest.mock import MagicMock, patch
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobResult
from parameterized import parameterized
from nautobot_ssot.integrations.device42.diffsync.adapters.device42 import (
    Device42Adapter,
    get_dns_a_record,
    get_circuit_status,
    get_site_from_mapping,
)
from nautobot_ssot.integrations.device42.jobs import Device42DataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


BUILDING_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_buildings_recv.json")
ROOM_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_rooms_recv.json")
RACK_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_racks_recv.json")
VENDOR_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_vendors_recv.json")
HARDWARE_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_hardware_models_recv.json")
VRFGROUP_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_vrfgroups_recv.json")
VLAN_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_vlans_with_location.json")
SUBNET_DEFAULT_CFS_FIXTURE = load_json(
    "./nautobot_ssot/tests/device42/fixtures/get_subnet_default_custom_fields_recv.json"
)
SUBNET_CFS_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnet_custom_fields_recv.json")
SUBNET_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnets.json")
DEVICE_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_devices_recv.json")
CLUSTER_MEMBER_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_cluster_members_recv.json")
PORTS_W_VLANS_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_ports_with_vlans_recv.json")
PORTS_WO_VLANS_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_ports_wo_vlans_recv.json")
PORT_CUSTOM_FIELDS = load_json("./nautobot_ssot/tests/device42/fixtures/get_port_custom_fields_recv.json")
IPADDRESS_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_ip_addrs.json")
IPADDRESS_CF_FIXTURE = load_json("./nautobot_ssot/tests/device42/fixtures/get_ipaddr_custom_fields_recv.json")


class Device42AdapterTestCase(TransactionTestCase):  # pylint: disable=too-many-public-methods
    """Test the Device42Adapter class."""

    job_class = Device42DataSource
    databases = ("default", "job_logs")

    def setUp(self):
        """Method to initialize test case."""
        # Create a mock client
        self.d42_client = MagicMock()
        self.d42_client.get_buildings.return_value = BUILDING_FIXTURE
        self.d42_client.get_rooms.return_value = ROOM_FIXTURE
        self.d42_client.get_racks.return_value = RACK_FIXTURE
        self.d42_client.get_vendors.return_value = VENDOR_FIXTURE
        self.d42_client.get_hardware_models.return_value = HARDWARE_FIXTURE
        self.d42_client.get_vrfgroups.return_value = VRFGROUP_FIXTURE
        self.d42_client.get_vlans_with_location.return_value = VLAN_FIXTURE
        self.d42_client.get_subnet_default_custom_fields.return_value = SUBNET_DEFAULT_CFS_FIXTURE
        self.d42_client.get_subnet_custom_fields.return_value = SUBNET_CFS_FIXTURE
        self.d42_client.get_subnets.return_value = SUBNET_FIXTURE
        self.d42_client.get_devices.return_value = DEVICE_FIXTURE
        self.d42_client.get_cluster_members.return_value = CLUSTER_MEMBER_FIXTURE
        self.d42_client.get_ports_with_vlans.return_value = PORTS_W_VLANS_FIXTURE
        self.d42_client.get_ports_wo_vlans.return_value = PORTS_WO_VLANS_FIXTURE
        self.d42_client.get_port_custom_fields.return_value = PORT_CUSTOM_FIELDS
        self.d42_client.get_ip_addrs.return_value = IPADDRESS_FIXTURE
        self.d42_client.get_ipaddr_custom_fields.return_value = IPADDRESS_CF_FIXTURE

        self.job = self.job_class()
        self.job.logger = MagicMock()
        self.job.logger.info = MagicMock()
        self.job.logger.warning = MagicMock()
        self.job.debug = True
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.device42 = Device42Adapter(job=self.job, sync=None, client=self.d42_client)
        self.mock_device = MagicMock()
        self.mock_device.name = "cluster1 - Switch 1"
        self.mock_device.os_version = "1.0"
        self.cluster_dev = MagicMock()
        self.cluster_dev.name = "cluster1"
        self.master_dev = MagicMock()
        self.master_dev.name = "cluster1"
        self.master_dev.os_version = ""

    @patch(
        "nautobot_ssot.integrations.device42.utils.device42.PLUGIN_CFG",
        {
            "device42_customer_is_facility": True,
            "device42_facility_prepend": "sitecode-",
            "device42_hostname_mapping": [{"AUS": "Austin"}],
        },
    )
    def test_data_loading(self):
        """Test the load() function."""
        self.device42.load_buildings()
        self.assertEqual(
            {site["name"] for site in BUILDING_FIXTURE},
            {site.get_unique_id() for site in self.device42.get_all("building")},
        )
        self.device42.load_rooms()
        self.assertEqual(
            {f"{room['name']}__{room['building']}" for room in ROOM_FIXTURE},
            {room.get_unique_id() for room in self.device42.get_all("room")},
        )
        self.device42.load_racks()
        self.assertEqual(
            {f"{rack['name']}__{rack['building']}__{rack['room']}" for rack in RACK_FIXTURE},
            {rack.get_unique_id() for rack in self.device42.get_all("rack")},
        )
        self.device42.load_vrfgroups()
        self.assertEqual(
            {vrf["name"] for vrf in VRFGROUP_FIXTURE},
            {vrf.get_unique_id() for vrf in self.device42.get_all("vrf")},
        )
        self.device42.load_vlans()
        self.assertEqual(
            {f"{vlan['vid']}__{self.device42.d42_building_sitecode_map[vlan['customer']]}" for vlan in VLAN_FIXTURE},
            {vlan.get_unique_id() for vlan in self.device42.get_all("vlan")},
        )
        self.device42.load_subnets()
        self.assertEqual(
            {f"{net['network']}__{net['mask_bits']}__{net['vrf']}" for net in SUBNET_FIXTURE},
            {net.get_unique_id() for net in self.device42.get_all("subnet")},
        )
        self.device42.load_devices_and_clusters()
        self.assertEqual(
            {dev["name"] for dev in DEVICE_FIXTURE},
            {dev.get_unique_id() for dev in self.device42.get_all("device")},
        )
        self.device42.load_ports()
        self.assertEqual(
            {f"{port['device_name']}__{port['port_name']}" for port in PORTS_WO_VLANS_FIXTURE},
            {port.get_unique_id() for port in self.device42.get_all("port")},
        )
        self.device42.load_ip_addresses()
        self.assertEqual(
            {
                f"{ipaddr['ip_address']}/{ipaddr['netmask']}__{ipaddr['subnet']}/{ipaddr['netmask']}"
                for ipaddr in IPADDRESS_FIXTURE
            },
            {ipaddr.get_unique_id() for ipaddr in self.device42.get_all("ipaddr")},
        )

    def test_load_buildings_duplicate_site(self):
        """Validate functionality of the load_buildings() function when duplicate site is loaded."""
        self.device42.load_buildings()
        self.device42.load_buildings()
        self.job.logger.warning.assert_called_with(
            "Microsoft HQ is already loaded. ('Object Microsoft HQ already present', building \"Microsoft HQ\")"
        )

    def test_load_rooms_duplicate_room(self):
        """Validate functionality of the load_rooms() function when duplicate room is loaded."""
        self.device42.load_buildings()
        self.device42.load_rooms()
        self.device42.load_rooms()
        self.job.logger.warning.assert_called_with(
            "Secondary IDF is already loaded. ('Object Secondary IDF__Microsoft HQ already present', room \"Secondary IDF__Microsoft HQ\")"
        )

    def test_load_rooms_missing_building(self):
        """Validate functionality of the load_rooms() function when room loaded with missing building."""
        ROOM_FIXTURE[0]["building"] = ""
        self.device42.load_buildings()
        self.device42.load_rooms()
        self.job.logger.warning.assert_called_with("Network Closet is missing Building and won't be imported.")

    def test_load_racks_duplicate_rack(self):
        """Validate the functionality of the load_racks() function when duplicate rack is loaded."""
        self.device42.load_buildings()
        self.device42.load_rooms()
        self.device42.load_racks()
        self.device42.load_racks()
        self.job.logger.warning.assert_called_with(
            "Rack Rack A already exists. ('Object Rack A__Microsoft HQ__Main IDF already present', rack \"Rack A__Microsoft HQ__Main IDF\")"
        )

    def test_load_racks_missing_building_and_room(self):
        """Validate functionality of the load_racks() function when rack loaded with missing building and room."""
        RACK_FIXTURE[0]["building"] = ""
        RACK_FIXTURE[0]["room"] = ""
        self.device42.load_buildings()
        self.device42.load_rooms()
        self.device42.load_racks()
        self.job.logger.warning.assert_called_with("Rack 1 is missing Building and Room and won't be imported.")

    def test_load_cluster_duplicate_cluster(self):
        """Validate functionality of the load_cluster() function when cluster loaded with duplicate cluster."""
        self.device42.get = MagicMock()
        self.device42.get.side_effect = ObjectAlreadyExists("Duplicate object found.", existing_object=None)
        self.device42.load_cluster(cluster_info=DEVICE_FIXTURE[3])
        self.job.logger.warning.assert_called_with(
            "Cluster stack01.testexample.com already has been added. ('Duplicate object found.', None)"
        )

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.adapters.device42.PLUGIN_CFG",
        {"device42_ignore_tag": "TEST"},
    )
    def test_load_cluster_ignore_tag(self):
        """Validate functionality of the load_cluster() function when cluster has ignore tag."""
        self.device42.load_cluster(cluster_info=DEVICE_FIXTURE[3])
        self.job.logger.info.assert_called_once_with("Cluster stack01.testexample.com being loaded from Device42.")
        self.job.logger.warning.assert_called_once_with("Cluster stack01.testexample.com has ignore tag so skipping.")

    def test_load_devices_with_blank_building(self):
        """Validate functionality of the load_devices_and_clusters() function when device has a blank building."""
        self.device42.load_devices_and_clusters()
        self.job.logger.warning.assert_called_with(
            "Device stack01.testexample.com can't be loaded as we're unable to find associated Building."
        )

    def test_assign_version_to_master_devices_with_valid_os_version(self):
        """Validate functionality of the assign_version_to_master_devices() function with valid os_version."""
        self.device42.device42_clusters = {"cluster1": {"members": [self.mock_device]}}
        self.device42.get_all = MagicMock()
        self.device42.get_all.return_value = [self.cluster_dev]

        self.device42.get = MagicMock()
        self.device42.get.side_effect = [self.mock_device, self.master_dev]

        self.device42.assign_version_to_master_devices()

        self.assertEqual(self.master_dev.os_version, "1.0")
        self.job.logger.info.assert_called_once_with("Assigning 1.0 version to cluster1.")

    def test_assign_version_to_master_devices_with_blank_os_version(self):
        """Validate functionality of the assign_version_to_master_devices() function with blank os_version."""
        self.mock_device.os_version = ""
        self.device42.device42_clusters = {"cluster1": {"members": [self.mock_device]}}

        self.device42.get_all = MagicMock()
        self.device42.get_all.return_value = [self.cluster_dev]

        self.device42.get = MagicMock()
        self.device42.get.side_effect = [self.mock_device, self.master_dev]

        self.device42.assign_version_to_master_devices()

        self.assertEqual(self.master_dev.os_version, "")
        self.job.logger.info.assert_called_once_with(
            "Software version for cluster1 - Switch 1 is blank so will not assign version to cluster1."
        )

    def test_assign_version_to_master_devices_with_missing_cluster_host(self):
        """Validate functionality of the assign_version_to_master_devices() function with missing cluster host in device42_clusters."""
        self.device42.get_all = MagicMock()
        self.device42.get_all.return_value = [self.cluster_dev]

        self.device42.get = MagicMock()
        self.device42.get.return_value = KeyError

        self.device42.assign_version_to_master_devices()
        self.job.logger.warning.assert_called_once_with(
            "Unable to find cluster host in device42_clusters dictionary. 'cluster1'"
        )

    def test_assign_version_to_master_devices_with_missing_master_device(self):
        """Validate functionality of the assign_version_to_master_devices() function with missing master device."""
        self.device42.device42_clusters = {"cluster1": {"members": [self.mock_device]}}
        self.device42.get_all = MagicMock()
        self.device42.get_all.return_value = [self.cluster_dev]

        self.device42.get = MagicMock()
        self.device42.get.side_effect = [self.mock_device, ObjectNotFound]

        self.device42.assign_version_to_master_devices()
        self.job.logger.warning.assert_called_once_with("Unable to find VC Master Device cluster1 to assign version.")

    statuses = [
        ("Production", "Production", "Active"),
        ("Provisioning", "Provisioning", "Provisioning"),
        ("Canceled", "Canceled", "Deprovisioning"),
        ("Decommissioned", "Decommissioned", "Decommissioned"),
        ("Ordered", "Ordered", "Offline"),
    ]

    @parameterized.expand(statuses, skip_on_empty=True)
    def test_get_circuit_status(self, name, sent, received):  # pylint: disable=unused-argument
        """Test get_circuit_status success."""
        self.assertEqual(get_circuit_status(sent), received)

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.adapters.device42.PLUGIN_CFG",
        {"device42_hostname_mapping": [{"^aus.+|AUS.+": "austin"}]},
    )
    def test_get_site_from_mapping(self):
        """Test the get_site_from_mapping method."""
        expected = "austin"
        self.assertEqual(get_site_from_mapping(device_name="aus.test.com"), expected)

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.adapters.device42.PLUGIN_CFG",
        {"device42_hostname_mapping": [{"^aus.+|AUS.+": "austin"}]},
    )
    def test_get_site_from_mapping_missing_site(self):
        """Test the get_site_from_mapping method with missing site."""
        expected = ""
        self.assertEqual(get_site_from_mapping(device_name="dfw.test.com"), expected)

    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.is_fqdn_resolvable", return_value=True)
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.fqdn_to_ip", return_value="192.168.0.1")
    def test_get_dns_a_record_success(self, mock_fqdn_to_ip, mock_is_fqdn_resolvable):
        """Test the get_dns_a_record method success."""
        result = get_dns_a_record("example.com")
        mock_is_fqdn_resolvable.assert_called_once_with("example.com")
        mock_fqdn_to_ip.assert_called_once_with("example.com")
        self.assertEqual(result, "192.168.0.1")

    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.is_fqdn_resolvable", return_value=False)
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.fqdn_to_ip")
    def test_get_dns_a_record_failure(self, mock_fqdn_to_ip, mock_is_fqdn_resolvable):
        """Test the get_dns_a_record method failure."""
        result = get_dns_a_record("invalid-hostname")
        mock_is_fqdn_resolvable.assert_called_once_with("invalid-hostname")
        mock_fqdn_to_ip.assert_not_called()
        self.assertFalse(result)

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.adapters.device42.PLUGIN_CFG",
        {"device42_hostname_mapping": [{"^nyc.+|NYC.+": "new-york-city"}]},
    )
    def test_get_building_for_device_from_mapping(self):
        """Test the get_building_for_device method using site_mapping."""
        mock_dev_record = {"name": "nyc.test.com"}
        expected = "new-york-city"
        self.assertEqual(self.device42.get_building_for_device(dev_record=mock_dev_record), expected)

    def test_get_building_for_device_from_device_record(self):
        """Test the get_building_for_device method from device record."""
        mock_dev_record = {"name": "la.test.com", "building": "los-angeles"}
        expected = "los-angeles"
        self.assertEqual(self.device42.get_building_for_device(dev_record=mock_dev_record), expected)

    def test_get_building_for_device_missing_building(self):
        """Test the get_building_for_device method with missing building."""
        mock_dev_record = {"name": "la.test.com", "building": None}
        expected = ""
        self.assertEqual(self.device42.get_building_for_device(dev_record=mock_dev_record), expected)

    def test_filter_ports(self):
        """Method to test filter_ports success."""
        vlan_ports = load_json("./nautobot_ssot/tests/device42/fixtures/ports_with_vlans.json")
        no_vlan_ports = load_json("./nautobot_ssot/tests/device42/fixtures/ports_wo_vlans.json")
        merged_ports = load_json("./nautobot_ssot/tests/device42/fixtures/merged_ports.json")
        result = self.device42.filter_ports(vlan_ports, no_vlan_ports)
        self.assertEqual(merged_ports, result)

    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.get_dns_a_record")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.find_ipaddr")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.get_management_intf")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.add_management_interface")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.add_ipaddr")
    def test_set_primary_from_dns_with_valid_fqdn(  # pylint: disable=too-many-arguments
        self, mock_add_ipaddr, mock_add_mgmt_intf, mock_get_mgmt_intf, mock_find_ipaddr, mock_dns_a_record
    ):
        """Method to test the set_primary_from_dns functionality with valid FQDN."""
        mock_dns_a_record.return_value = "10.0.0.1"
        mock_find_ipaddr.return_value = False
        mock_mgmt_interface = MagicMock(name="mgmt_intf")
        mock_mgmt_interface.name = "eth0"
        mock_get_mgmt_intf.return_value = mock_mgmt_interface
        mock_add_mgmt_intf.return_value = mock_mgmt_interface
        mock_ip = MagicMock()
        mock_add_ipaddr.return_value = mock_ip
        dev_name = "router.test-example.com"
        self.device42.set_primary_from_dns(dev_name)

        mock_dns_a_record.assert_called_once_with(dev_name=dev_name)
        mock_find_ipaddr.assert_called_once_with(address="10.0.0.1")
        mock_get_mgmt_intf.assert_called_once_with(dev_name=dev_name)
        mock_add_mgmt_intf.assert_not_called()
        mock_add_ipaddr.assert_called_once_with(
            address="10.0.0.1/32", dev_name=dev_name, interface="eth0", namespace="Global"
        )
        self.assertEqual(mock_ip.device, "router.test-example.com")
        self.assertEqual(mock_ip.interface, "eth0")
        self.assertTrue(mock_ip.primary)

    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.get_dns_a_record")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.find_ipaddr")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.get_management_intf")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.add_management_interface")
    @patch("nautobot_ssot.integrations.device42.diffsync.adapters.device42.Device42Adapter.add_ipaddr")
    def test_set_primary_from_dns_with_invalid_fqdn(  # pylint: disable=too-many-arguments
        self, mock_add_ipaddr, mock_add_mgmt_intf, mock_get_mgmt_intf, mock_find_ipaddr, mock_dns_a_record
    ):
        """Method to test the set_primary_from_dns functionality with invalid FQDN."""
        mock_dns_a_record.return_value = ""
        dev_name = "router.test-example.com"
        self.job.logger.warning = MagicMock()
        self.device42.set_primary_from_dns(dev_name=dev_name)

        mock_dns_a_record.assert_called_once_with(dev_name=dev_name)
        mock_find_ipaddr.assert_not_called()
        mock_get_mgmt_intf.assert_not_called()
        mock_add_mgmt_intf.assert_not_called()
        mock_add_ipaddr.assert_not_called()
        self.job.logger.warning.assert_called_once()
