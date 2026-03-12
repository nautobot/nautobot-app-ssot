"""Test Meraki adapter."""

from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.models import JobResult, Status

from nautobot_ssot.integrations.meraki.diffsync.adapters.meraki import MerakiAdapter
from nautobot_ssot.integrations.meraki.jobs import MerakiDataSource
from nautobot_ssot.tests.meraki.fixtures import fixtures as fix


class TestMerakiAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotMerakiAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize test case."""
        super().setUp()

        self.status_active = Status.objects.get(name="Active")
        self.meraki_client = MagicMock()
        self.meraki_client.get_org_networks.return_value = fix.GET_ORG_NETWORKS_SENT_FIXTURE
        self.meraki_client.network_map = fix.NETWORK_MAP_FIXTURE
        self.meraki_client.get_org_devices.return_value = fix.GET_ORG_DEVICES_FIXTURE
        self.meraki_client.get_org_device_statuses.return_value = fix.GET_ORG_DEVICE_STATUSES_RECV_FIXTURE
        self.meraki_client.get_org_uplink_addresses_by_device.return_value = (
            fix.GET_ORG_UPLINK_ADDRESSES_BY_DEVICE_FIXTURE
        )
        self.meraki_client.get_management_ports.return_value = fix.GET_MANAGEMENT_PORTS_RECV_FIXTURE
        self.meraki_client.get_uplink_settings.return_value = fix.GET_UPLINK_SETTINGS_RECV
        self.meraki_client.get_switchport_statuses.return_value = fix.GET_SWITCHPORT_STATUSES
        self.meraki_client.get_org_uplink_statuses.return_value = fix.GET_ORG_UPLINK_STATUSES_RECV_FIXTURE
        self.meraki_client.get_appliance_switchports.return_value = fix.GET_APPLIANCE_SWITCHPORTS_FIXTURE
        self.meraki_client.get_org_switchports.return_value = fix.GET_ORG_SWITCHPORTS_RECV_FIXTURE

        site_loctype = LocationType.objects.get_or_create(name="Site")[0]
        site_loctype.content_types.add(ContentType.objects.get_for_model(Device))
        self.job = MerakiDataSource()
        self.job.logger.debug = MagicMock()
        self.job.logger.warning = MagicMock()
        self.job.instance = MagicMock()
        self.job.instance.controller_managed_device_groups = MagicMock()
        self.job.instance.controller_managed_device_groups.first().name = "Meraki Managed Device Group"
        self.job.instance.controller_managed_device_groups.count().return_value = 1
        self.job.hostname_mapping = []
        self.job.devicetype_mapping = [("MS", "Switch"), ("MX", "Firewall")]
        self.job.network_loctype = site_loctype
        self.job.location_map = {}
        self.job.device_status = None
        self.job.location = None
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.meraki = MerakiAdapter(job=self.job, sync=None, client=self.meraki_client)

    def test_data_loading(self):
        """Test Nautobot SSoT for Meraki load() function."""
        self.meraki_client.validate_organization_exists.return_value = True
        self.meraki.load()
        wan1_ports = [
            f"wan1__{dev['name']}"
            for dev in fix.GET_ORG_DEVICES_FIXTURE
            if dev["model"].startswith(("MX", "MG", "MR", "MS", "Z"))
        ]
        wan2_ports = [
            f"wan2__{dev['name']}"
            for dev in fix.GET_ORG_DEVICES_FIXTURE
            if dev["model"].startswith(("MX", "MG", "MR", "MS", "Z"))
        ]
        man1_ports = [
            f"man1__{dev['name']}" for dev in fix.GET_ORG_DEVICES_FIXTURE if dev["model"].startswith(("MR", "CW"))
        ]
        lan_ports = []
        for port in fix.GET_APPLIANCE_SWITCHPORTS_FIXTURE:
            for dev in fix.GET_ORG_DEVICES_FIXTURE:
                if dev["model"].startswith(("MX", "MG", "Z")):
                    lan_ports.append(f"{port['number']}__{dev['name']}")
        for switch in fix.GET_ORG_SWITCHPORTS_SENT_FIXTURE:
            for port in switch["ports"]:
                lan_ports.append(f"{port['portId']}__Lab Switch")
        expected_ports = set(wan1_ports + wan2_ports + lan_ports + man1_ports)
        self.assertEqual(expected_ports, {port.get_unique_id() for port in self.meraki.get_all("port")})
        self.assertEqual(
            {"10.1.15.0/24__Global", "10.5.52.3/32__Global", "2001:116:4811:7d51:b7e:a1fa:edbe:4f2c/128__Global"},
            {pf.get_unique_id() for pf in self.meraki.get_all("prefix")},
        )
        self.assertEqual(
            {
                "10.1.15.10__None",
                "10.1.15.34__None",
                "10.5.52.3__None",
                "2001:116:4811:7d51:b7e:a1fa:edbe:4f2c__None",
            },
            {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")},
        )

    def test_load_networks(self):
        """Test loading of Meraki networks."""
        self.meraki.load_networks()
        self.assertEqual(
            {f"{net['name']}__None" for net in fix.GET_ORG_NETWORKS_SENT_FIXTURE},
            {net.get_unique_id() for net in self.meraki.get_all("network")},
        )

    def test_load_networks_empty(self):
        """Test loading networks when API returns empty list."""
        self.meraki_client.get_org_networks.return_value = []
        self.meraki.load_networks()
        networks = self.meraki.get_all("network")
        self.assertEqual(len(networks), 0)

    def test_load_networks_with_parent_loctype_and_location(self):
        """Test loading of Meraki networks when network_loctype has a parent."""
        region_loctype = LocationType.objects.get_or_create(name="Region")[0]
        us_region = Location.objects.get_or_create(name="US", location_type=region_loctype, status=self.status_active)[
            0
        ]

        self.job.network_loctype.parent = region_loctype
        self.job.network_loctype.save()
        self.job.parent_location = us_region

        self.meraki.load_networks()

        self.assertEqual(
            {f"{net['name']}__US" for net in fix.GET_ORG_NETWORKS_SENT_FIXTURE},
            {net.get_unique_id() for net in self.meraki.get_all("network")},
        )

    def test_load_networks_with_location_map(self):
        """Test loading of Meraki networks when location_map is defined on the job."""
        region_loctype = LocationType.objects.get_or_create(name="Region")[0]
        self.job.network_loctype.parent = region_loctype
        self.job.network_loctype.validated_save()
        us_region = Location.objects.get_or_create(name="US", location_type=region_loctype, status=self.status_active)[
            0
        ]
        self.job.parent_location = us_region
        self.job.location_map = {"Lab": {"name": "Chicago", "parent": "US"}, "HQ": {"name": "New York", "parent": "US"}}

        self.meraki.load_networks()

        self.assertEqual(
            {"Chicago__US", "New York__US"},
            {net.get_unique_id() for net in self.meraki.get_all("network")},
        )

    def test_load_devices_success(self):
        """Test successful loading of Meraki devices."""
        self.job.hostname_mapping = []
        self.job.devicetype_mapping = []
        self.meraki.load_firewall_ports = MagicMock()
        self.meraki.load_switch_ports = MagicMock()
        self.meraki.load_ap_ports = MagicMock()
        self.meraki.load_devices()
        self.assertEqual(
            {dev["name"] for dev in fix.GET_ORG_DEVICES_FIXTURE},
            {dev.get_unique_id() for dev in self.meraki.get_all("device")},
        )
        self.meraki.load_firewall_ports.assert_called()
        self.meraki.load_switch_ports.assert_called()
        self.meraki.load_ap_ports.assert_called()

    def test_load_devices_missing_hostname(self):
        """Test loading of Meraki devices when hostname is missing."""
        self.meraki_client.get_org_devices.return_value = [{"name": "", "serial": "ABCD-EF12-3456"}]
        self.meraki.load_devices()
        self.job.logger.warning.assert_called()
        self.job.logger.warning.calls[0].contains(
            message="Device serial ABCD-EF12-3456 is missing hostname so will be skipped."
        )

    def test_duplicate_device_loading_error(self):
        """Validate error thrown when duplicate device attempts to be loaded."""
        self.meraki.load_devices()
        self.meraki.load_devices()
        self.job.logger.warning.assert_called()
        self.job.logger.warning.calls[0].contains(message="Duplicate device Lab01 found and being skipped.")
        self.job.logger.warning.calls[1].contains(message="Duplicate device HQ01 found and being skipped.")
        self.job.logger.warning.calls[2].contains(message="Duplicate device Lab Switch found and being skipped.")
        self.job.logger.warning.calls[3].contains(message="Duplicate device HQ AP found and being skipped.")

    @patch("nautobot_ssot.integrations.meraki.diffsync.adapters.meraki.parse_hostname_for_role")
    def test_load_devices_with_hostname_mapping(self, mock_parse):
        """Validate loading of devices with hostname mapping."""
        self.job.debug = True
        self.meraki_client.get_org_devices.return_value = [
            {
                "name": "test.switch.net",
                "serial": "ABCD-EF12-3456",
                "networkId": "H_203630551508078460",
                "model": "MS225-24",
                "notes": "Lab switch",
                "firmware": "switch-15-21-1",
            }
        ]
        self.job.hostname_mapping = [(".*switch.*", "Switch")]
        mock_parse.return_value = "Switch"
        self.meraki.load_devices()
        self.job.logger.debug.assert_called()
        self.job.logger.debug.calls[0].contains("Parsing hostname for device test.switch.net to determine role.")
        mock_parse.assert_called_with(
            device_hostname="test.switch.net", hostname_map=self.job.hostname_mapping, default_role="Unknown"
        )

    @patch("nautobot_ssot.integrations.meraki.diffsync.adapters.meraki.get_role_from_devicetype")
    def test_load_devices_with_devicetype_mapping(self, mock_get_role):
        """Validate loading of devices with DeviceType mapping."""
        self.job.debug = True
        self.meraki_client.get_org_devices.return_value = [
            {
                "name": "HQ AP",
                "serial": "L6XI-2BIN-EUTI",
                "networkId": "L_165471703274884707",
                "model": "MR42",
                "notes": "",
                "firmware": "wireless-29-5-1",
            }
        ]
        self.job.devicetype_mapping = [("MR", "AP")]
        mock_get_role.return_value = "AP"
        self.meraki.load_devices()
        self.job.logger.debug.assert_called()
        self.job.logger.debug.calls[0].contains("Parsing device model for device HQ AP to determine role.")
        mock_get_role.assert_called_with(dev_model="MR42", devicetype_map=self.job.devicetype_mapping)

    def test_load_ap_uplink_ports_success_without_prefix(self):
        """Validate load_ap_uplink_ports() loads an AP uplink port as expected when a prefix isn't passed."""
        mock_device = MagicMock()
        mock_device.name = "HQ AP"

        self.meraki.device_map = {"HQ AP": fix.GET_ORG_DEVICES_FIXTURE[3]}
        self.meraki.conn.network_map = {"L_165471703274884707": {"name": "HQ"}}

        ap_port = {
            "interface": "man1",
            "addresses": [
                {
                    "protocol": "ipv4",
                    "address": "10.5.52.3",
                }
            ],
        }

        self.meraki.load_ap_uplink_ports(device=mock_device, port=ap_port)
        self.assertEqual(
            {
                "man1__HQ AP",
            },
            {uplink.get_unique_id() for uplink in self.meraki.get_all("port")},
        )
        self.assertEqual({"10.5.52.3__None"}, {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")})

    def test_load_ap_uplink_ports_success_with_prefix(self):
        """Validate load_ap_uplink_ports() loads an AP uplink port as expected when a prefix is passed."""
        mock_device = MagicMock()
        mock_device.name = "HQ AP"

        self.meraki.device_map = {"HQ AP": fix.GET_ORG_DEVICES_FIXTURE[3]}
        self.meraki.conn.network_map = {"L_165471703274884707": {"name": "HQ"}}

        self.meraki.load_ap_uplink_ports(
            device=mock_device,
            port=fix.GET_ORG_UPLINK_ADDRESSES_BY_DEVICE_FIXTURE[0]["uplinks"][0],
            prefix="10.5.52.0/24",
        )
        self.assertEqual(
            {
                "man1__HQ AP",
            },
            {uplink.get_unique_id() for uplink in self.meraki.get_all("port")},
        )
        self.assertEqual(
            {
                "10.5.52.3__None",
                "2001:116:4811:7d51:b7e:a1fa:edbe:4f2c__None",
            },
            {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")},
        )

    def test_load_firewall_ports_pppoe_address_without_mask(self):
        """Validate load_firewall_ports() handles PPPoE address without mask."""
        mock_device = MagicMock()
        mock_device.name = "HQ MX"

        self.meraki_client.get_management_ports.return_value = {"wan1": {}}
        self.meraki_client.get_uplink_settings.return_value = fix.GET_UPLINK_SETTINGS_PPPOE_RECV_FIXTURE
        self.meraki_client.get_appliance_switchports.return_value = []

        self.meraki.load_firewall_ports(
            device=mock_device,
            serial="V4GD-ABDP-YVCK",
            network_id="L_165471703274884707",
            lan_ip=None,
        )

        self.assertEqual(
            {"wan1__HQ MX"},
            {port.get_unique_id() for port in self.meraki.get_all("port")},
        )
        self.assertEqual(
            {"1.6.8.10__None"},
            {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")},
        )
        self.assertEqual(
            {"1.6.8.10/32__Global"},
            {prefix.get_unique_id() for prefix in self.meraki.get_all("prefix")},
        )

    def test_load_firewall_ports_lan_svis_disabled(self):
        """LAN SVIs are skipped when sync_firewall_lan_ips is False."""
        mock_device = MagicMock()
        mock_device.name = "HQ01"

        self.job.sync_firewall_lan_ips = False
        self.meraki.device_map = {"HQ01": fix.GET_ORG_DEVICES_FIXTURE[1]}

        # Avoid unrelated WAN/port side effects
        self.meraki_client.get_management_ports.return_value = {}
        self.meraki_client.get_uplink_settings.return_value = {}
        self.meraki_client.get_appliance_switchports.return_value = []

        self.meraki.load_firewall_ports(
            device=mock_device,
            serial="V4GD-ABDP-YVCK",
            network_id="L_165471703274884707",
            lan_ip=None,
        )

        self.meraki_client.get_appliance_vlans_settings.assert_not_called()

        ports = {port.get_unique_id() for port in self.meraki.get_all("port")}
        self.assertNotIn("Vlan1234__HQ01", ports)
        self.assertNotIn("Vlan1__HQ01", ports)

    def test_load_firewall_ports_vlan_svis(self):
        """VLAN-mode SVIs are loaded when sync_firewall_lan_ips is True."""
        mock_device = MagicMock()
        mock_device.name = "HQ01"

        self.job.sync_firewall_lan_ips = True
        self.meraki.device_map = {"HQ01": fix.GET_ORG_DEVICES_FIXTURE[1]}

        self.meraki_client.get_appliance_vlans_settings.return_value = fix.GET_APPLIANCE_VLANS_SETTINGS_TRUE_FIXTURE
        self.meraki_client.get_appliance_vlans.return_value = fix.GET_APPLIANCE_VLANS_FIXTURE

        self.meraki_client.get_management_ports.return_value = {}
        self.meraki_client.get_uplink_settings.return_value = {}
        self.meraki_client.get_appliance_switchports.return_value = []

        self.meraki.load_firewall_ports(
            device=mock_device,
            serial="V4GD-ABDP-YVCK",
            network_id="L_165471703274884707",
            lan_ip=None,
        )

        self.meraki_client.get_appliance_single_lan.assert_not_called()

        ports = {port.get_unique_id() for port in self.meraki.get_all("port")}
        self.assertIn("Vlan1234__HQ01", ports)

        prefixes = {pf.get_unique_id() for pf in self.meraki.get_all("prefix")}
        self.assertIn("192.168.1.0/24__Global", prefixes)

        ipaddrs = {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")}
        self.assertIn("192.168.1.2__None", ipaddrs)

        ipassignment = self.meraki.get(
            "ipassignment",
            {"address": "192.168.1.2", "device": "HQ01", "namespace": "Global", "port": "Vlan1234"},
        )
        self.assertFalse(ipassignment.primary)

    def test_load_firewall_ports_single_lan_svi(self):
        """Single-LAN SVIs are loaded when VLANs are disabled."""
        mock_device = MagicMock()
        mock_device.name = "HQ01"

        self.job.sync_firewall_lan_ips = True
        self.meraki.device_map = {"HQ01": fix.GET_ORG_DEVICES_FIXTURE[1]}

        self.meraki_client.get_appliance_vlans_settings.return_value = fix.GET_APPLIANCE_VLANS_SETTINGS_FALSE_FIXTURE
        self.meraki_client.get_appliance_single_lan.return_value = fix.GET_APPLIANCE_SINGLE_LAN_FIXTURE

        self.meraki_client.get_management_ports.return_value = {}
        self.meraki_client.get_uplink_settings.return_value = {}
        self.meraki_client.get_appliance_switchports.return_value = []

        self.meraki.load_firewall_ports(
            device=mock_device,
            serial="V4GD-ABDP-YVCK",
            network_id="L_165471703274884707",
            lan_ip=None,
        )

        self.meraki_client.get_appliance_vlans.assert_not_called()

        ports = {port.get_unique_id() for port in self.meraki.get_all("port")}
        self.assertIn("Vlan1__HQ01", ports)

        prefixes = {pf.get_unique_id() for pf in self.meraki.get_all("prefix")}
        self.assertIn("192.168.50.0/24__Global", prefixes)

        ipaddrs = {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")}
        self.assertIn("192.168.50.2__None", ipaddrs)

        ipassignment = self.meraki.get(
            "ipassignment",
            {"address": "192.168.50.2", "device": "HQ01", "namespace": "Global", "port": "Vlan1"},
        )
        self.assertFalse(ipassignment.primary)

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"meraki_allow_dhcp_mgmt_ips": True}})
    def test_load_switch_with_dhcp_mgmt_ip(self):
        """Validate load_switch_ports() loads a switch with a dynamic management ip."""
        mock_device = MagicMock()
        mock_device.name = "HQ-SW-1"

        self.meraki.device_map = {"HQ-SW-1": fix.GET_ORG_DEVICES_DHCP_FIXTURE[0]}
        self.meraki.conn.network_map = {"L_628815097971621533": {"name": "HQ-SW-1"}}

        self.meraki_client.get_org_uplink_addresses_by_device.return_value = (
            fix.GET_ORG_UPLINK_ADDRESSES_BY_DEVICE_SW_DHCP_FIXTURE
        )
        self.meraki_client.get_management_ports.return_value = fix.GET_MANAGEMENT_PORTS_RECV_DHCP_FIXTURE
        self.meraki_client.self.conn.get_org_switchports.return_value = fix.GET_MANAGEMENT_PORTS_RECV_DHCP_FIXTURE

        self.meraki.load_switch_ports(
            device=mock_device, serial=fix.GET_ORG_DEVICES_DHCP_FIXTURE[0]["serial"], lan_ip="146.171.212.44"
        )
        self.assertEqual(
            {"wan1__HQ-SW-1", "man1__HQ-SW-1"},
            {uplink.get_unique_id() for uplink in self.meraki.get_all("port")},
        )
        self.assertEqual(
            {
                "146.171.212.44__None",
            },
            {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")},
        )

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"meraki_allow_dhcp_mgmt_ips": True}})
    def test_default_location(self):
        """Test default location job input var."""
        self.job.location = MagicMock()
        self.job.location.name = "default location"

        mock_device = MagicMock()
        mock_device.name = "HQ-SW-1"

        self.meraki_client.get_org_devices.return_value = fix.GET_ORG_DEVICES_DHCP_FIXTURE

        self.meraki_client.get_org_uplink_addresses_by_device.return_value = (
            fix.GET_ORG_UPLINK_ADDRESSES_BY_DEVICE_SW_DHCP_FIXTURE
        )
        self.meraki_client.get_management_ports.return_value = fix.GET_MANAGEMENT_PORTS_RECV_DHCP_FIXTURE
        self.meraki_client.self.conn.get_org_switchports.return_value = fix.GET_MANAGEMENT_PORTS_RECV_DHCP_FIXTURE
        self.meraki.load_devices()
        self.assertEqual(
            {"default location"},
            {dev.network for dev in self.meraki.get_all("device")},
        )

    def test_device_status(self):
        """Test device status job input var."""
        self.job.device_status = Status.objects.get(name="Staged")

        self.meraki_client.get_org_devices.return_value = [
            {
                "name": "HQ AP",
                "serial": "L6XI-2BIN-EUTI",
                "networkId": "L_165471703274884707",
                "model": "MR42",
                "notes": "",
                "firmware": "wireless-29-5-1",
            }
        ]
        self.meraki.load_devices()
        self.assertEqual(
            {"Staged"},
            {dev.status for dev in self.meraki.get_all("device")},
        )
