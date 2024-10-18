"""Test Meraki adapter."""

from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, LocationType
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.meraki.diffsync.adapters.meraki import MerakiAdapter
from nautobot_ssot.integrations.meraki.jobs import MerakiDataSource
from nautobot_ssot.tests.meraki.fixtures import fixtures as fix


class TestMerakiAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotMerakiAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize test case."""
        self.meraki_client = MagicMock()
        self.meraki_client.get_org_networks.return_value = fix.GET_ORG_NETWORKS_SENT_FIXTURE
        self.meraki_client.network_map = fix.NETWORK_MAP_FIXTURE
        self.meraki_client.get_org_devices.return_value = fix.GET_ORG_DEVICES_FIXTURE
        self.meraki_client.get_org_device_statuses.return_value = fix.GET_ORG_DEVICE_STATUSES_RECV_FIXTURE
        self.meraki_client.get_management_ports.return_value = fix.GET_MANAGEMENT_PORTS_RECV_FIXTURE
        self.meraki_client.get_uplink_settings.return_value = fix.GET_UPLINK_SETTINGS_RECV
        self.meraki_client.get_switchport_statuses.return_value = fix.GET_SWITCHPORT_STATUSES
        self.meraki_client.get_org_uplink_statuses.return_value = fix.GET_ORG_UPLINK_STATUSES_RECV_FIXTURE
        self.meraki_client.get_appliance_switchports.return_value = fix.GET_APPLIANCE_SWITCHPORTS_FIXTURE
        self.meraki_client.get_org_switchports.return_value = fix.GET_ORG_SWITCHPORTS_RECV_FIXTURE

        site_loctype = LocationType.objects.get_or_create(name="Site")[0]
        site_loctype.content_types.add(ContentType.objects.get_for_model(Device))
        self.job = MerakiDataSource()
        self.job.logger.warning = MagicMock()
        self.job.instance = MagicMock()
        self.job.instance.controller_managed_device_groups = MagicMock()
        self.job.instance.controller_managed_device_groups.first().name = "Meraki Managed Device Group"
        self.job.instance.controller_managed_device_groups.count().return_value = 1
        self.job.hostname_mapping = []
        self.job.devicetype_mapping = [("MS", "Switch"), ("MX", "Firewall")]
        self.job.network_loctype = site_loctype
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.meraki = MerakiAdapter(job=self.job, sync=None, client=self.meraki_client)

    def test_data_loading(self):
        """Test Nautobot SSoT for Meraki load() function."""
        self.meraki_client.validate_organization_exists.return_value = True
        self.meraki.load()
        self.assertEqual(
            {f"{net['name']}__None" for net in fix.GET_ORG_NETWORKS_SENT_FIXTURE},
            {net.get_unique_id() for net in self.meraki.get_all("network")},
        )
        self.assertEqual(
            {dev["name"] for dev in fix.GET_ORG_DEVICES_FIXTURE},
            {dev.get_unique_id() for dev in self.meraki.get_all("device")},
        )
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
        lan_ports = []
        for port in fix.GET_APPLIANCE_SWITCHPORTS_FIXTURE:
            for dev in fix.GET_ORG_DEVICES_FIXTURE:
                if dev["model"].startswith(("MX", "MG", "Z")):
                    lan_ports.append(f"{port['number']}__{dev['name']}")
        for switch in fix.GET_ORG_SWITCHPORTS_SENT_FIXTURE:
            for port in switch["ports"]:
                lan_ports.append(f"{port['portId']}__Lab Switch")
        expected_ports = set(wan1_ports + wan2_ports + lan_ports)
        self.assertEqual(expected_ports, {port.get_unique_id() for port in self.meraki.get_all("port")})
        self.assertEqual({"10.1.15.0/24__Global"}, {pf.get_unique_id() for pf in self.meraki.get_all("prefix")})
        self.assertEqual(
            {
                "10.1.15.10/24__10.1.15.0/24",
                "10.1.15.34/24__10.1.15.0/24",
            },
            {ip.get_unique_id() for ip in self.meraki.get_all("ipaddress")},
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
