"""Test Citrix ADM adapter."""

from unittest.mock import MagicMock

from diffsync.exceptions import ObjectNotFound
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.citrix_adm.diffsync.adapters.citrix_adm import CitrixAdmAdapter
from nautobot_ssot.integrations.citrix_adm.jobs import CitrixAdmDataSource
from nautobot_ssot.tests.citrix_adm.fixtures import (
    ADM_DEVICE_MAP_FIXTURE,
    DEVICE_FIXTURE_RECV,
    NSIP6_FIXTURE_RECV,
    SITE_FIXTURE_RECV,
    VLAN_FIXTURE_RECV,
)


class TestCitrixAdmAdapterTestCase(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test NautobotSsotCitrixAdmAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        """Initialize test case."""
        self.sor_cf = None
        self.status_active = None
        self.hq_site = None
        self.test_dev = None
        self.intf = None
        self.addr = None
        super().__init__(*args, **kwargs)

    def setUp(self):
        """Configure shared objects for test cases."""
        super().setUp()
        self.instance = MagicMock()
        self.instance.name = "Test"
        self.instance.remote_url = "https://test.example.com"
        self.instance.verify_ssl = True

        self.citrix_adm_client = MagicMock()
        self.citrix_adm_client.get_sites.return_value = SITE_FIXTURE_RECV
        self.citrix_adm_client.get_devices.return_value = DEVICE_FIXTURE_RECV
        self.citrix_adm_client.get_vlan_bindings.side_effect = VLAN_FIXTURE_RECV
        self.citrix_adm_client.get_nsip6.side_effect = NSIP6_FIXTURE_RECV
        self.job = CitrixAdmDataSource()
        self.job.debug = True
        self.job.location_map = {}
        self.job.parent_location = None
        self.job.hostname_mapping = {}
        self.job.logger.warning = MagicMock()
        self.job.logger.info = MagicMock()
        self.job.logger.debug = MagicMock()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.citrix_adm = CitrixAdmAdapter(job=self.job, sync=None, instances=[self.instance])
        self.citrix_adm.conn = self.citrix_adm_client

    def test_load_site(self):
        """Test Nautobot SSoT Citrix ADM load_site() function."""
        self.citrix_adm.load_site(site_info=SITE_FIXTURE_RECV[2])
        self.assertEqual(
            {"ARIA__West"},
            {site.get_unique_id() for site in self.citrix_adm.get_all("datacenter")},
        )
        self.job.logger.info.assert_called_with("Loaded Datacenter from Citrix ADM: ARIA")

    def test_load_site_w_location_map(self):
        """Test Nautobot SSoT Citrix ADM load_site() function with location_map from Job form."""
        site_info = SITE_FIXTURE_RECV[3]
        self.job.debug = True
        self.job.location_map = {"Apple Inc.": {"name": "Apple", "parent": "Cupertino"}}
        self.citrix_adm.load_site(site_info=site_info)
        self.assertEqual(
            {"Apple__Cupertino"},
            {site.get_unique_id() for site in self.citrix_adm.get_all("datacenter")},
        )
        self.job.logger.info.assert_called_with("Loaded Datacenter from Citrix ADM: Apple")

    def test_load_devices(self):
        """Test the Nautobot SSoT Citrix ADM load_devices() function."""
        self.citrix_adm.adm_site_map[DEVICE_FIXTURE_RECV[0]["datacenter_id"]] = SITE_FIXTURE_RECV[1]
        self.citrix_adm_client.get_devices.return_value = [DEVICE_FIXTURE_RECV[0]]
        self.citrix_adm.load_devices()
        self.assertEqual(
            {"UYLLBFRCXM55-EA"},
            {dev.get_unique_id() for dev in self.citrix_adm.get_all("device")},
        )

    def test_load_devices_duplicate(self):
        """Test the Nautobot SSoT Citrix ADM load_devices() function with duplicate devices."""
        self.citrix_adm.adm_site_map[DEVICE_FIXTURE_RECV[3]["datacenter_id"]] = SITE_FIXTURE_RECV[2]
        self.citrix_adm_client.get_devices.return_value = [DEVICE_FIXTURE_RECV[3]]
        self.citrix_adm.load_devices()
        self.citrix_adm.load_devices()
        self.job.logger.warning.assert_called_with(
            "Duplicate Device attempting to be loaded: OGI-MSCI-IMS-Mctdgj-Pqsf-M"
        )

    def test_load_devices_without_hostname(self):
        """Test the Nautobot SSoT Citrix ADM load_devices() function with a device missing hostname."""
        self.citrix_adm_client.get_devices.return_value = [{"hostname": ""}]
        self.citrix_adm.load_devices()
        self.job.logger.warning.assert_called_with("Device without hostname will not be loaded. {'hostname': ''}")

    def test_load_ports(self):
        """Test the Nautobot SSoT Citrix ADM load_ports() function."""
        self.citrix_adm.adm_device_map = ADM_DEVICE_MAP_FIXTURE
        self.citrix_adm.get = MagicMock()
        self.citrix_adm.get.side_effect = [ObjectNotFound, MagicMock(), ObjectNotFound, MagicMock()]
        self.citrix_adm.load_ports()
        expected_ports = {
            f"{port['port']}__{adc['hostname']}"
            for _, adc in self.citrix_adm.adm_device_map.items()
            for port in adc["ports"]
        }
        expected_ports = list(expected_ports)
        actual_ports = [port.get_unique_id() for port in self.citrix_adm.get_all("port")]
        self.assertEqual(sorted(expected_ports), sorted(actual_ports))

    def test_load_addresses(self):
        """Test the Nautobot SSoT Citrix ADM load_addresses() function."""
        self.citrix_adm.adm_device_map = ADM_DEVICE_MAP_FIXTURE
        self.citrix_adm.load_prefix = MagicMock()
        self.citrix_adm.load_address = MagicMock()
        self.citrix_adm.load_address_to_interface = MagicMock()
        self.citrix_adm.load_addresses()
        self.citrix_adm.load_prefix.assert_called_with(prefix="192.168.1.0/24")
        self.citrix_adm.load_address.assert_called_with(
            host_addr="192.168.1.5",
            mask_length=24,
            prefix="192.168.1.0/24",
            tags=["MGMT"],
        )
        self.citrix_adm.load_address_to_interface.assert_called_with(
            host_addr="192.168.1.5", device="TEST", port="0/1", primary=True
        )

    def test_load_prefix(self):
        """Test the Nautobot SSoT Citrix ADM load_prefix() function."""
        self.citrix_adm.load_prefix(prefix="10.0.0.0/16")
        self.assertEqual({"10.0.0.0/16__Global"}, {pf.get_unique_id() for pf in self.citrix_adm.get_all("prefix")})

    def test_load_address(self):
        """Test the Nautobot SSoT Citrix ADM load_address() function."""
        self.citrix_adm.load_address(host_addr="10.0.0.1", mask_length=24, prefix="10.0.0.0/24", tags=["TEST"])
        self.assertEqual(
            {"10.0.0.1__None"},
            {addr.get_unique_id() for addr in self.citrix_adm.get_all("address")},
        )

    def test_load_address_to_interface(self):
        """Test the Nautobot SSoT Citrix ADM load_address_to_interface() function."""
        self.citrix_adm.load_address_to_interface(host_addr="10.0.0.1", device="TEST", port="mgmt", primary=True)
        self.assertEqual(
            {"10.0.0.1__TEST__mgmt"}, {map.get_unique_id() for map in self.citrix_adm.get_all("ip_on_intf")}
        )

    def test_find_closer_parent_prefix_with_update(self):
        """Test the Nautobot SSoT Citrix ADM find_closer_parent_prefix() function where the prefix is updated."""
        self.citrix_adm.load_prefix(prefix="192.168.1.0/24")
        self.citrix_adm.load_address(host_addr="192.168.1.1", mask_length=32, prefix="192.168.1.0/24")
        self.citrix_adm.load_prefix(prefix="192.168.1.0/29")
        self.job.debug = True
        self.citrix_adm.find_closer_parent_prefix()
        self.job.logger.debug.assert_called_with(
            "More specific Prefix %s found for IPAddress %s", "192.168.1.0/29", "192.168.1.1"
        )
        loaded_addr = self.citrix_adm.get("address", "192.168.1.1__None")
        self.assertEqual(loaded_addr.prefix, "192.168.1.0/29")

    def test_find_closer_parent_prefix_with_mismatched_address_and_prefix(self):
        """Test the Nautobot SSoT Citrix ADM find_closer_parent_prefix() function where the prefix IPv6 and address is IPv4."""
        self.citrix_adm.load_prefix(prefix="2001:db8::/64")
        self.citrix_adm.load_prefix(prefix="192.168.2.0/24")
        self.citrix_adm.load_address(host_addr="192.168.1.1", mask_length=32, prefix="2001:db8::/64")
        self.citrix_adm.load_prefix(prefix="2001:db8::/48")
        self.citrix_adm.find_closer_parent_prefix()
        loaded_addr = self.citrix_adm.get("address", "192.168.1.1__None")
        self.assertEqual(loaded_addr.prefix, "2001:db8::/64")
        self.job.logger.debug.assert_not_called()
