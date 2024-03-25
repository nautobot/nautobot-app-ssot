"""Tests of CloudVision utility methods."""

from unittest.mock import MagicMock
from unittest.mock import patch

from cloudvision.Connector.codec.custom_types import FrozenDict
from django.test import override_settings
from nautobot.core.testing import TestCase
from parameterized import parameterized

from nautobot_ssot.integrations.aristacv.utils import cloudvision
from nautobot_ssot.integrations.aristacv.utils.nautobot import get_config
from nautobot_ssot.tests.aristacv.fixtures import fixtures


class TestCloudvisionApi(TestCase):
    """Test CloudVision Api client and methods."""

    databases = ("default", "job_logs")

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvp_host": "localhost",
                "aristacv_verify": True,
            },
        },
    )
    def test_auth_failure_exception(self):
        """Test that AuthFailure is thrown when no credentials are passed."""
        config = get_config()
        with self.assertRaises(cloudvision.AuthFailure):
            cloudvision.CloudvisionApi(config)  # nosec

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvaas_url": "www.arista.io:443",
                "aristacv_cvp_token": "1234567890abcdef",
            },
        },
    )
    def test_auth_cvass_with_token(self):
        """Test that authentication against CVaaS with token works."""
        config = get_config()
        cloudvision.CloudvisionApi(config)
        self.assertEqual(config.url, "https://www.arista.io:443")
        self.assertEqual(config.token, "1234567890abcdef")


