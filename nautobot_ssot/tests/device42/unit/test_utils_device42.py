"""Tests of Device42 utility methods."""

import json
from unittest.mock import patch

import responses
from nautobot.core.testing import TestCase
from parameterized import parameterized
from nautobot_ssot.integrations.device42.jobs import Device42DataSource
from nautobot_ssot.integrations.device42.utils import device42


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


class TestMissingConfigSetting(TestCase):
    """Test MissingConfigSetting Exception."""

    def setUp(self):
        """Setup MissingConfigSetting instance."""
        self.setting = "D42_URL"
        self.missing_setting = device42.MissingConfigSetting(setting=self.setting)

    def test_missingconfigsetting(self):
        self.assertTrue(self.missing_setting.setting == "D42_URL")
        self.assertLogs("Missing configuration setting - D42_URL!")


class TestUtilsDevice42(TestCase):
    """Test Device42 util methods."""

    databases = ("default", "job_logs")

    def test_merge_offset_dicts(self):
        first_dict = {"total_count": 10, "limit": 2, "offset": 2, "Objects": ["a", "b"]}
        second_dict = {"total_count": 10, "limit": 2, "offset": 4, "Objects": ["c", "d"]}
        result_dict = {"total_count": 10, "limit": 2, "offset": 4, "Objects": ["a", "b", "c", "d"]}
        self.assertEqual(device42.merge_offset_dicts(orig_dict=first_dict, offset_dict=second_dict), result_dict)

    def test_get_intf_type_eth_intf(self):
        # test physical Ethernet interfaces
        eth_intf = {
            "port_name": "GigabitEthernet0/1",
            "port_type": "physical",
            "discovered_type": "ethernetCsmacd",
            "port_speed": "1.0 Gbps",
        }
        self.assertEqual(device42.get_intf_type(intf_record=eth_intf), "1000base-t")

    def test_get_intf_type_fc_intf(self):
        # test physical FiberChannel interfaces
        fc_intf = {
            "port_name": "FC0/1",
            "port_type": "physical",
            "discovered_type": "fibreChannel",
            "port_speed": "1.0 Gbps",
            "device_name": "core-router.testexample.com",
        }
        self.assertEqual(device42.get_intf_type(intf_record=fc_intf), "1gfc-sfp")

    def test_get_intf_type_unknown_phy_intf(self):
        # test physical interfaces that don't have a discovered_type of Ethernet or FiberChannel
        unknown_phy_intf_speed = {
            "port_name": "Ethernet0/1",
            "port_type": "physical",
            "discovered_type": "Unknown",
            "port_speed": "1.0 Gbps",
        }
        self.assertEqual(device42.get_intf_type(intf_record=unknown_phy_intf_speed), "1000base-t")

    @patch.object(Device42DataSource, "debug", True)
    def test_get_intf_name_mapping(self):
        # test name of Interface matching INTF_NAME_MAP
        ethernet_interface = {
            "port_name": "FastEthernet1/1",
            "port_type": "physical",
            "discovered_type": "ethernetCsmacd",
            "port_speed": "10 Mbps",
        }
        self.assertEqual(device42.get_intf_type(intf_record=ethernet_interface), "100base-tx")

    def test_get_intf_type_gigabit_ethernet_intf(self):
        # test physical interface that's discovered as gigabitEthernet
        gigabit_ethernet_intf = {
            "port_name": "Vethernet100",
            "port_type": "physical",
            "discovered_type": "gigabitEthernet",
            "port_speed": "0",
        }
        self.assertEqual(device42.get_intf_type(intf_record=gigabit_ethernet_intf), "1000base-t")

    def test_get_intf_type_dot11_intf(self):
        # test physical interface discoverd as dot11a/b
        dot11_intf = {
            "port_name": "01:23:45:67:89:AB.0",
            "port_type": "physical",
            "discovered_type": "dot11b",
            "port_speed": None,
        }
        self.assertEqual(device42.get_intf_type(intf_record=dot11_intf), "ieee802.11a")

    def test_get_intf_type_ad_lag_intf(self):
        # test 802.3ad lag logical interface
        ad_lag_intf = {
            "port_name": "port-channel100",
            "port_type": "logical",
            "discovered_type": "ieee8023adLag",
            "port_speed": "100 Mbps",
            "device_name": "core-router.testexample.com",
        }
        self.assertEqual(device42.get_intf_type(intf_record=ad_lag_intf), "lag")

    def test_get_intf_type_lacp_intf(self):
        # test lacp logical interface
        lacp_intf = {
            "port_name": "Internal_Trunk",
            "port_type": "logical",
            "discovered_type": "lacp",
            "port_speed": "40 Gbps",
            "device_name": "core-router.testexample.com",
        }
        self.assertEqual(device42.get_intf_type(intf_record=lacp_intf), "lag")

    def test_get_intf_type_virtual_intf(self):
        # test "virtual" logical interface
        virtual_intf = {
            "port_name": "Vlan100",
            "port_type": "logical",
            "discovered_type": "propVirtual",
            "port_speed": "1.0 Gbps",
            "device_name": "distro-switch.testexample.com",
        }
        self.assertEqual(device42.get_intf_type(intf_record=virtual_intf), "virtual")

    def test_get_intf_type_port_channel_intf(self):
        # test Port-Channel logical interface
        port_channel_intf = {
            "port_name": "port-channel100",
            "port_type": "logical",
            "discovered_type": "propVirtual",
            "port_speed": "20 Gbps",
            "device_name": "distro-switch.testexample.com",
        }
        self.assertEqual(device42.get_intf_type(intf_record=port_channel_intf), "lag")

    port_statuses = [
        ("Active", {"up": True, "up_admin": True}, "Active"),
        ("Decommissioning", {"up": False, "up_admin": False}, "Decommissioning"),
        ("Failed", {"up": False, "up_admin": True}, "Failed"),
        ("Planned", {}, "Planned"),
        ("up_admin", {"up_admin": True}, "Active"),
    ]

    @parameterized.expand(port_statuses, skip_on_empty=True)
    def test_get_intf_status(self, name, sent, received):  # pylint: disable=unused-argument
        self.assertEqual(device42.get_intf_status(sent), received)

    netmiko_platforms = [
        ("asa", "asa", "cisco_asa"),
        ("ios", "ios", "cisco_ios"),
        ("iosxe", "iosxe", "cisco_ios"),
        ("iosxr", "iosxr", "cisco_xr"),
        ("nxos", "nxos", "cisco_nxos"),
        ("junos", "junos", "juniper_junos"),
        ("dell", "dell", "dell"),
    ]

    @parameterized.expand(netmiko_platforms, skip_on_empty=True)
    def test_get_netmiko_platform(self, name, sent, received):  # pylint: disable=unused-argument
        self.assertEqual(device42.get_netmiko_platform(sent), received)

    @patch(
        "nautobot_ssot.integrations.device42.utils.device42.PLUGIN_CFG",
        {"device42_role_prepend": "nautobot-"},
    )
    def test_find_device_role_from_tags(self):
        tags_w_role = [
            "core-router",
            "nautobot-core-router",
        ]
        self.assertEqual(device42.find_device_role_from_tags(tag_list=tags_w_role), "core-router")
        tags_missing_role = [
            "802.1x",
        ]
        self.assertEqual(device42.find_device_role_from_tags(tag_list=tags_missing_role), "Unknown")

    @patch(
        "nautobot_ssot.integrations.device42.utils.device42.PLUGIN_CFG",
        {"device42_facility_prepend": "sitecode-"},
    )
    def test_get_facility(self):
        tags = ["core-router", "nautobot-core-router", "sitecode-DFW"]
        self.assertEqual(device42.get_facility(tags=tags), "DFW")

    def test_get_custom_field_dict(self):
        """Test the get_custom_field_dict method."""
        expected = {
            "Test": {
                "key": "Test",
                "value": None,
                "notes": None,
            }
        }
        mock_custom_fields = [{"key": "Test", "value": None, "notes": None}]
        actual = device42.get_custom_field_dict(cfields=mock_custom_fields)
        self.assertEqual(actual, expected)


