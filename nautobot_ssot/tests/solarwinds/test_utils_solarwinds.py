# pylint: disable=R0801
"""Test SolarWinds utility functions and client."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import requests
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobResult
from parameterized import parameterized

from nautobot_ssot.integrations.solarwinds.jobs import SolarWindsDataSource
from nautobot_ssot.integrations.solarwinds.utils.solarwinds import (
    determine_role_from_devicetype,
    determine_role_from_hostname,
)
from nautobot_ssot.tests.solarwinds.conftest import create_solarwinds_client


class TestSolarWindsClientTestCase(TransactionTestCase):  # pylint: disable=too-many-public-methods
    """Test the SolarWindsClient class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Configure shared variables for tests."""
        self.job = SolarWindsDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="Fake task", user=None, id=uuid.uuid4()
        )
        self.job.integration = MagicMock()
        self.job.integration.extra_config = {"batch_size": 10}
        self.job.logger.debug = MagicMock()
        self.job.logger.error = MagicMock()
        self.job.logger.info = MagicMock()
        self.job.logger.warning = MagicMock()
        self.test_client = create_solarwinds_client(job=self.job)

        self.test_nodes = [{"Name": "Router01", "MemberPrimaryID": 1}, {"Name": "Switch01", "MemberPrimaryID": 2}]
        self.node_details = {1: {"NodeHostname": "Router01", "NodeID": 1}, 2: {"NodeHostname": "Switch01", "NodeID": 2}}

    def test_solarwinds_client_initialization(self):
        """Validate the SolarWindsClient functionality."""
        self.assertEqual(self.test_client.url, "https://test.solarwinds.com:443/SolarWinds/InformationService/v3/Json/")
        self.assertEqual(self.test_client.job, self.job)
        self.assertEqual(self.test_client.batch_size, 10)
        self.assertEqual(self.test_client.timeout, 60)
        self.assertEqual(self.test_client.retries, 5)

    def test_query(self):
        """Validate that query() works as expected."""
        mock_expected = MagicMock(spec=requests.Response)
        mock_expected.status_code = 200
        mock_expected.json.return_value = {"results": {"1": {"Name": "HQ"}}}
        self.test_client._req = MagicMock()  # pylint: disable=protected-access
        self.test_client._req.return_value = mock_expected  # pylint: disable=protected-access
        result = self.test_client.query(query="SELECT ContainerID FROM Orion.Container WHERE Name = 'HQ'")
        self.test_client._req.assert_called_with(  # pylint: disable=protected-access
            "POST", "Query", {"query": "SELECT ContainerID FROM Orion.Container WHERE Name = 'HQ'", "parameters": {}}
        )
        self.assertEqual(result, {"results": {"1": {"Name": "HQ"}}})

    def test_json_serial(self):
        """Validate the _json_serial() functionality."""
        test_datetime = datetime(2020, 1, 1, 12, 0, 0)
        expected_serialized = "2020-01-01T12:00:00"
        result = self.test_client._json_serial(test_datetime)  # pylint: disable=protected-access
        self.assertEqual(expected_serialized, result)

    @patch("nautobot_ssot.integrations.solarwinds.utils.solarwinds.requests.Session.request")
    def test_successful_request(self, mock_request):
        """Validate successful functionality of the _req() function."""
        mock_response = MagicMock(requests.Response)
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        response = self.test_client._req("GET", "test")  # pylint: disable=protected-access

        self.assertEqual(response.status_code, 200)
        mock_request.assert_called_once_with("GET", self.test_client.url + "test", data="null", timeout=60)

    @patch("nautobot_ssot.integrations.solarwinds.utils.solarwinds.requests.Session.request")
    def test_request_with_data(self, mock_request):
        """Validate successful functionality of the _req() function with data passed."""
        mock_response = MagicMock(requests.Response)
        mock_response.status_code = 201
        mock_request.return_value = mock_response

        response = self.test_client._req("POST", "create", data={"key": "value"})  # pylint: disable=protected-access

        self.assertEqual(response.status_code, 201)
        mock_request.assert_called_once_with(
            "POST", self.test_client.url + "create", data='{"key": "value"}', timeout=60
        )

    @patch("nautobot_ssot.integrations.solarwinds.utils.solarwinds.requests.Session.request")
    def test_request_400_600_status_code(self, mock_request):
        """Validate handling of _req() call when 4xx or 5xx status code returned."""
        mock_response = MagicMock(requests.Response)
        mock_response.status_code = 401
        mock_response.text = '{"Message": "Unauthorized"}'
        mock_request.return_value = mock_response

        response = self.test_client._req("GET", "unauthorized")  # pylint: disable=protected-access

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.reason, "Unauthorized")
        self.assertIsInstance(response, requests.Response)
        mock_request.assert_called_once_with("GET", self.test_client.url + "unauthorized", data="null", timeout=60)

    @patch("nautobot_ssot.integrations.solarwinds.utils.solarwinds.requests.Session.request")
    def test_request_json_decoding_error_handling(self, mock_request):
        """Validate handling of JSON decoding error in _req() call."""
        mock_response = MagicMock(requests.Response)
        mock_response.status_code = 500
        mock_response.text = '{"key": "value"'
        mock_request.return_value = mock_response

        response = self.test_client._req("GET", "decode_error")  # pylint: disable=protected-access

        self.assertEqual(response.status_code, 500)
        self.assertIsInstance(response, requests.Response)
        mock_request.assert_called_once_with("GET", self.test_client.url + "decode_error", data="null", timeout=60)

    @patch("nautobot_ssot.integrations.solarwinds.utils.solarwinds.requests.Session.request")
    def test_request_exception_handling(self, mock_request):
        """Validate handling of Exception thrown in _req() call."""
        mock_request.side_effect = requests.exceptions.RequestException("Request timed out")

        response = self.test_client._req("GET", "timeout")  # pylint: disable=protected-access

        self.job.logger.error.assert_called_with("An error occurred: Request timed out")
        self.assertEqual(response.status_code, None)
        self.assertIsInstance(response, requests.Response)
        self.assertEqual(response.content, None)
        mock_request.assert_called_once_with("GET", self.test_client.url + "timeout", data="null", timeout=60)

    def test_get_filtered_container_ids_success(self):
        """Validate successful retrieval of container IDs with get_filtered_container_ids()."""
        self.test_client.find_container_id_by_name = MagicMock()
        self.test_client.find_container_id_by_name.side_effect = [1, 2]

        expected = {"DC01": 1, "DC02": 2}
        result = self.test_client.get_filtered_container_ids(containers="DC01,DC02")
        self.assertEqual(result, expected)
        self.job.logger.error.assert_not_called()

    def test_get_filtered_container_ids_failure(self):
        """Validate failed retrieval of container IDs with get_filtered_container_ids()."""
        self.test_client.find_container_id_by_name = MagicMock()
        self.test_client.find_container_id_by_name.return_value = -1

        result = self.test_client.get_filtered_container_ids(containers="Failure")
        self.job.logger.error.assert_called_once_with("Unable to find container Failure.")
        self.assertEqual(result, {})

    def test_get_container_nodes(self):
        """Validate functionality of get_container_nodes()."""
        container_ids = {"DC01": 1}
        self.test_client.recurse_collect_container_nodes = MagicMock()
        self.test_client.recurse_collect_container_nodes.return_value = [1, 2, 3]
        result = self.test_client.get_container_nodes(container_ids=container_ids)

        self.job.logger.debug.assert_called_once_with("Gathering container nodes for DC01 CID: 1.")
        self.test_client.recurse_collect_container_nodes.assert_called_once()
        self.assertEqual(result, {"DC01": [1, 2, 3]})

    def test_get_top_level_containers(self):
        """Validate functionality of get_top_level_containers()."""
        self.test_client.find_container_id_by_name = MagicMock()
        self.test_client.find_container_id_by_name.return_value = 1
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {
            "results": [
                {"ContainerID": 1, "Name": "Test", "MemberPrimaryID": 10},
                {"ContainerID": 1, "Name": "Test2", "MemberPrimaryID": 11},
            ]
        }

        result = self.test_client.get_top_level_containers(top_container="Top")
        self.assertEqual(result, {"Test": 10, "Test2": 11})
        self.test_client.find_container_id_by_name.assert_called_once_with(container_name="Top")

    def test_recurse_collect_container_nodes(self):
        """Validate functionality of recurse_collect_container_nodes() finding Orion.Nodes EntityType."""

        self.test_client.query = MagicMock()
        self.test_client.query.side_effect = [
            {
                "results": [
                    {"Name": "Room01", "MemberEntityType": "Orion.Groups", "MemberPrimaryID": 20},
                    {"Name": "DistroSwitch01", "MemberEntityType": "Orion.Nodes", "MemberPrimaryID": 21},
                ]
            },
            {"results": [{"Name": "Room01-Router", "MemberEntityType": "Orion.Nodes", "MemberPrimaryID": 30}]},
        ]

        result = self.test_client.recurse_collect_container_nodes(current_container_id=1)

        self.job.logger.debug.assert_called_once_with("Exploring container: Room01 CID: 20")
        self.assertEqual(
            result,
            [
                {"Name": "Room01-Router", "MemberEntityType": "Orion.Nodes", "MemberPrimaryID": 30},
                {"Name": "DistroSwitch01", "MemberEntityType": "Orion.Nodes", "MemberPrimaryID": 21},
            ],
        )

    def test_find_container_id_by_name_success(self):
        """Validate successful functionality of find_container_id_by_name() finding container ID by name."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {"results": [{"ContainerID": 1}]}
        results = self.test_client.find_container_id_by_name(container_name="Test")
        self.assertEqual(results, 1)
        self.test_client.query.assert_called_once_with("SELECT ContainerID FROM Orion.Container WHERE Name = 'Test'")

    def test_find_container_id_by_name_failure(self):
        """Validate failure functionality of find_container_id_by_name() finding container ID by name."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {"results": []}
        results = self.test_client.find_container_id_by_name(container_name="Test")
        self.assertEqual(results, -1)

    def test_build_node_details(self):
        """Validate functionality of build_node_details()."""
        self.test_client.batch_fill_node_details = MagicMock()
        self.test_client.get_node_prefix_length = MagicMock()
        self.test_client.gather_interface_data = MagicMock()
        self.test_client.gather_ipaddress_data = MagicMock()
        result = self.test_client.build_node_details(nodes=self.test_nodes)

        self.test_client.batch_fill_node_details.assert_called_once_with(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.test_client.get_node_prefix_length.assert_called_once_with(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.job.logger.info.assert_called_once_with("Loading interface details for nodes.")
        self.test_client.gather_interface_data.assert_called_once_with(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.test_client.gather_ipaddress_data.assert_called_once_with(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.assertEqual(result, self.node_details)

    def test_batch_fill_node_details_success(self):
        """Validate successful functionality of batch_fill_node_details() to fill in node details."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {
            "results": [
                {
                    "NodeID": 1,
                    "Version": "v1",
                    "IPAddress": "192.168.1.1",
                    "SNMPLocation": "",
                    "Vendor": "Cisco",
                    "DeviceType": "Cisco Catalyst 3560-G24TS",
                    "Model": "WS-C3560G-24TS-S",
                    "ServiceTag": "",
                }
            ]
        }
        self.test_client.batch_fill_node_details(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.job.logger.debug.assert_called_once_with("Processing batch 1 of 1 - Orion.Nodes.")
        self.test_client.query.assert_called_once_with(
            "\n                SELECT IOSVersion AS Version,\n                o.IPAddress,\n                Location AS SNMPLocation,\n                o.Vendor,\n                MachineType AS DeviceType,\n                IOSImage,\n                h.Model,\n                h.ServiceTag,\n                o.NodeID\n                FROM Orion.Nodes o LEFT JOIN Orion.HardwareHealth.HardwareInfo h ON o.NodeID = h.NodeID\n                WHERE NodeID IN (\n            '1','2')"
        )
        self.assertEqual(
            self.node_details,
            {
                1: {
                    "NodeHostname": "Router01",
                    "NodeID": 1,
                    "Version": "v1",
                    "IPAddress": "192.168.1.1",
                    "SNMPLocation": "",
                    "Vendor": "Cisco",
                    "DeviceType": "Cisco Catalyst 3560-G24TS",
                    "Model": "WS-C3560G-24TS-S",
                    "ServiceTag": "",
                    "PFLength": 32,
                },
                2: {"NodeHostname": "Switch01", "NodeID": 2},
            },
        )

    def test_batch_fill_node_details_failure(self):
        """Validate functionality of batch_fill_node_details() when no information is returned."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {"results": []}
        self.test_client.batch_fill_node_details(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.job.logger.error.assert_called_once_with("Error: No node details found for the batch of nodes")

    def test_get_node_prefix_length_success(self):
        """Validate functionality of get_node_prefix_length() when data returned."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {"results": [{"NodeID": 1, "PFLength": 32}]}
        self.test_client.get_node_prefix_length(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.job.logger.debug.assert_called_once_with("Processing batch 1 of 1 - IPAM.IPInfo.")
        self.test_client.query.assert_called_once_with(
            "SELECT i.CIDR AS PFLength, o.NodeID FROM Orion.Nodes o JOIN IPAM.IPInfo i ON o.IPAddressGUID = i.IPAddressN WHERE o.NodeID IN ('1','2')"
        )
        self.assertEqual(
            self.node_details,
            {
                1: {
                    "NodeHostname": "Router01",
                    "NodeID": 1,
                    "PFLength": 32,
                },
                2: {"NodeHostname": "Switch01", "NodeID": 2},
            },
        )

    def test_get_node_prefix_length_failure(self):
        """Validate functionality of get_node_prefix_length() when no information is returned."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {"results": []}
        self.test_client.get_node_prefix_length(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.job.logger.error.assert_called_once_with("Error: No node details found for the batch of nodes")

    def test_gather_interface_data_success(self):
        """Validate functionality of gather_interface_data() when data is returned."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {
            "results": [
                {
                    "NodeID": 1,
                    "Name": "TenGigabitEthernet0/0/0",
                    "Enabled": "Up",
                    "Status": "Up",
                    "TypeName": "ethernetCsmacd",
                    "Speed": 10000000000.0,
                    "MAC": "DE68F1A6C467",
                    "MTU": 1500,
                },
                {
                    "NodeID": 1,
                    "Name": "TenGigabitEthernet0/0/1",
                    "Enabled": "Up",
                    "Status": "Up",
                    "TypeName": "ethernetCsmacd",
                    "Speed": 10000000000.0,
                    "MAC": "DE68F1A6C468",
                    "MTU": 1500,
                },
            ]
        }
        expected = {
            1: {
                "NodeHostname": "Router01",
                "NodeID": 1,
                "interfaces": {
                    "TenGigabitEthernet0/0/0": {
                        "Name": "TenGigabitEthernet0/0/0",
                        "Enabled": "Up",
                        "Status": "Up",
                        "TypeName": "ethernetCsmacd",
                        "Speed": 10000000000.0,
                        "MAC": "DE68F1A6C467",
                        "MTU": 1500,
                    },
                    "TenGigabitEthernet0/0/1": {
                        "Name": "TenGigabitEthernet0/0/1",
                        "Enabled": "Up",
                        "Status": "Up",
                        "TypeName": "ethernetCsmacd",
                        "Speed": 10000000000.0,
                        "MAC": "DE68F1A6C468",
                        "MTU": 1500,
                    },
                },
            },
            2: {"NodeHostname": "Switch01", "NodeID": 2},
        }
        self.test_client.gather_interface_data(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.test_client.query.assert_called_once_with(
            "\n                SELECT n.NodeID,\n                    sa.StatusName AS Enabled,\n                    so.StatusName AS Status,\n                    i.Name,\n                    i.MAC,\n                    i.Speed,\n                    i.TypeName,\n                    i.MTU\n                FROM Orion.Nodes n JOIN Orion.NPM.Interfaces i ON n.NodeID = i.NodeID INNER JOIN Orion.StatusInfo sa ON i.AdminStatus = sa.StatusId INNER JOIN Orion.StatusInfo so ON i.OperStatus = so.StatusId\n                WHERE n.NodeID IN (\n                '1','2')"
        )
        self.assertEqual(self.node_details, expected)

    def test_gather_interface_data_failure(self):
        """Validate functionality of gather_interface_data() when no information is returned."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {"results": []}
        self.test_client.gather_interface_data(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.job.logger.error.assert_called_once_with("Error: No node details found for the batch of nodes")

    node_types = [
        (
            "catalyst",
            {
                "Vendor": "Cisco",
                "DeviceType": "Catalyst 9500-48Y4C",
                "Model": "C9500-48Y4C",
            },
            "WS-C9500-48Y4C",
        ),
        (
            "blank_model",
            {"Vendor": "Cisco", "DeviceType": "Cisco Catalyst 3560CG-8PC-S", "Model": ""},
            "WS-C3560CG-8PC-S",
        ),
        (
            "space_model",
            {"Vendor": "Cisco", "DeviceType": "Cisco Catalyst 4500X-32 SFP+ Switch", "Model": " "},
            "WS-C4500X-32 SFP+ Switch",
        ),
        ("both_blank", {"Vendor": "Cisco", "DeviceType": "", "Model": ""}, ""),
        (
            "ignore_wireless",
            {"Vendor": "Cisco", "DeviceType": "Cisco 8540 Wireless Series Controllers", "Model": ""},
            "8540 Wireless Series Controllers",
        ),
        (
            "ignore_wlc",
            {"Vendor": "Cisco", "DeviceType": "Cisco 8500 WLC", "Model": ""},
            "8500 WLC",
        ),
        (
            "ignore_asr",
            {"Vendor": "Cisco", "DeviceType": "Cisco ASR 9901", "Model": ""},
            "ASR 9901",
        ),
        (
            "ignore_ws-",
            {"Vendor": "Cisco", "DeviceType": "Cisco WS-C3850-48U-S", "Model": ""},
            "WS-C3850-48U-S",
        ),
    ]

    @parameterized.expand(node_types, skip_on_empty=True)
    def test_standardize_device_type(self, name, sent, received):  # pylint: disable=unused-argument
        """Validate functionality of standardize_device_type()."""
        result = self.test_client.standardize_device_type(node=sent)
        self.assertEqual(result, received)

    intf_types = [
        ("standard_tengig", {"TypeName": "ethernetCsmacd", "Name": "TenGigabitEthernet0/0/0"}, "10gbase-t"),
        ("ethernet_speed", {"TypeName": "ethernetCsmacd", "Name": "Ethernet0/0", "Speed": 100000000.0}, "100base-tx"),
        ("virtual", {"TypeName": "propVirtual", "Name": "PortChannel10"}, "virtual"),
    ]

    @parameterized.expand(intf_types, skip_on_empty=True)
    def test_determine_interface_type(self, name, sent, received):  # pylint: disable=unused-argument
        """Validate functionality of determine_interface_type()."""
        result = self.test_client.determine_interface_type(interface=sent)
        self.assertEqual(result, received)

    def test_determine_interface_type_failure(self):
        """Validate functionality of determine_interface_type() when can't determine type."""
        test_intf = {"TypeName": "ethernetCsmacd", "Name": "Management", "Speed": 1.0}
        result = self.test_client.determine_interface_type(interface=test_intf)
        self.assertEqual(result, "virtual")
        self.job.logger.debug.assert_called_once_with("Unable to find Ethernet interface in map: Management")

    test_versions = [
        ("release_software", "17.6.5, RELEASE SOFTWARE (fc2)", "17.6.5"),
        ("copyright_software", "4.2(2f), Copyright (c) 2008-2022, Cisco Systems, Inc.", "4.2(2f)"),
        ("release_no_comma", "03.11.01.E RELEASE SOFTWARE (fc4)", "03.11.01.E"),
        ("copyright_no_comma", "4.0(4b) Copyright (c) 2008-2019, Cisco Systems, Inc.", "4.0(4b)"),
    ]

    @parameterized.expand(test_versions, skip_on_empty=True)
    def test_extract_version(self, name, sent, received):  # pylint: disable=unused-argument
        """Validate functionality of the extract_version() method."""
        result = self.test_client.extract_version(version=sent)
        self.assertEqual(result, received)

    def test_gather_ipaddress_data_success(self):
        """Validate functionality of gather_ipaddress_data() when data is returned."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {
            "results": [
                {
                    "NodeID": 1,
                    "IPAddress": "10.0.0.1",
                    "IPAddressType": "IPv4",
                    "Name": "Ethernet0/1",
                    "SubnetMask": "",
                },
                {
                    "NodeID": 1,
                    "IPAddress": "2001:db8:::",
                    "IPAddressType": "IPv6",
                    "Name": "Ethernet0/2",
                    "SubnetMask": 32,
                },
                {
                    "NodeID": 2,
                    "IPAddress": "192.168.0.1",
                    "IPAddressType": "IPv4",
                    "Name": "GigabitEthernet0/1",
                    "SubnetMask": "255.255.255.0",
                },
            ]
        }
        expected = {
            1: {
                "NodeHostname": "Router01",
                "NodeID": 1,
                "ipaddrs": {
                    "10.0.0.1": {
                        "IPAddress": "10.0.0.1",
                        "SubnetMask": 32,
                        "IPAddressType": "IPv4",
                        "IntfName": "Ethernet0/1",
                    },
                    "2001:db8:::": {
                        "IPAddress": "2001:db8:::",
                        "SubnetMask": 128,
                        "IPAddressType": "IPv6",
                        "IntfName": "Ethernet0/2",
                    },
                },
            },
            2: {
                "NodeHostname": "Switch01",
                "NodeID": 2,
                "ipaddrs": {
                    "192.168.0.1": {
                        "IPAddress": "192.168.0.1",
                        "SubnetMask": 24,
                        "IPAddressType": "IPv4",
                        "IntfName": "GigabitEthernet0/1",
                    }
                },
            },
        }
        self.test_client.gather_ipaddress_data(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.test_client.query.assert_called_once_with(
            "\n                SELECT NIPA.NodeID,\n                    NIPA.InterfaceIndex,\n                    NIPA.IPAddress,\n                    NIPA.IPAddressType,\n                    NPMI.Name,\n                    NIPA.SubnetMask\n                    FROM Orion.NodeIPAddresses NIPA INNER JOIN Orion.NPM.Interfaces NPMI ON NIPA.NodeID=NPMI.NodeID AND NIPA.InterfaceIndex=NPMI.InterfaceIndex INNER JOIN Orion.Nodes N ON NIPA.NodeID=N.NodeID\n                    WHERE NIPA.NodeID IN (\n                '1','2')"
        )
        self.assertEqual(self.node_details, expected)

    def test_gather_ipaddress_data_failure(self):
        """Validate functionality of gather_ipaddress_data() when no information is returned."""
        self.test_client.query = MagicMock()
        self.test_client.query.return_value = {"results": []}
        self.test_client.gather_ipaddress_data(
            node_data=self.test_nodes, node_details=self.node_details, nodes_per_batch=10
        )
        self.job.logger.error.assert_called_once_with("Error: No node details found for the batch of nodes")

    def test_determine_role_from_devicetype_success(self):
        """Validate successful functionality of determine_role_from_devicetype()."""
        result = determine_role_from_devicetype(device_type="ASR1001", role_map={"ASR1001": "Router"})
        self.assertEqual(result, "Router")

    def test_determine_role_from_devicetype_failure(self):
        """Validate functionality of determine_role_from_devicetype() when match isn't found."""
        result = determine_role_from_devicetype(device_type="Cat3k", role_map={"ASR1001": "Router"})
        self.assertEqual(result, "")

    def test_determine_role_from_hostname_success(self):
        """Validate successful functionality of determine_role_from_hostname()."""
        result = determine_role_from_hostname(hostname="core-router.test.com", role_map={".*router.*": "Router"})
        self.assertEqual(result, "Router")

    def test_determine_role_from_hostname_failure(self):
        """Validate functionality of determine_role_from_hostname() when match not found."""
        result = determine_role_from_hostname(hostname="distro-switch.test.com", role_map={".*router.*": "Router"})
        self.assertEqual(result, "")
