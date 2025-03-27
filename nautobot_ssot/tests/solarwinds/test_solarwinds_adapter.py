"""Test SolarWinds adapter."""

import uuid
from unittest.mock import MagicMock, call, patch

from diffsync.enum import DiffSyncModelFlags
from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.models import JobResult, Role, Status

import nautobot_ssot.tests.solarwinds.conftest as fix  # move to fixtures folder?
from nautobot_ssot.integrations.solarwinds.diffsync.adapters.solarwinds import SolarWindsAdapter
from nautobot_ssot.integrations.solarwinds.jobs import SolarWindsDataSource


class TestSolarWindsAdapterTestCase(TransactionTestCase):  # pylint: disable=too-many-public-methods
    """Test NautobotSsotSolarWindsAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):  # pylint: disable=invalid-name
        """Initialize test case."""
        self.status_active = Status.objects.get_or_create(name="Active")[0]
        self.status_active.content_types.add(ContentType.objects.get_for_model(Device))

        self.solarwinds_client = MagicMock()
        self.solarwinds_client.get_top_level_containers.return_value = fix.GET_TOP_LEVEL_CONTAINERS_FIXTURE
        self.solarwinds_client.get_filtered_container_ids.return_value = {"HQ": 1}
        self.solarwinds_client.get_container_nodes.side_effect = fix.get_container_nodes

        self.containers = "HQ"

        self.location_type = LocationType.objects.get_or_create(name="Site")[0]
        self.location_type.content_types.add(ContentType.objects.get_for_model(Device))

        self.parent = Location.objects.get_or_create(
            name="USA", location_type=LocationType.objects.get_or_create(name="Region")[0], status=self.status_active
        )[0]

        self.job = SolarWindsDataSource()
        self.job.debug = True
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="Fake task", user=None, id=uuid.uuid4()
        )
        self.job.logger = MagicMock()
        self.job.logger.debug = MagicMock()
        self.job.logger.error = MagicMock()
        self.job.logger.info = MagicMock()
        self.job.logger.warning = MagicMock()
        self.job.location_type = self.location_type
        self.job.location_override = None
        self.job.parent = self.parent
        self.job.default_role = Role.objects.get_or_create(name="Router")[0]
        self.solarwinds = SolarWindsAdapter(
            job=self.job,
            sync=None,
            client=self.solarwinds_client,
            containers=self.containers,
            location_type=self.location_type,
        )

    def test_data_loading_wo_parent(self):
        """Test Nautobot SSoT SolarWinds load() function without parent specified."""
        self.solarwinds_client.standardize_device_type.side_effect = ["", "WS-C4500 L3", ""]
        self.solarwinds_client.extract_version.return_value = "03.11.01.E"
        self.solarwinds_client.build_node_details.return_value = fix.NODE_DETAILS_FIXTURE
        self.solarwinds_client.determine_interface_type.return_value = "10gbase-t"

        self.solarwinds.load_parent = MagicMock()
        self.solarwinds.load_prefix = MagicMock()
        self.solarwinds.load_ipaddress = MagicMock()
        self.solarwinds.load_interfaces = MagicMock()
        self.solarwinds.load_ipassignment = MagicMock()

        self.solarwinds.load()
        self.solarwinds.load_parent.assert_not_called()
        self.job.logger.debug.assert_has_calls(
            [
                call("Retrieving node details from SolarWinds for HQ."),
                call(
                    'Node details: {\n  "10": {\n    "NodeHostname": "UNKNOWN_DEVICE_TYPE1",\n    "NodeID": 10,\n    "interfaces": {\n      "TenGigabitEthernet0/0/0": {\n        "Name": "TenGigabitEthernet0/0/0",\n        "Enabled": "Up",\n        "Status": "Up",\n        "TypeName": "ethernetCsmacd",\n        "Speed": 10000000000.0,\n        "MAC": "AA74D2BCD341",\n        "MTU": 9104\n      },\n      "TenGigabitEthernet0/1/0": {\n        "Name": "TenGigabitEthernet0/1/0",\n        "Enabled": "Unknown",\n        "Status": "Unknown",\n        "TypeName": "ethernetCsmacd",\n        "Speed": 10000000000.0,\n        "MAC": "B8D028D78C15",\n        "MTU": 9216\n      },\n      "TenGigabitEthernet0/1/0.75": {\n        "Name": "TenGigabitEthernet0/1/0.75",\n        "Enabled": "Unknown",\n        "Status": "Unknown",\n        "TypeName": "l2vlan",\n        "Speed": 10000000000.0,\n        "MAC": "G6F260AD2C18",\n        "MTU": 9216\n      }\n    },\n    "ipaddrs": {\n      "1.1.1.1": {\n        "IPAddress": "1.1.1.1",\n        "SubnetMask": 23,\n        "IPAddressType": "IPv4",\n        "IntfName": "TenGigabitEthernet0/0/0"\n      },\n      "10.10.1.2": {\n        "IPAddress": "10.10.1.2",\n        "SubnetMask": 23,\n        "IPAddressType": "IPv4",\n        "IntfName": "TenGigabitEthernet0/1/0.75"\n      }\n    }\n  },\n  "11": {\n    "NodeHostname": "Router01",\n    "NodeID": 11,\n    "Version": "03.11.01.E RELEASE SOFTWARE (fc4)",\n    "IPAddress": "172.16.5.2",\n    "PFLength": 24,\n    "SNMPLocation": "LOCATION STRING",\n    "Vendor": "Cisco",\n    "DeviceType": "Cisco Catalyst 4500 L3",\n    "Model": null,\n    "ServiceTag": null,\n    "interfaces": {\n      "TenGigabitEthernet1/1/1": {\n        "Name": "TenGigabitEthernet1/1/1",\n        "Enabled": "Unknown",\n        "Status": "Unknown",\n        "TypeName": "ethernetCsmacd",\n        "Speed": 1000000000.0,\n        "MAC": "F674BD01ADE4",\n        "MTU": 1500\n      },\n      "TenGigabitEthernet1/1/2": {\n        "Name": "TenGigabitEthernet1/1/2",\n        "Enabled": "Unknown",\n        "Status": "Unknown",\n        "TypeName": "ethernetCsmacd",\n        "Speed": 1000000000.0,\n        "MAC": "F674BD01ADE5",\n        "MTU": 1500\n      }\n    },\n    "ipaddrs": {\n      "10.11.1.1": {\n        "IPAddress": "10.11.1.1",\n        "SubnetMask": 23,\n        "IPAddressType": "IPv4",\n        "IntfName": "TenGigabitEthernet1/1/1"\n      },\n      "10.11.1.2": {\n        "IPAddress": "10.11.1.2",\n        "SubnetMask": 23,\n        "IPAddressType": "IPv4",\n        "IntfName": "TenGigabitEthernet1/1/2"\n      },\n      "172.16.1.1": {\n        "IPAddress": "172.16.1.1",\n        "SubnetMask": 24,\n        "IPAddressType": "IPv4",\n        "IntfName": "Ethernet0/1"\n      }\n    }\n  },\n  "12": {\n    "NodeHostname": "net-snmp Device",\n    "NodeID": 12,\n    "Vendor": "net-snmp"\n  }\n}'
                ),
            ]
        )
        self.assertEqual(
            {
                dev["NodeHostname"]
                for _, dev in fix.NODE_DETAILS_FIXTURE.items()
                if dev.get("Model") or dev.get("DeviceType")
            },
            {dev.get_unique_id() for dev in self.solarwinds.get_all("device")},
        )
        self.solarwinds.load_prefix.assert_called()
        self.solarwinds.load_prefix.assert_has_calls(
            [
                call(network="172.16.5.0/24"),
                call(network="10.11.0.0/23"),
                call(network="10.11.0.0/23"),
                call(network="172.16.1.0/24"),
            ]
        )
        self.solarwinds.load_ipaddress.assert_called()
        self.solarwinds.load_ipaddress.assert_has_calls(
            [
                call(addr="172.16.5.2", prefix_length=24, prefix="172.16.5.0/24", addr_type="IPv4"),
                call(addr="10.11.1.1", prefix_length=23, prefix="10.11.0.0/23", addr_type="IPv4"),
                call(addr="10.11.1.2", prefix_length=23, prefix="10.11.0.0/23", addr_type="IPv4"),
                call(addr="172.16.1.1", prefix_length=24, prefix="172.16.1.0/24", addr_type="IPv4"),
            ]
        )

        loaded_dev = self.solarwinds.get("device", "Router01")
        self.solarwinds.load_interfaces.assert_called()
        self.solarwinds.load_interfaces.assert_has_calls(
            [
                call(device=loaded_dev, intfs=fix.NODE_DETAILS_FIXTURE["11"]["interfaces"]),
                call(device=loaded_dev, intfs={1: {"Name": "Management", "Enabled": "Up", "Status": "Up"}}),
            ]
        )
        self.solarwinds.load_ipassignment.assert_has_calls(
            [
                call(
                    addr="172.16.5.2",
                    dev_name="Router01",
                    intf_name="Management",
                    addr_type="IPv4",
                    mgmt_addr="172.16.5.2",
                ),
                call(
                    addr="10.11.1.1",
                    dev_name="Router01",
                    intf_name="TenGigabitEthernet1/1/1",
                    addr_type="IPv4",
                    mgmt_addr="172.16.5.2",
                ),
                call(
                    addr="10.11.1.2",
                    dev_name="Router01",
                    intf_name="TenGigabitEthernet1/1/2",
                    addr_type="IPv4",
                    mgmt_addr="172.16.5.2",
                ),
                call(
                    addr="172.16.1.1",
                    dev_name="Router01",
                    intf_name="Ethernet0/1",
                    addr_type="IPv4",
                    mgmt_addr="172.16.5.2",
                ),
            ]
        )
        self.job.logger.error.assert_has_calls(
            [
                call("UNKNOWN_DEVICE_TYPE1 is missing DeviceType so won't be imported."),
                call("net-snmp Device is showing as net-snmp so won't be imported."),
            ]
        )
        self.assertEqual(len(self.solarwinds.failed_devices), 2)
        self.job.logger.warning.assert_called_with(
            'List of 2 devices that were unable to be loaded. [\n  {\n    "NodeHostname": "UNKNOWN_DEVICE_TYPE1",\n    "NodeID": 10,\n    "interfaces": {\n      "TenGigabitEthernet0/0/0": {\n        "Name": "TenGigabitEthernet0/0/0",\n        "Enabled": "Up",\n        "Status": "Up",\n        "TypeName": "ethernetCsmacd",\n        "Speed": 10000000000.0,\n        "MAC": "AA74D2BCD341",\n        "MTU": 9104\n      },\n      "TenGigabitEthernet0/1/0": {\n        "Name": "TenGigabitEthernet0/1/0",\n        "Enabled": "Unknown",\n        "Status": "Unknown",\n        "TypeName": "ethernetCsmacd",\n        "Speed": 10000000000.0,\n        "MAC": "B8D028D78C15",\n        "MTU": 9216\n      },\n      "TenGigabitEthernet0/1/0.75": {\n        "Name": "TenGigabitEthernet0/1/0.75",\n        "Enabled": "Unknown",\n        "Status": "Unknown",\n        "TypeName": "l2vlan",\n        "Speed": 10000000000.0,\n        "MAC": "G6F260AD2C18",\n        "MTU": 9216\n      }\n    },\n    "ipaddrs": {\n      "1.1.1.1": {\n        "IPAddress": "1.1.1.1",\n        "SubnetMask": 23,\n        "IPAddressType": "IPv4",\n        "IntfName": "TenGigabitEthernet0/0/0"\n      },\n      "10.10.1.2": {\n        "IPAddress": "10.10.1.2",\n        "SubnetMask": 23,\n        "IPAddressType": "IPv4",\n        "IntfName": "TenGigabitEthernet0/1/0.75"\n      }\n    },\n    "error": "Unable to determine DeviceType."\n  },\n  {\n    "NodeHostname": "net-snmp Device",\n    "NodeID": 12,\n    "Vendor": "net-snmp",\n    "error": "Unable to determine DeviceType."\n  }\n]'
        )

    def test_data_loading_w_parent(self):
        """Test Nautobot SSoT SolarWinds load() function with parent specified."""
        self.solarwinds = SolarWindsAdapter(
            job=self.job,
            sync=None,
            client=self.solarwinds_client,
            containers=self.containers,
            location_type=self.location_type,
            parent=self.parent,
        )

        self.solarwinds.load_parent = MagicMock()
        self.solarwinds.get_container_nodes = MagicMock()

        self.solarwinds.load()
        self.solarwinds.load_parent.assert_called_once()
        self.solarwinds.get_container_nodes.assert_called_once()

    def test_load_manufacturer_and_device_type(self):
        """Test the load_manufacturer_and_device_type() function for success."""
        self.solarwinds.load_manufacturer_and_device_type(manufacturer="Cisco", device_type="ASR1001")
        self.assertEqual({"Cisco"}, {manu.get_unique_id() for manu in self.solarwinds.get_all("manufacturer")})
        self.assertEqual({"ASR1001__Cisco"}, {manu.get_unique_id() for manu in self.solarwinds.get_all("device_type")})

    def test_get_container_nodes_specific_container(self):
        """Test the get_container_nodes() function success with a specific container."""
        results = self.solarwinds.get_container_nodes()
        self.assertEqual(self.solarwinds.containers, "HQ")
        self.solarwinds_client.get_filtered_container_ids.assert_called_once_with(containers="HQ")
        self.solarwinds_client.get_container_nodes.assert_called()
        self.assertEqual(results, fix.GET_CONTAINER_NODES_FIXTURE)

    def test_get_container_nodes_all_containers(self):
        """Test the get_container_nodes() function success with all containers."""
        self.solarwinds.containers = "ALL"
        self.job.top_container = "USA"
        results = self.solarwinds.get_container_nodes()
        self.solarwinds_client.get_top_level_containers.assert_called_once_with(top_container="USA")
        self.solarwinds_client.get_container_nodes.assert_called()
        self.assertEqual(results, fix.GET_CONTAINER_NODES_FIXTURE)

    def test_get_container_nodes_all_containers_custom_property(self):
        """Test the get_container_nodes() function success with all containers."""
        self.solarwinds.containers = "ALL"
        self.job.top_container = "USA"
        self.job.custom_property = "Nautobot_Sync"
        results = self.solarwinds.get_container_nodes(custom_property=self.job.custom_property)
        self.solarwinds_client.get_top_level_containers.assert_called_once_with(top_container="USA")
        self.solarwinds_client.get_container_nodes.assert_called()
        self.assertEqual(results, fix.GET_CONTAINER_NODES_CUSTOM_PROPERTY_FIXTURE)

    def test_load_location(self):
        """Test the load_location() function."""
        self.solarwinds.load_location(loc_name="HQ", location_type="Site", status="Active")
        self.assertEqual(
            {"HQ__Site__None__None__None__None"}, {loc.get_unique_id() for loc in self.solarwinds.get_all("location")}
        )

    def test_load_parent(self):
        """Test the load_parent() function loads the Parent Location."""
        self.solarwinds = SolarWindsAdapter(
            job=self.job,
            sync=None,
            client=self.solarwinds_client,
            containers=self.containers,
            location_type=self.location_type,
            parent=self.parent,
        )
        self.solarwinds.load_parent()
        self.assertEqual(
            {"USA__Region__None__None__None__None"},
            {loc.get_unique_id() for loc in self.solarwinds.get_all("location")},
        )
        parent = self.solarwinds.get("location", "USA__Region__None__None__None__None")
        self.assertEqual(parent.model_flags, DiffSyncModelFlags.SKIP_UNMATCHED_DST)

    def load_sites_wo_parent(self):
        """Test the load_sites() function when a parent isn't specified."""
        test_sites = {
            "HQ": [
                {"ContainerID": 1, "MemberPrimaryID": 10},
                {"ContainerID": 1, "MemberPrimaryID": 11},
            ],
            "DC01": [
                {"ContainerID": 2, "MemberPrimaryID": 20},
                {"ContainerID": 2, "MemberPrimaryID": 21},
            ],
        }
        self.solarwinds.load_sites(container_nodes=test_sites)
        self.job.logger.debug.calls[0].assert_called_with("Found 2 nodes for HQ container.")
        self.job.logger.debug.calls[1].assert_called_with("Found 2 nodes for DC01 container.")
        self.assertEqual(
            {"HQ__Site__None__None__None__None", "DC01__Site__None__None__None__None"},
            {loc.get_unique_id() for loc in self.solarwinds.get_all("location")},
        )

    def load_sites_w_parent(self):
        """Test the load_sites() function when a parent isn't specified."""
        self.solarwinds = SolarWindsAdapter(
            job=self.job,
            sync=None,
            client=self.solarwinds_client,
            containers=self.containers,
            location_type=self.location_type,
            parent=self.parent,
        )
        test_sites = {
            "HQ": [
                {"ContainerID": 1, "MemberPrimaryID": 10},
                {"ContainerID": 1, "MemberPrimaryID": 11},
            ],
            "DC01": [
                {"ContainerID": 2, "MemberPrimaryID": 20},
                {"ContainerID": 2, "MemberPrimaryID": 21},
            ],
        }
        self.solarwinds.load_sites(container_nodes=test_sites)
        self.job.logger.debug.calls[0].assert_called_with("Found 2 nodes for HQ container.")
        self.job.logger.debug.calls[1].assert_called_with("Found 2 nodes for DC01 container.")
        self.assertEqual(
            {"HQ__Site__USA__Region", "DC01__Site__USA__Region"},
            {loc.get_unique_id() for loc in self.solarwinds.get_all("location")},
        )

    @patch("nautobot_ssot.integrations.solarwinds.diffsync.adapters.solarwinds.determine_role_from_devicetype")
    def test_determine_device_role_device_type(self, mock_func):
        """Test the determine_device_role() when DeviceType role choice is specified."""
        self.job.role_map = {"ASR1001": "Router"}
        self.job.role_choice = "DeviceType"

        self.solarwinds.determine_device_role(node={}, device_type="ASR1001")
        mock_func.assert_called_with(device_type="ASR1001", role_map={"ASR1001": "Router"})

    @patch("nautobot_ssot.integrations.solarwinds.diffsync.adapters.solarwinds.determine_role_from_hostname")
    def test_determine_device_role_hostname(self, mock_func):
        """Test the determine_device_role() when Hostname role choice is specified."""
        self.job.role_map = {".*router.*": "Router"}
        self.job.role_choice = "Hostname"

        self.solarwinds.determine_device_role(node={"NodeHostname": "core-router.corp"}, device_type="")
        mock_func.assert_called_with(hostname="core-router.corp", role_map={".*router.*": "Router"})

    def test_load_role(self):
        """Test the load_role() success."""
        self.solarwinds.load_role(role="Test")
        self.assertEqual({"Test"}, {role.get_unique_id() for role in self.solarwinds.get_all("role")})

    def test_load_platform_aireos(self):
        """Test the load_platform() function with AireOS device."""
        result = self.solarwinds.load_platform(device_type="8540 Series Wireless Controllers", manufacturer="Cisco")
        result2 = self.solarwinds.load_platform(device_type="8500WLC", manufacturer="Cisco")
        self.assertEqual(result, "cisco.ios.aireos")
        self.assertEqual(result2, "cisco.ios.aireos")
        self.assertEqual(
            {"cisco.ios.aireos__Cisco"}, {plat.get_unique_id() for plat in self.solarwinds.get_all("platform")}
        )

    def test_load_platform_aruba_aoscx(self):
        """Test the load_platform() function with Aruba AOSCX device."""
        result = self.solarwinds.load_platform(device_type="6100-US", manufacturer="Aruba")
        self.assertEqual(result, "arubanetworks.aos.aoscx")
        self.assertEqual(
            {"arubanetworks.aos.aoscx__Aruba"}, {plat.get_unique_id() for plat in self.solarwinds.get_all("platform")}
        )

    def test_load_platform_aruba_os(self):
        """Test the load_platform() function with Aruba OS device."""
        result = self.solarwinds.load_platform(device_type="MM-HW-5K", manufacturer="Aruba")
        result2 = self.solarwinds.load_platform(device_type="7240XM-US", manufacturer="Aruba")
        self.assertEqual(result, "arubanetworks.aos.os")
        self.assertEqual(result2, "arubanetworks.aos.os")
        self.assertEqual(
            {"arubanetworks.aos.os__Aruba"}, {plat.get_unique_id() for plat in self.solarwinds.get_all("platform")}
        )

    def test_load_platform_aruba_osswitch(self):
        """Test the load_platform() function with Aruba OSSwitch device."""
        result = self.solarwinds.load_platform(device_type="2530-US", manufacturer="Aruba")
        self.assertEqual(result, "arubanetworks.aos.osswitch")
        self.assertEqual(
            {"arubanetworks.aos.osswitch__Aruba"},
            {plat.get_unique_id() for plat in self.solarwinds.get_all("platform")},
        )

    def test_load_platform_ios(self):
        """Test the load_platform() function with IOS device."""
        result = self.solarwinds.load_platform(device_type="ASR1001", manufacturer="Cisco")
        self.assertEqual(result, "cisco.ios.ios")
        self.assertEqual(
            {"cisco.ios.ios__Cisco"}, {plat.get_unique_id() for plat in self.solarwinds.get_all("platform")}
        )

    def test_load_platform_nxos(self):
        """Test the load_platform() function with Nexus device."""
        result = self.solarwinds.load_platform(device_type="N9K-93180YC", manufacturer="Cisco")
        self.assertEqual(result, "cisco.nxos.nxos")
        self.assertEqual(
            {"cisco.nxos.nxos__Cisco"}, {plat.get_unique_id() for plat in self.solarwinds.get_all("platform")}
        )

    def test_load_interfaces(self):
        """Test the load_interfaces() functions successfully."""
        mock_dev = MagicMock()
        mock_dev.name = "Test Device"

        self.solarwinds_client.determine_interface_type.return_value = "1000base-t"

        test_intfs = {
            "GigabitEthernet0/1": {
                "Name": "GigabitEthernet0/1",
                "Enabled": "Up",
                "Status": "Up",
                "MTU": 9180,
                "MAC": "112233445566",
            },
            "GigabitEthernet0/2": {
                "Name": "GigabitEthernet0/2",
                "Enabled": "Up",
                "Status": "Up",
                "MTU": 9180,
                "MAC": "112233445567",
            },
        }
        self.solarwinds.load_interfaces(device=mock_dev, intfs=test_intfs)
        self.assertEqual(
            {"GigabitEthernet0/1__Test Device", "GigabitEthernet0/2__Test Device"},
            {intf.get_unique_id() for intf in self.solarwinds.get_all("interface")},
        )
        self.solarwinds_client.determine_interface_type.assert_called()
        mock_dev.add_child.assert_called()

    def test_load_prefix(self):
        """Validate that the load_prefix() function loads Prefix DiffSync object."""
        self.solarwinds.load_prefix(network="10.0.0.0/24")
        self.assertEqual({"10.0.0.0__24__Global"}, {pf.get_unique_id() for pf in self.solarwinds.get_all("prefix")})

    def test_load_ipaddress(self):
        """Validate that load_ipaddress() correctly loads a DiffSync object."""
        self.solarwinds.load_ipaddress(addr="10.0.0.1", prefix_length=24, prefix="10.0.0.0/24", addr_type="IPv4")
        self.assertEqual(
            {"10.0.0.1__10.0.0.0__24__Global"},
            {ipaddr.get_unique_id() for ipaddr in self.solarwinds.get_all("ipaddress")},
        )

    def test_load_ipassignment(self):
        """Validate that load_ipassignment() correctly loads a DiffSync object."""
        self.solarwinds.load_ipassignment(
            addr="10.0.0.1", dev_name="Test Device", intf_name="Management", addr_type="IPv4", mgmt_addr="10.0.0.1"
        )
        self.assertEqual(
            {"Test Device__Management__10.0.0.1"},
            {assignment.get_unique_id() for assignment in self.solarwinds.get_all("ipassignment")},
        )

    def test_reprocess_ip_parent_prefixes_more_specific(self):
        """Validate that reprocess_ip_parent_prefixes identifies a more specific prefix."""
        self.solarwinds.load_prefix(network="10.0.0.0/24")
        self.solarwinds.load_prefix(network="10.0.0.0/25")
        self.solarwinds.load_ipaddress(addr="10.0.0.1", prefix_length=24, prefix="10.0.0.0/24", addr_type="IPv4")
        self.solarwinds.reprocess_ip_parent_prefixes()
        self.job.debug = True
        self.job.logger.debug.assert_called_once_with(
            "More specific subnet %s found for IP %s/%s", "10.0.0.0/25", "10.0.0.1", 24
        )
        self.assertEqual(
            {"10.0.0.1__10.0.0.0__25__Global"},
            {ipaddr.get_unique_id() for ipaddr in self.solarwinds.get_all("ipaddress")},
        )

    def test_reprocess_ip_parent_prefixes_no_update(self):
        """Validate that reprocess_ip_parent_prefixes does not update the ip."""
        self.solarwinds.load_prefix(network="10.0.0.0/24")
        self.solarwinds.load_prefix(network="10.0.0.0/23")
        self.solarwinds.load_ipaddress(addr="10.0.0.1", prefix_length=24, prefix="10.0.0.0/24", addr_type="IPv4")
        self.solarwinds.reprocess_ip_parent_prefixes()
        self.job.debug = True
        self.job.logger.debug.assert_not_called()
        self.assertEqual(
            {"10.0.0.1__10.0.0.0__24__Global"},
            {ipaddr.get_unique_id() for ipaddr in self.solarwinds.get_all("ipaddress")},
        )