class TestCloudvisionUtils(TestCase):
    """Test CloudVision utility methods."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Setup mock CloudVision client."""
        self.client = MagicMock()

    def test_get_all_devices(self):
        """Test get_devices function for active and inactive devices."""
        device1 = MagicMock()
        device1.value.key.device_id.value = "JPE12345678"
        device1.value.hostname.value = "ams01-edge-01.ntc.com"
        device1.value.fqdn.value = "ams01-edge-01.ntc.com"
        device1.value.software_version.value = "4.26.5M"
        device1.value.streaming_status = 2
        device1.value.model_name.value = "DCS-7280CR2-60"
        device1.value.system_mac_address.value = "12:34:56:78:ab:cd"

        device2 = MagicMock()
        device2.value.key.device_id.value = "JPE12345679"
        device2.value.hostname.value = "ams01-edge-02.ntc.com"
        device2.value.fqdn.value = "ams01-edge-02.ntc.com"
        device2.value.software_version.value = "4.26.5M"
        device2.value.streaming_status = 2
        device2.value.model_name.value = "DCS-7280CR2-60"
        device2.value.system_mac_address.value = "12:34:56:78:ab:ce"

        device_list = [device1, device2]

        device_svc_stub = MagicMock()
        device_svc_stub.DeviceServiceStub.return_value.GetAll.return_value = device_list

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.services", device_svc_stub):
            results = cloudvision.get_devices(client=self.client, import_active=False)
        expected = fixtures.DEVICE_FIXTURE
        self.assertEqual(results, expected)

    def test_get_active_devices(self):
        """Test get_devices function for active devices."""
        device1 = MagicMock()
        device1.value.key.device_id.value = "JPE12345678"
        device1.value.hostname.value = "ams01-edge-01.ntc.com"
        device1.value.fqdn.value = "ams01-edge-01.ntc.com"
        device1.value.software_version.value = "4.26.5M"
        device1.value.streaming_status = 2
        device1.value.model_name.value = "DCS-7280CR2-60"
        device1.value.system_mac_address.value = "12:34:56:78:ab:cd"

        device_list = [device1]

        device_svc_stub = MagicMock()
        device_svc_stub.DeviceServiceStub.return_value.GetAll.return_value = device_list

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.services", device_svc_stub):
            results = cloudvision.get_devices(client=self.client, import_active=True)
        expected = [
            {
                "device_id": "JPE12345678",
                "hostname": "ams01-edge-01.ntc.com",
                "fqdn": "ams01-edge-01.ntc.com",
                "status": "Active",
                "sw_ver": "4.26.5M",
                "model": "DCS-7280CR2-60",
                "system_mac_address": "12:34:56:78:ab:cd",
            }
        ]
        self.assertEqual(results, expected)

    def test_get_tags_by_type(self):
        """Test get_tags_by_type method."""

        mock_tag = MagicMock()
        mock_tag.value.key.label.value = "test"
        mock_tag.value.key.value.value = "test"
        mock_tag.value.creator_type = 1

        device_tag_stub = MagicMock()
        device_tag_stub.TagServiceStub.return_value.GetAll.return_value = [mock_tag]

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.tag_services", device_tag_stub):
            results = cloudvision.get_tags_by_type(client=self.client)
        expected = [{"label": "test", "value": "test"}]
        self.assertEqual(results, expected)

    def test_get_device_tags(self):
        """Test get_device_tags method."""
        mock_tag = MagicMock()
        mock_tag.value.key.label.value = "ztp"
        mock_tag.value.key.value.value = "enabled"
        mock_tag.value.device_id.value = "JPE12345678"

        tag_stub = MagicMock()
        tag_stub.TagAssignmentServiceStub.return_value.GetAll.return_value = [
            mock_tag
        ]  # credit to @Eric-Jckson in https://github.com/nautobot/nautobot-plugin-ssot-arista-cloudvision/pull/164 for update to get_device_tags()

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.tag_services", tag_stub):
            results = cloudvision.get_device_tags(client=self.client, device_id="JPE12345678")
        expected = [{"label": "ztp", "value": "enabled"}]
        self.assertEqual(results, expected)

    def test_unfreeze_frozen_dict(self):
        """Test the unfreeze_frozen_dict method."""
        test_dict = {"test": "test"}
        test_frozen = FrozenDict({"test2": "test2"})

        frozen_result = cloudvision.unfreeze_frozen_dict(frozen_dict=(test_dict, test_frozen))
        self.assertEqual(frozen_result, [{"test": "test"}, {"test2": "test2"}])

        set_result = cloudvision.unfreeze_frozen_dict(frozen_dict="test")
        self.assertEqual(set_result, ("test"))

    def test_get_device_type_modular(self):
        """Test the get_device_type method for modular chassis."""
        mock_query = MagicMock()
        mock_query.return_value = {"fixedSystem": None}

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.unfreeze_frozen_dict", mock_query):
            results = cloudvision.get_device_type(client=self.client, dId="JPE12345678")
        self.assertEqual(results, "modular")

    def test_get_device_type_fixed(self):
        """Test the get_device_type method for fixed type."""
        mock_query = MagicMock()
        mock_query.return_value = {"fixedSystem": True}

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.unfreeze_frozen_dict", mock_query):
            results = cloudvision.get_device_type(client=self.client, dId="JPE12345678")
        self.assertEqual(results, "fixedSystem")

    def test_get_device_type_unknown(self):
        """Test the get_device_type method for unknown type."""
        mock_query = MagicMock()
        mock_query.return_value = {}

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.unfreeze_frozen_dict", mock_query):
            results = cloudvision.get_device_type(client=self.client, dId="JPE12345678")
        self.assertEqual(results, "Unknown")

    def test_get_interfaces_fixed(self):
        """Test get_interfaces_fixed method."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\tinterface",
            "\304\006status",
            "\304\003eth",
            "\304\003phy",
            "\304\005slice",
            "\304\0011",
            "\304\nintfStatus",
            "\304\00\001",
        ]

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.FIXED_INTF_QUERY
            results = cloudvision.get_interfaces_fixed(client=self.client, dId="JPE12345678")
        expected = fixtures.FIXED_INTERFACE_FIXTURE
        self.assertEqual(results, expected)

    def test_get_interfaces_chassis(self):
        """Test get_interfaces_chassis method."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\tinterface",
            "\304\006status",
            "\304\003eth",
            "\304\003phy",
            "\304\005slice",
        ]

        mock_lc = MagicMock()
        mock_lc.return_value = {"Linecard1": None}

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.unfreeze_frozen_dict", mock_lc):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.CHASSIS_INTF_QUERY
            results = cloudvision.get_interfaces_chassis(client=self.client, dId="JPE12345678")

        expected = fixtures.CHASSIS_INTERFACE_FIXTURE
        self.assertEqual(results, expected)

    def test_get_interface_transceiver_eeprom(self):
        """Test the get_interface_transceiver method from eeprom."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\010hardware",
            "\304\006archer",
            "\304\004xcvr",
            "\304\006status",
            "\304\003all",
            "\304\tEthernet1",
        ]

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.TRANSCEIVER_EEPROM_QUERY
            results = cloudvision.get_interface_transceiver(
                client=self.client, dId="JPE12345678", interface="Ethernet1"
            )
        self.assertEqual(results, "40GBASE-PLR4")

    def test_get_interface_transceiver_local(self):
        """Test the get_interface_transceiver method from local interface."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345679"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\010hardware",
            "\304\006archer",
            "\304\004xcvr",
            "\304\006status",
            "\304\003all",
            "\304\tEthernet1",
        ]

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.TRANSCEIVER_LOCAL_QUERY
            results = cloudvision.get_interface_transceiver(
                client=self.client, dId="JPE12345678", interface="Ethernet1"
            )
        self.assertEqual(results, "xcvr1000BaseT")

    def test_get_interface_mode_trunk(self):
        """Test the get_interface_mode method for a trunk."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\010bridging",
            "\304\020switchIntfConfig",
            "\304\020switchIntfConfig",
            "\304\tEthernet1",
        ]

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.TRUNK_INTF_MODE_QUERY
            results = cloudvision.get_interface_mode(client=self.client, dId="JPE12345678", interface="Ethernet1")
        expected = "trunk"
        self.assertEqual(results, expected)

    def test_get_interface_mode_access(self):
        """Test the get_interface_mode method for a access."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\010bridging",
            "\304\020switchIntfConfig",
            "\304\020switchIntfConfig",
            "\304\tEthernet5",
        ]

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.ACCESS_INTF_MODE_QUERY
            results = cloudvision.get_interface_mode(client=self.client, dId="JPE12345678", interface="Ethernet5")
        expected = "access"
        self.assertEqual(results, expected)

    port_types = [
        ("built_in_gig", {"port_info": {}, "transceiver": "xcvr1000BaseT"}, "1000base-t"),
        ("build_in_10g_sr", {"port_info": {}, "transceiver": "xcvr10GBaseSr"}, "10gbase-x-xfp"),
        ("management_port", {"port_info": {"interface": "Management1"}, "transceiver": "Unknown"}, "1000base-t"),
        ("vlan_port", {"port_info": {"interface": "Vlan100"}, "transceiver": "Unknown"}, "virtual"),
        ("loopback_port", {"port_info": {"interface": "Loopback0"}, "transceiver": "Unknown"}, "virtual"),
        ("port_channel_port", {"port_info": {"interface": "Port-Channel10"}, "transceiver": "Unknown"}, "lag"),
        ("unknown_ethernet_port", {"port_info": {"interface": "Ethernet1"}, "transceiver": "Unknown"}, "other"),
    ]

    @parameterized.expand(port_types, skip_on_empty=True)
    def test_get_port_type(self, name, sent, received):  # pylint: disable=unused-argument
        """Test the get_port_type method."""
        self.assertEqual(
            cloudvision.get_port_type(port_info=sent["port_info"], transceiver=sent["transceiver"]), received
        )

    port_statuses = [
        ("active_port", {"link_status": "up", "oper_status": "up"}, "Active"),
        ("planned_port", {"link_status": "down", "oper_status": "up"}, "Planned"),
        ("maintenance_port", {"link_status": "down", "oper_status": "down"}, "Maintenance"),
        ("decommissioning_port", {"link_status": "up", "oper_status": "down"}, "Decommissioning"),
    ]

    @parameterized.expand(port_statuses, skip_on_empty=True)
    def test_get_interface_status(self, name, sent, received):  # pylint: disable=unused-argument
        """Test the get_interface_status method."""
        self.assertEqual(cloudvision.get_interface_status(port_info=sent), received)

    def test_get_interface_description(self):
        """Test get_interface_description method."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\tinterface",
            "\304\006config",
            "\304\003eth",
            "\304\003phy",
            "\304\005slice",
            "\304\0011",
            "\304\nintfStatus",
            "\304\tEthernet1",
        ]

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.INTF_DESCRIPTION_QUERY
            results = cloudvision.get_interface_description(
                client=self.client, dId="JPE12345678", interface="Ethernet1"
            )
        expected = "Uplink to DC1"
        self.assertEqual(results, expected)

    def test_get_ip_interfaces(self):
        """Test the get_ip_interfaces method."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"
        mock_query.paths.path_elements = [
            "\304\005Sysdb",
            "\304\002ip",
            "\304\006config",
            "\304\014ipIntfConfig",
            "\307\00\001",
        ]

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.IP_INTF_QUERY
            results = cloudvision.get_ip_interfaces(client=self.client, dId="JPE12345678")
        expected = fixtures.IP_INTF_FIXTURE
        self.assertEqual(results, expected)
