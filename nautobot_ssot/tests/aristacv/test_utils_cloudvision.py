"""Tests of CloudVision utility methods."""

from unittest.mock import MagicMock, patch

from cloudvision.Connector.codec.custom_types import FrozenDict, Path
from cvprac.cvp_client import CvpLoginError
from django.test import override_settings
from nautobot.apps.testing import TestCase
from parameterized import parameterized

from nautobot_ssot.integrations.aristacv.utils import cloudvision
from nautobot_ssot.integrations.aristacv.utils.nautobot import get_config
from nautobot_ssot.tests.aristacv.fixtures import fixtures

CVAAS_PLUGIN_CONFIG = {
    "nautobot_ssot": {
        "aristacv_cvaas_url": "www.arista.io:443",
        "aristacv_cvp_token": "1234567890abcdef",
    },
}


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

    @override_settings(PLUGINS_CONFIG=CVAAS_PLUGIN_CONFIG)
    def test_auth_cvass_with_token(self):
        """Test that authentication against CVaaS with token works."""
        config = get_config()
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient"):
            cloudvision.CloudvisionApi(config)
        self.assertEqual(config.url, "https://www.arista.io:443")
        self.assertEqual(config.token, "1234567890abcdef")

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvp_host": "localhost",
                "aristacv_cvp_token": "1234567890abcdef",
                "aristacv_verify": True,
            },
        },
    )
    def test_auth_on_premise_with_token(self):
        """Test that on-premise authentication with a token passes the token to the REST client."""
        config = get_config()
        self.assertTrue(config.is_on_premise)
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient") as mock_cvp:
            cloudvision.CloudvisionApi(config)
            _, kwargs = mock_cvp.return_value.connect.call_args
            self.assertEqual(kwargs["api_token"], "1234567890abcdef")
            self.assertFalse(kwargs["is_cvaas"])

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvp_host": "localhost",
                "aristacv_cvp_user": "admin",
                "aristacv_cvp_password": "password",  # noqa: S106
                "aristacv_verify": True,
            },
        },
    )
    def test_auth_on_premise_with_user_password(self):
        """Test that on-premise authentication with user/password passes credentials to the REST client."""
        config = get_config()
        self.assertTrue(config.is_on_premise)
        with (
            patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient") as mock_cvp,
            patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.requests.post") as mock_post,
        ):
            mock_post.return_value.json.return_value = {"sessionId": "session-token"}
            cloudvision.CloudvisionApi(config)
            _, kwargs = mock_cvp.return_value.connect.call_args
            self.assertEqual(kwargs["username"], "admin")
            self.assertEqual(kwargs["password"], "password")
            self.assertFalse(kwargs["is_cvaas"])
            self.assertNotIn("api_token", kwargs)

    @override_settings(PLUGINS_CONFIG=CVAAS_PLUGIN_CONFIG)
    def test_get_version_returns_version_from_response(self):
        """get_version returns the value of the 'version' key from get_cvp_info()."""
        config = get_config()
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient") as mock_cvp:
            mock_cvp.return_value.api.get_cvp_info.return_value = {"version": "2024.3.0"}
            api = cloudvision.CloudvisionApi(config)
            self.assertEqual(api.get_version(), "2024.3.0")
            mock_cvp.return_value.connect.assert_called_once()

    @override_settings(PLUGINS_CONFIG=CVAAS_PLUGIN_CONFIG)
    def test_get_version_returns_blank_when_missing(self):
        """get_version returns '' when the response lacks a 'version' key."""
        config = get_config()
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient") as mock_cvp:
            mock_cvp.return_value.api.get_cvp_info.return_value = {}
            api = cloudvision.CloudvisionApi(config)
            self.assertEqual(api.get_version(), "")

    @override_settings(PLUGINS_CONFIG=CVAAS_PLUGIN_CONFIG)
    def test_get_inventory_passthrough(self):
        """get_inventory delegates to CvpClient.api.get_inventory()."""
        config = get_config()
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient") as mock_cvp:
            mock_cvp.return_value.api.get_inventory.return_value = fixtures.INVENTORY_FIXTURE
            api = cloudvision.CloudvisionApi(config)
            self.assertEqual(api.get_inventory(), fixtures.INVENTORY_FIXTURE)

    @override_settings(PLUGINS_CONFIG=CVAAS_PLUGIN_CONFIG)
    def test_rest_login_failure_wrapped_as_authfailure(self):
        """A CvpLoginError during connect is wrapped as AuthFailure."""
        config = get_config()
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient") as mock_cvp:
            mock_cvp.return_value.connect.side_effect = CvpLoginError("bad creds")
            with self.assertRaises(cloudvision.AuthFailure):
                cloudvision.CloudvisionApi(config)

    @override_settings(PLUGINS_CONFIG=CVAAS_PLUGIN_CONFIG)
    def test_get_cvp_version_emits_deprecation_warning(self):
        """The legacy get_cvp_version function emits DeprecationWarning."""
        config = get_config()
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.CvpClient") as mock_cvp:
            mock_cvp.return_value.api.get_cvp_info.return_value = {"version": "2024.3.0"}
            with self.assertWarns(DeprecationWarning):
                result = cloudvision.get_cvp_version(config)
            self.assertEqual(result, "2024.3.0")