class TestDevice42Api(TestCase):  # pylint: disable=too-many-public-methods
    """Test Base Device42 API Client and Calls."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Setup Device42API instance."""
        self.uri = "https://device42.testexample.com"
        self.username = "testuser"
        self.password = "testpassword"  # nosec B105
        self.verify = False
        self.dev42 = device42.Device42API(self.uri, self.username, self.password, self.verify)

    def test_validate_url(self):
        """Test validate_url success."""
        validate_url = self.dev42.validate_url("api_endpoint")
        self.assertEqual(validate_url, "https://device42.testexample.com/api_endpoint")

    def test_validate_url_missing_extra_slash(self):
        """Test validate_url success with missing '/'."""
        # Instantiate a new object, to test additional logic for missing'/':
        self.uri = "https://device42.testexample.com"
        self.dev42 = device42.Device42API(self.uri, self.username, self.password, self.verify)
        validate_url = self.dev42.validate_url("api_endpoint")
        self.assertEqual(validate_url, "https://device42.testexample.com/api_endpoint")

    def test_validate_url_path_has_slash(self):
        """Test validate_url success when path has '/'."""
        # Instantiate a new object, to test additional logic for missing'/':
        self.uri = "https://device42.testexample.com"
        self.dev42 = device42.Device42API(self.uri, self.username, self.password, self.verify)
        validate_url = self.dev42.validate_url("/api_endpoint")
        self.assertEqual(validate_url, "https://device42.testexample.com/api_endpoint")

    def test_validate_url_verify_true(self):
        """Test validate_url success with verify true."""
        # Instantiate a new object, to test additional logic for verify True
        self.dev42 = device42.Device42API(self.uri, self.username, self.password, verify=True)
        validate_url = self.dev42.validate_url("api_endpoint")
        self.assertEqual(validate_url, "https://device42.testexample.com/api_endpoint")

    @responses.activate
    def test_get_buildings(self):
        """Test get_buildings success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_buildings.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/api/1.0/buildings",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_buildings_recv.json")
        response = self.dev42.get_buildings()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_building_pks(self):
        """Test get_building_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_building_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT * FROM view_building_v1&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open("./nautobot_ssot/tests/device42/fixtures/get_building_pks_recv.json", "r", encoding="utf-8") as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_building_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_rooms(self):
        """Test get_rooms success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_rooms.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/api/1.0/rooms",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_rooms_recv.json")
        response = self.dev42.get_rooms()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_room_pks(self):
        """Test get_room_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_room_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT * FROM view_room_v1&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open("./nautobot_ssot/tests/device42/fixtures/get_room_pks_recv.json", "r", encoding="utf-8") as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_room_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_racks(self):
        """Test get_racks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_racks.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/api/1.0/racks",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_racks_recv.json")
        response = self.dev42.get_racks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_rack_pks(self):
        """Test get_room_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_rack_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT * FROM view_rack_v1&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open("./nautobot_ssot/tests/device42/fixtures/get_rack_pks_recv.json", "r", encoding="utf-8") as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_rack_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_vendors(self):
        """Test get_vendors success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_vendors_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/api/1.0/vendors",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_vendors_recv.json")
        response = self.dev42.get_vendors()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_hardware_models(self):
        """Test get_hardware_models success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_hardware_models_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/api/1.0/hardwares",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_hardware_models_recv.json")
        response = self.dev42.get_hardware_models()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_devices(self):
        """Test get_devices success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_devices_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/api/1.0/devices/all/?is_it_switch=yes&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_devices_recv.json")
        response = self.dev42.get_devices()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_cluster_members(self):
        """Test get_cluster_members success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_cluster_members_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT+m.name+as+cluster%2C+string_agg%28d.name%2C+%27%253B+%27%29+as+members%2C+h.name+as+hardware%2C+d.network_device%2C+d.os_name+as+os%2C+b.name+as+customer%2C+d.tags+FROM+view_device_v1+m+JOIN+view_devices_in_cluster_v1+c+ON+c.parent_device_fk+%3D+m.device_pk+JOIN+view_device_v1+d+ON+d.device_pk+%3D+c.child_device_fk+JOIN+view_hardware_v1+h+ON+h.hardware_pk+%3D+d.hardware_fk+JOIN+view_customer_v1+b+ON+b.customer_pk+%3D+d.customer_fk+WHERE+m.type+like+%27%25cluster%25%27+GROUP+BY+m.name%2C+h.name%2C+d.network_device%2C+d.os_name%2C+b.name%2C+d.tags&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_cluster_members_recv.json")
        response = self.dev42.get_cluster_members()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)
        self.assertTrue(
            responses.calls[0].request.url
            == "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT+m.name+as+cluster%2C+string_agg%28d.name%2C+%27%253B+%27%29+as+members%2C+h.name+as+hardware%2C+d.network_device%2C+d.os_name+as+os%2C+b.name+as+customer%2C+d.tags+FROM+view_device_v1+m+JOIN+view_devices_in_cluster_v1+c+ON+c.parent_device_fk+%3D+m.device_pk+JOIN+view_device_v1+d+ON+d.device_pk+%3D+c.child_device_fk+JOIN+view_hardware_v1+h+ON+h.hardware_pk+%3D+d.hardware_fk+JOIN+view_customer_v1+b+ON+b.customer_pk+%3D+d.customer_fk+WHERE+m.type+like+%27%25cluster%25%27+GROUP+BY+m.name%2C+h.name%2C+d.network_device%2C+d.os_name%2C+b.name%2C+d.tags&output_type=json&_paging=1&_return_as_object=1&_max_results=1000"
        )

    @responses.activate
    def test_get_ports_with_vlans(self):
        """Test get_ports_with_vlans success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_ports_with_vlans_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT array_agg( distinct concat (v.vlan_pk)) AS vlan_pks, n.netport_pk, n.port AS port_name, n.description, n.up, n.up_admin, n.discovered_type, n.hwaddress, n.port_type, n.port_speed, n.mtu, n.tags, n.second_device_fk, d.name AS device_name FROM view_vlan_v1 v LEFT JOIN view_vlan_on_netport_v1 vn ON vn.vlan_fk = v.vlan_pk LEFT JOIN view_netport_v1 n ON n.netport_pk = vn.netport_fk LEFT JOIN view_device_v1 d ON d.device_pk = n.device_fk WHERE n.port is not null GROUP BY n.netport_pk, n.port, n.description, n.up, n.up_admin, n.discovered_type, n.hwaddress, n.port_type, n.port_speed, n.mtu, n.tags, n.second_device_fk, d.name&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_ports_with_vlans_recv.json")
        response = self.dev42.get_ports_with_vlans()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_ports_wo_vlans(self):
        """Test get_ports_wo_vlans success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_ports_wo_vlans_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT m.netport_pk, m.port as port_name, m.description, m.up_admin, m.discovered_type, m.hwaddress, m.port_type, m.port_speed, m.mtu, m.tags, m.second_device_fk, d.name as device_name FROM view_netport_v1 m JOIN view_device_v1 d on d.device_pk = m.device_fk WHERE m.port is not null GROUP BY m.netport_pk, m.port, m.description, m.up_admin, m.discovered_type, m.hwaddress, m.port_type, m.port_speed, m.mtu, m.tags, m.second_device_fk, d.name&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_ports_wo_vlans_recv.json")
        response = self.dev42.get_ports_wo_vlans()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_port_default_custom_fields(self):
        """Test get_port_default_custom_fields success."""
        test_query = [
            {"key": "Software Version", "value": "10R.2D.2", "notes": None},
            {"key": "EOL Date", "value": "12/31/2999", "notes": None},
        ]
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes FROM view_netport_custom_fields_v1 cf&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = {
            "EOL Date": {"key": "EOL Date", "value": None, "notes": None},
            "Software Version": {"key": "Software Version", "value": None, "notes": None},
        }
        response = self.dev42.get_port_default_custom_fields()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_port_custom_fields(self):
        """Test get_port_custom_fields success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_port_custom_fields_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes, np.port as port_name, d.name as device_name FROM view_netport_custom_fields_v1 cf LEFT JOIN view_netport_v1 np ON np.netport_pk = cf.netport_fk LEFT JOIN view_device_v1 d ON d.device_pk = np.device_fk&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_port_custom_fields_recv.json")
        response = self.dev42.get_port_custom_fields()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_vrfgroups(self):
        """Test get_vrfgroups success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_vrfgroups_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/api/1.0/vrfgroup/?_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_vrfgroups_recv.json")
        response = self.dev42.get_vrfgroups()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_subnets(self):
        """Test get_subnets success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnets.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT s.name, s.network, s.mask_bits, s.tags, v.name as vrf FROM view_subnet_v1 s JOIN view_vrfgroup_v1 v ON s.vrfgroup_fk = v.vrfgroup_pk&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnets.json")
        response = self.dev42.get_subnets()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_subnet_default_custom_fields(self):
        """Test get_subnet_default_custom_fields success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnet_default_custom_fields_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes FROM view_subnet_custom_fields_v1 cf&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnet_default_custom_fields_recv.json")
        response = self.dev42.get_subnet_default_custom_fields()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_subnet_custom_fields(self):
        """Test get_subnet_custom_fields success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnet_custom_fields_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes, s.name AS subnet_name, s.network, s.mask_bits FROM view_subnet_custom_fields_v1 cf LEFT JOIN view_subnet_v1 s ON s.subnet_pk = cf.subnet_fk&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes FROM view_subnet_custom_fields_v1 cf&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_subnet_custom_fields_recv.json")
        response = self.dev42.get_subnet_custom_fields()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 2)

    @responses.activate
    def test_get_ip_addrs(self):
        """Test get_ip_addrs success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_ip_addrs.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT i.ip_address, i.available, i.label, i.tags, np.netport_pk, s.network as subnet, s.mask_bits as netmask, v.name as vrf FROM view_ipaddress_v1 i LEFT JOIN view_subnet_v1 s ON s.subnet_pk = i.subnet_fk LEFT JOIN view_netport_v1 np ON np.netport_pk = i.netport_fk LEFT JOIN view_vrfgroup_v1 v ON v.vrfgroup_pk = s.vrfgroup_fk WHERE s.mask_bits <> 0&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_ip_addrs.json")
        response = self.dev42.get_ip_addrs()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_ipaddr_default_custom_fields(self):
        """Test get_ipaddr_default_custom_fields success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_ipaddr_default_custom_fields_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes FROM view_ipaddress_custom_fields_v1 cf&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_ipaddr_default_custom_fields_recv.json")
        response = self.dev42.get_ipaddr_default_custom_fields()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_ipaddr_custom_fields(self):
        """Test get_ipaddr_custom_fields success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_ipaddr_custom_fields_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes, i.ip_address, s.mask_bits FROM view_ipaddress_custom_fields_v1 cf LEFT JOIN view_ipaddress_v1 i ON i.ipaddress_pk = cf.ipaddress_fk LEFT JOIN view_subnet_v1 s ON s.subnet_pk = i.subnet_fk&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_ipaddr_custom_fields_recv.json")
        response = self.dev42.get_ipaddr_custom_fields()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    def test_get_all_custom_fields(self):
        """Test get_all_custom_fields success."""
        test_sample = load_json("./nautobot_ssot/tests/device42/fixtures/get_all_custom_fields_sent.json")
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_all_custom_fields_recv.json")
        response = self.dev42.get_all_custom_fields(test_sample)
        self.assertEqual(response, expected)

    @responses.activate
    def test_get_vlans_with_location(self):
        """Test get_vlans_with_location success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_vlans_with_location.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT v.vlan_pk, v.number AS vid, v.description, v.tags, vn.vlan_name, b.name as building, c.name as customer FROM view_vlan_v1 v LEFT JOIN view_vlan_on_netport_v1 vn ON vn.vlan_fk = v.vlan_pk LEFT JOIN view_netport_v1 n on n.netport_pk = vn.netport_fk LEFT JOIN view_device_v2 d on d.device_pk = n.device_fk LEFT JOIN view_building_v1 b ON b.building_pk = d.building_fk LEFT JOIN view_customer_v1 c ON c.customer_pk = d.customer_fk WHERE vn.vlan_name is not null and v.number <> 0 GROUP BY v.vlan_pk, v.number, v.description, v.tags, vn.vlan_name, b.name, c.name&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_vlans_with_location.json")
        response = self.dev42.get_vlans_with_location()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_vlan_info(self):
        """Test get_vlan_info success."""
        vinfo_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_vlan_info_vlaninfo.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT v.vlan_pk, v.name, v.number as vid FROM view_vlan_v1 v&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=vinfo_query,
            status=200,
        )
        cfields_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_vlan_info_cfields.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT cf.key, cf.value, cf.notes, v.vlan_pk FROM view_vlan_custom_fields_v1 cf LEFT JOIN view_vlan_v1 v ON v.vlan_pk = cf.vlan_fk&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=cfields_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_vlan_info_recv.json")
        response = self.dev42.get_vlan_info()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 2)

    @responses.activate
    def test_get_device_pks(self):
        """Test get_device_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_device_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT name, device_pk FROM view_device_v1 WHERE name <> ''&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open("./nautobot_ssot/tests/device42/fixtures/get_device_pks_recv.json", "r", encoding="utf-8") as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_device_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_port_pks(self):
        """Test get_port_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_port_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT np.port, np.netport_pk, np.hwaddress, np.second_device_fk, d.name as device FROM view_netport_v1 np JOIN view_device_v1 d ON d.device_pk = np.device_fk&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open("./nautobot_ssot/tests/device42/fixtures/get_port_pks_recv.json", "r", encoding="utf-8") as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_port_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_port_connections(self):
        """Test get_port_connections success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_port_connections.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT netport_pk as src_port, device_fk as src_device, second_device_fk as second_src_device, remote_netport_fk as dst_port FROM view_netport_v1 WHERE device_fk is not null AND remote_netport_fk is not null&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_port_connections.json")
        response = self.dev42.get_port_connections()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_telcocircuits(self):
        """Test get_telcocircuits success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_telcocircuits.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT * FROM view_telcocircuit_v1&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_telcocircuits.json")
        response = self.dev42.get_telcocircuits()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_vendor_pks(self):
        """Test get_vendor_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_vendor_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT * FROM view_vendor_v1&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open("./nautobot_ssot/tests/device42/fixtures/get_vendor_pks_recv.json", "r", encoding="utf-8") as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_vendor_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_patch_panels(self):
        """Test get_patch_panels success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_patch_panels.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT+a.name%2C+a.in_service%2C+a.serial_no%2C+a.customer_fk%2C+a.building_fk%2C+a.calculated_building_fk%2C+a.room_fk%2C+a.calculated_room_fk%2C+a.calculated_rack_fk%2C+a.size%2C+a.depth%2C+m.number_of_ports%2C+m.name+as+model_name%2C+m.port_type_name+as+port_type%2C+v.name+as+vendor%2C+a.rack_fk%2C+a.start_at+as+position%2C+a.orientation+FROM+view_asset_v1+a+LEFT+JOIN+view_patchpanelmodel_v1+m+ON+m.patchpanelmodel_pk+%3D+a.patchpanelmodel_fk+JOIN+view_vendor_v1+v+ON+v.vendor_pk+%3D+m.vendor_fk+WHERE+a.patchpanelmodel_fk+is+not+null+AND+a.name+is+not+null&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        expected = load_json("./nautobot_ssot/tests/device42/fixtures/get_patch_panels.json")
        response = self.dev42.get_patch_panels()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_patch_panel_port_pks(self):
        """Test get_patch_panel_port_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_patch_panel_port_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT p.*, a.name FROM view_patchpanelport_v1 p JOIN view_asset_v1 a ON a.asset_pk = p.patchpanel_asset_fk&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open(
            "./nautobot_ssot/tests/device42/fixtures/get_patch_panel_port_pks_recv.json", "r", encoding="utf-8"
        ) as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_patch_panel_port_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)

    @responses.activate
    def test_get_customer_pks(self):
        """Test get_customer_pks success."""
        test_query = load_json("./nautobot_ssot/tests/device42/fixtures/get_customer_pks_sent.json")
        responses.add(
            responses.GET,
            "https://device42.testexample.com/services/data/v1.0/query/?query=SELECT * FROM view_customer_v1&output_type=json&_paging=1&_return_as_object=1&_max_results=1000",
            json=test_query,
            status=200,
        )
        with open("./nautobot_ssot/tests/device42/fixtures/get_customer_pks_recv.json", "r", encoding="utf-8") as file:
            json_data = file.read()
        expected = json.loads(json_data, object_hook=lambda d: {int(k) if k.isdigit() else k: v for k, v in d.items()})
        response = self.dev42.get_customer_pks()
        self.assertEqual(response, expected)
        self.assertTrue(len(responses.calls) == 1)