# pylint: disable=too-many-public-methods
class TestCloudvisionUtils(TestCase):
    """Test CloudVision utility methods."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Setup mock CloudVision client."""
        self.client = MagicMock()

    def test_get_all_devices(self):
        """Test get_devices function for active and inactive devices."""
        device_list = []
        for entry in fixtures.DEVICE_FIXTURE:
            mock_dev = MagicMock()
            mock_dev.value.key.device_id.value = entry["device_id"]
            mock_dev.value.hostname.value = entry["hostname"]
            mock_dev.value.fqdn.value = entry["fqdn"]
            mock_dev.value.software_version.value = entry["sw_ver"]
            mock_dev.value.streaming_status = 2 if entry["status"] == "Active" else 0
            mock_dev.value.model_name.value = entry["model"]
            mock_dev.value.system_mac_address.value = entry["system_mac_address"]
            device_list.append(mock_dev)

        device_svc_stub = MagicMock()
        device_svc_stub.DeviceServiceStub.return_value.GetAll.return_value = device_list

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.services", device_svc_stub):
            results = cloudvision.get_devices(client=self.client, logger=MagicMock(), import_active=False)
        self.assertEqual(results, fixtures.DEVICE_FIXTURE)

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
            results = cloudvision.get_devices(client=self.client, logger=MagicMock(), import_active=True)
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
            results = cloudvision.get_tags_by_type(client=self.client, logger=MagicMock())
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

    def test_unpath(self):
        """Test that unpath converts Path values into plain lists while leaving other types alone."""
        path = Path(("Sysdb", "interface", "config", "eth", "lag", "intfConfig", "Port-Channel1000"))
        nested = FrozenDict({"intfId": "Ethernet53/1", "lag": path, "mode": FrozenDict({"Name": "lacpModeActive"})})

        result = cloudvision.unpath(nested)
        self.assertEqual(
            result,
            {
                "intfId": "Ethernet53/1",
                "lag": ["Sysdb", "interface", "config", "eth", "lag", "intfConfig", "Port-Channel1000"],
                "mode": {"Name": "lacpModeActive"},
            },
        )
        # Already-plain structures must round-trip unchanged.
        already_plain = {"a": [1, 2, {"b": "c"}]}
        self.assertEqual(cloudvision.unpath(already_plain), already_plain)

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

    def test_get_interfaces_fixed_multi_notification_batch(self):
        """Test that get_interfaces_fixed returns one entry per notification, not per batch.

        Regression: CloudVision can pack multiple interfaces into a single batch (observed
        with breakout sub-ports like Ethernet53/1-4). The previous implementation built one
        result dict per batch and only retained the last interface's fields, silently
        dropping the rest.
        """

        def make_notif(intf_id):
            return {
                "path_elements": ["Sysdb", "interface", "status", "eth", "phy", "slice", "1", "intfStatus", intf_id],
                "updates": {
                    "intfId": intf_id,
                    "linkStatus": {"Name": "linkUp"},
                    "operStatus": {"Name": "intfOperUp"},
                    "enabledState": {"Name": "enabled"},
                    "burnedInAddr": "ab:cd:ef:00:00:01",
                    "mtu": 1500,
                },
            }

        batches = [
            {"notifications": [make_notif("Ethernet1")]},
            {"notifications": [make_notif("Ethernet53/1"), make_notif("Ethernet53/2"), make_notif("Ethernet54/1")]},
        ]
        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", MagicMock()):
            self.client.get = MagicMock(return_value=batches)
            results = cloudvision.get_interfaces_fixed(client=self.client, dId="JPE12345678")
        self.assertEqual(
            [r["interface"] for r in results],
            ["Ethernet1", "Ethernet53/1", "Ethernet53/2", "Ethernet54/1"],
        )

    def test_get_interfaces_fixed_split_notifications(self):
        """Test get_interfaces_fixed merges frames when state arrives without intfId.

        Regression: CloudVision streams an interface's attributes across multiple frames. The
        identity frame carries intfId while a later frame carries state (enabledState/operStatus/
        linkStatus) and omits intfId, identifying the interface only via path_elements. The previous
        guard dropped that frame, leaving the interface without an ``enabled`` key.
        """
        path = ["Sysdb", "interface", "status", "eth", "phy", "slice", "1", "intfStatus", "Ethernet1"]
        batches = [
            {
                "notifications": [
                    {"path_elements": path, "updates": {"intfId": "Ethernet1", "burnedInAddr": "ab:cd:ef:00:00:01"}},
                    {
                        "path_elements": path,
                        "updates": {
                            "enabledState": {"Name": "enabled"},
                            "operStatus": {"Name": "intfOperUp"},
                            "linkStatus": {"Name": "linkUp"},
                        },
                    },
                ]
            }
        ]
        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", MagicMock()):
            self.client.get = MagicMock(return_value=batches)
            results = cloudvision.get_interfaces_fixed(client=self.client, dId="JPE12345678")
        self.assertEqual(
            results,
            [
                {
                    "interface": "Ethernet1",
                    "mac_addr": "ab:cd:ef:00:00:01",
                    "enabled": True,
                    "oper_status": "up",
                    "link_status": "up",
                }
            ],
        )

    def test_get_interfaces_chassis_split_notifications(self):
        """Test get_interfaces_chassis merges frames when state arrives without intfId."""
        path = ["Sysdb", "interface", "status", "eth", "phy", "slice", "Linecard1", "intfStatus", "Ethernet1"]
        batches = [
            {
                "notifications": [
                    {"path_elements": path, "updates": {"intfId": "Ethernet1", "burnedInAddr": "ab:cd:ef:00:00:01"}},
                    {
                        "path_elements": path,
                        "updates": {
                            "enabledState": {"Name": "enabled"},
                            "operStatus": {"Name": "intfOperUp"},
                            "linkStatus": {"Name": "linkUp"},
                        },
                    },
                ]
            }
        ]
        mock_get_query = MagicMock(return_value={"Linecard1": None})
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.get_query", mock_get_query):
            self.client.get = MagicMock(return_value=batches)
            results = cloudvision.get_interfaces_chassis(client=self.client, dId="JPE12345678")
        self.assertEqual(
            results,
            [
                {
                    "interface": "Ethernet1",
                    "mac_addr": "ab:cd:ef:00:00:01",
                    "enabled": True,
                    "oper_status": "up",
                    "link_status": "up",
                }
            ],
        )

    def test_get_interfaces_port_channel_split_notifications(self):
        """Test get_interfaces_port_channel attributes a frame missing intfId via path_elements."""
        status_path = ["Sysdb", "lag", "input", "interface", "lag", "intfStatus", "Port-Channel1000"]
        config_path = ["Sysdb", "interface", "config", "eth", "lag", "intfConfig", "Port-Channel1000"]
        status_batches = [
            {
                "notifications": [
                    # No intfId in updates; identity comes from path_elements only.
                    {
                        "path_elements": status_path,
                        "updates": {
                            "linkStatus": {"Name": "linkUp"},
                            "operStatus": {"Name": "intfOperUp"},
                            "addr": "fc:bd:67:0f:6f:04",
                            "active": True,
                        },
                    }
                ]
            }
        ]
        config_batches = [{"notifications": [{"path_elements": config_path, "updates": {"mtu": 9214}}]}]
        self.client.get = MagicMock(side_effect=[status_batches, config_batches])
        results = cloudvision.get_interfaces_port_channel(client=self.client, dId="JPE12345678")
        self.assertEqual(
            results,
            [
                {
                    "interface": "Port-Channel1000",
                    "link_status": "up",
                    "oper_status": "up",
                    "mac_addr": "fc:bd:67:0f:6f:04",
                    "enabled": True,
                    "mtu": 9214,
                }
            ],
        )

    def test_get_interfaces_chassis(self):
        """Test get_interfaces_chassis method."""
        mock_get_query = MagicMock(return_value={"Linecard1": None})

        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.get_query", mock_get_query):
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

    def test_get_interfaces_port_channel(self):
        """Test get_interfaces_port_channel merges intfStatus and intfConfig notifications."""
        self.client.get = MagicMock(
            side_effect=[fixtures.PORT_CHANNEL_STATUS_QUERY, fixtures.PORT_CHANNEL_CONFIG_QUERY]
        )
        results = cloudvision.get_interfaces_port_channel(client=self.client, dId="JPE12345678")
        by_name = {entry["interface"]: entry for entry in results}
        self.assertEqual(set(by_name), {"Port-Channel1000", "Recirc-Channel1"})
        self.assertEqual(
            by_name["Port-Channel1000"],
            {
                "interface": "Port-Channel1000",
                "link_status": "down",
                "oper_status": "down",
                "mac_addr": "fc:bd:67:0f:6f:04",
                "mtu": 9214,
                "enabled": True,
            },
        )
        self.assertEqual(
            by_name["Recirc-Channel1"],
            {
                "interface": "Recirc-Channel1",
                "link_status": "up",
                "oper_status": "up",
                "mac_addr": "fc:bd:67:0f:6e:d5",
                "mtu": 9214,
                "enabled": True,
            },
        )

    def test_get_interfaces_port_channel_empty(self):
        """Test get_interfaces_port_channel returns an empty list when there are no port-channels."""
        self.client.get = MagicMock(return_value=[{"notifications": []}])
        self.assertEqual(cloudvision.get_interfaces_port_channel(client=self.client, dId="JPE12345678"), [])

    def test_get_port_channel_members(self):
        """Test get_port_channel_members reads LAG membership from Sysdb/lag/input/config/cli/phyIntf."""
        self.client.get = MagicMock(return_value=fixtures.LAG_INPUT_PHYINTF_QUERY)
        results = cloudvision.get_port_channel_members(client=self.client, dId="JPE12345678")
        self.assertEqual(
            results,
            {
                "Ethernet53/1": "Port-Channel1000",
                "Ethernet54/1": "Port-Channel1000",
                "Ethernet6": "Recirc-Channel1",
            },
        )

    def test_get_interface_description_port_channel(self):
        """Test get_interface_description for Port-Channel interfaces against a real CV response.

        Asserts two things:
        1. The function queries the lag intfConfig path (`eth/lag/intfConfig`), not the
           eth/phy path used for regular Ethernet interfaces.
        2. The function returns the description parsed from the captured CloudVision
           response shape.
        """
        captured_paths = []

        def fake_create_query(args, _dataset):
            for path_elts, _ in args:
                captured_paths.append(list(path_elts))
            return MagicMock()

        self.client.get = MagicMock(return_value=fixtures.PORTCHANNEL_DESCRIPTION_QUERY)
        with patch("nautobot_ssot.integrations.aristacv.utils.cloudvision.create_query", side_effect=fake_create_query):
            result = cloudvision.get_interface_description(
                client=self.client, dId="JPE12345678", interface="Port-Channel1000"
            )
        self.assertEqual(result, "Uplink to spine1")
        self.assertEqual(
            captured_paths[0],
            ["Sysdb", "interface", "config", "eth", "lag", "intfConfig", "Port-Channel1000"],
        )

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

    def test_get_routed_interface_description(self):
        """Test get_routed_interface_description returns description for a Loopback interface."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.ROUTED_INTF_DESCRIPTION_QUERY
            results = cloudvision.get_routed_interface_description(
                client=self.client, dId="JPE12345678", interface="Loopback0"
            )
        self.assertEqual(results, "hello!")

    def test_get_routed_interface_description_empty(self):
        """Test get_routed_interface_description returns empty string when interface has no description."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.ROUTED_INTF_DESCRIPTION_QUERY
            results = cloudvision.get_routed_interface_description(
                client=self.client, dId="JPE12345678", interface="Vlan132"
            )
        self.assertEqual(results, "")

    def test_get_routed_interface_description_not_found(self):
        """Test get_routed_interface_description returns empty string when interface is not in the response."""
        mock_query = MagicMock()
        mock_query.dataset.type = "device"
        mock_query.dataset.name = "JPE12345678"

        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", mock_query):
            self.client.get = MagicMock()
            self.client.get.return_value = fixtures.ROUTED_INTF_DESCRIPTION_QUERY
            results = cloudvision.get_routed_interface_description(
                client=self.client, dId="JPE12345678", interface="Ethernet99"
            )
        self.assertEqual(results, "")

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

    def test_get_ip_interfaces_split_notifications(self):
        """Test get_ip_interfaces when intfId and addrWithMask are in separate gRPC notifications."""
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
            self.client.get.return_value = fixtures.IP_INTF_SPLIT_NOTIF_QUERY
            results = cloudvision.get_ip_interfaces(client=self.client, dId="JPE12345678")
        expected = fixtures.IP_INTF_SPLIT_NOTIF_FIXTURE
        self.assertEqual(results, expected)

    def test_get_all_interface_modes_bulk(self):
        """Test get_all_interface_modes returns a dict keyed by interface name."""
        batches = [
            {
                "notifications": [
                    {
                        "path_elements": [
                            "Sysdb",
                            "bridging",
                            "switchIntfConfig",
                            "switchIntfConfig",
                            "Ethernet1",
                        ],
                        "updates": {"switchportMode": {"Name": "trunk"}},
                    },
                    {
                        "path_elements": [
                            "Sysdb",
                            "bridging",
                            "switchIntfConfig",
                            "switchIntfConfig",
                            "Ethernet2",
                        ],
                        "updates": {"switchportMode": {"Name": "access"}},
                    },
                    {
                        "path_elements": [
                            "Sysdb",
                            "bridging",
                            "switchIntfConfig",
                            "switchIntfConfig",
                            "Ethernet3",
                        ],
                        "updates": {},
                    },
                ]
            }
        ]
        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", MagicMock()):
            self.client.get = MagicMock(return_value=batches)
            results = cloudvision.get_all_interface_modes(client=self.client, dId="JPE12345678")
        self.assertEqual(results, {"Ethernet1": "trunk", "Ethernet2": "access"})

    def test_get_all_interface_transceivers_bulk(self):
        """Test get_all_interface_transceivers returns a dict keyed by interface name."""
        batches = [
            {
                "notifications": [
                    {
                        "path_elements": ["Sysdb", "hardware", "archer", "xcvr", "status", "all", "Ethernet1"],
                        "updates": {"actualIdEepromContents": {"mediaType": "40GBASE-PLR4"}},
                    },
                    {
                        "path_elements": ["Sysdb", "hardware", "archer", "xcvr", "status", "all", "Ethernet2"],
                        "updates": {"mediaType": {"Name": "xcvr10GBaseSR"}},
                    },
                    {
                        "path_elements": ["Sysdb", "hardware", "archer", "xcvr", "status", "all", "Ethernet3"],
                        "updates": {"localMediaType": {"Name": "xcvr1000BaseT"}},
                    },
                    {
                        "path_elements": ["Sysdb", "hardware", "archer", "xcvr", "status", "all", "Ethernet4"],
                        "updates": {},
                    },
                ]
            }
        ]
        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", MagicMock()):
            self.client.get = MagicMock(return_value=batches)
            results = cloudvision.get_all_interface_transceivers(client=self.client, dId="JPE12345678")
        self.assertEqual(
            results,
            {
                "Ethernet1": "40GBASE-PLR4",
                "Ethernet2": "xcvr10GBaseSR",
                "Ethernet3": "xcvr1000BaseT",
            },
        )

    def test_get_all_interface_descriptions_bulk(self):
        """Test get_all_interface_descriptions returns a dict keyed by intfId.

        Two queries are issued (physical eth/phy/slice path and non-physical wildcard path);
        each Wildcard() matches exactly one path segment, so a single wildcard query cannot
        cover both shapes. The mock returns physical descriptions on the first call and
        non-physical descriptions on the second.
        """
        physical_batch = [
            {
                "notifications": [
                    {
                        "path_elements": [
                            "Sysdb",
                            "interface",
                            "config",
                            "eth",
                            "phy",
                            "slice",
                            "1",
                            "intfConfig",
                            "Ethernet1",
                        ],
                        "updates": {"intfId": "Ethernet1", "description": "uplink to spine"},
                    },
                    {
                        "path_elements": [
                            "Sysdb",
                            "interface",
                            "config",
                            "eth",
                            "phy",
                            "slice",
                            "1",
                            "intfConfig",
                            "Ethernet2",
                        ],
                        "updates": {"intfId": "Ethernet2", "description": ""},
                    },
                ]
            }
        ]
        non_physical_batch = [
            {
                "notifications": [
                    {
                        "path_elements": [
                            "Sysdb",
                            "interface",
                            "config",
                            "eth",
                            "lag",
                            "intfConfig",
                            "Port-Channel1",
                        ],
                        "updates": {"intfId": "Port-Channel1", "description": "bonded uplink"},
                    },
                    {
                        "path_elements": [
                            "Sysdb",
                            "interface",
                            "config",
                            "l3",
                            "intf",
                            "intfConfig",
                            "Loopback0",
                        ],
                        "updates": {"intfId": "Loopback0", "description": "router id"},
                    },
                ]
            }
        ]
        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", MagicMock()):
            self.client.get = MagicMock(side_effect=[physical_batch, non_physical_batch])
            results = cloudvision.get_all_interface_descriptions(client=self.client, dId="JPE12345678")
        self.assertEqual(
            results,
            {
                "Ethernet1": "uplink to spine",
                "Port-Channel1": "bonded uplink",
                "Loopback0": "router id",
            },
        )

    def test_get_ip_interfaces_coalesced_batch(self):
        """Test get_ip_interfaces when CloudVision coalesces multiple interfaces into one batch.

        Regression: gRPC can pack notifications for several interfaces into a single batch when
        the query uses Wildcard(). Per-batch accumulators would silently merge or overwrite
        interfaces. Group by notif["path_elements"][-1] (interface name) instead.
        """
        with patch("cloudvision.Connector.grpc_client.grpcClient.create_query", MagicMock()):
            self.client.get = MagicMock(return_value=fixtures.IP_INTF_COALESCED_BATCH_QUERY)
            results = cloudvision.get_ip_interfaces(client=self.client, dId="JPE12345678")
        self.assertEqual(results, fixtures.IP_INTF_COALESCED_BATCH_FIXTURE)
