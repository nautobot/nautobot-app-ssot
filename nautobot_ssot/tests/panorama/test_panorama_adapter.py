"""Test Panorama adapter."""

import json
import os
from unittest.mock import MagicMock, patch

from nautobot.apps.testing import TransactionTestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.panorama.diffsync.adapters.panorama import PanoSSoTPanoramaAdapter
from nautobot_ssot.integrations.panorama.jobs import PanoramaDataSource
from nautobot_ssot.integrations.panorama.utils.panorama_adapter_utils import (
    load_firewall_to_diffsync,
    load_ipaddress_to_interface_to_diffsync,
    load_vsys_interface_to_diffsync,
)


def load_json(path):
    """Load a json file."""
    base_path = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_path, "fixtures", path), encoding="utf-8") as file:
        return json.loads(file.read())


def create_panorama_adapter():
    """Create a Panorama adapter for testing."""
    test_panorama_url = "https://panorama.example.com"
    test_panorama_name = "panorama-01"

    panorama_integration = MagicMock()
    panorama_integration.external_integration.remote_url = test_panorama_url
    panorama_integration.external_integration.verify_ssl = True
    panorama_integration.external_integration.secrets_group.get_secret_value.side_effect = (
        lambda **kwargs: "test_user"
        if kwargs.get("access_type") == "TYPE_HTTP" and kwargs.get("secret_type") == "TYPE_USERNAME"
        else "test_password"
    )
    panorama_integration.name = test_panorama_name

    job = PanoramaDataSource()
    job.debug = False
    job.job_result = JobResult.objects.create(
        name=job.job_model.name,
        job_model=job.job_model,
        user=None,
    )
    patcher = patch("nautobot_ssot.integrations.panorama.diffsync.adapters.panorama.Panorama")
    mock_panorama_class = patcher.start()

    mock_pano = MagicMock()
    mock_pano.firewall = MagicMock()
    mock_pano.device_group = MagicMock()
    mock_pano.device_group.device_groups = {}
    mock_panorama_class.return_value = mock_pano

    adapter = PanoSSoTPanoramaAdapter(job=job, sync=None, pan=panorama_integration)
    return adapter, job, patcher, mock_pano, panorama_integration


def load_fixture_to_panos_mocks(fixture, mock_pano):  # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    """Convert fixture JSON data to mock panos objects.

    This helper transforms the raw fixture JSON data into mock panos objects
    that match the structure returned by the actual panos SDK.

    Args:
        fixture: The loaded JSON fixture data
        mock_pano: The mock panorama object to populate
    """

    mock_pano.firewall.firewalls = []
    for fw_data in fixture.get("firewalls", []):
        mock_fw = MagicMock()
        mock_fw.serial = fw_data.get("serial", "")
        mock_fw.name = fw_data.get("name", "")
        mock_fw.vsys = "vsys1"
        mock_fw.show_system_info.return_value = fw_data.get("firewall_system_info", {})

        mock_pano.firewall.firewalls.append(
            {
                "name": fw_data.get("name", ""),
                "value": mock_fw,
                "type": "firewall",
                "vsys_name": "vsys1",
                "vsys_obj": MagicMock(name="vsys1"),
                "location": fw_data.get("location", "shared"),
                "management_ip": fw_data.get("management_ip", ""),
            }
        )

    mock_pano.firewall.vsys = {}
    for serial, vsys_data in fixture.get("vsys", {}).items():
        mock_pano.firewall.vsys[serial] = {}
        for vsys_name, vsys_info in vsys_data.items():
            mock_vsys_obj = MagicMock()
            mock_vsys_obj.name = vsys_name
            mock_fw_obj = MagicMock()
            mock_fw_obj.serial = serial

            interfaces = []
            for iface_name, iface_data in fixture.get("interfaces", {}).items():
                mock_iface = MagicMock()
                mock_iface.name = iface_name
                mock_iface.about.return_value = iface_data
                interfaces.append(mock_iface)

            mock_pano.firewall.vsys[serial][vsys_name] = {
                "name": vsys_name,
                "vsys_obj": mock_vsys_obj,
                "firewall_name": vsys_info.get("name", ""),
                "firewall_obj": mock_fw_obj,
                "devicegroup": vsys_info.get("devicegroup", ""),
                "interfaces": interfaces,
                "cached_successfully": vsys_info.get("cached_successfully", True),
            }

    mock_pano.device_group.device_groups = {}
    for name, parent in fixture.get("device_groups", {}).items():
        mock_group = MagicMock()
        mock_group.name = name
        mock_group.get_parent.return_value = parent
        mock_pano.device_group.device_groups[name] = mock_group


class TestPanoramaAdapter(TransactionTestCase):  # pylint: disable=too-many-public-methods
    """Test Panorama adapter."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize test case."""
        super().setUp()

        def mock_get_mgmt_interface_and_ip(firewall):
            sys_info = firewall.show_system_info()
            system = sys_info.get("system", {})
            mgmt_ip = system.get("mgmt-ip") or system.get("ip-address")
            netmask = system.get("netmask")
            return ("management", f"{mgmt_ip}/{netmask}")

        self.adapter, self.job, self.patcher, _, self.panorama_integration = create_panorama_adapter()
        self.fixture = load_json("panorama_mock_data.json")
        load_fixture_to_panos_mocks(self.fixture, self.adapter.pano)
        self.adapter.pano.firewall.get_management_interface_name_and_ip = MagicMock(
            side_effect=mock_get_mgmt_interface_and_ip
        )
        self.adapter.pano.firewall.get_hostname = MagicMock(return_value="fw-01")
        self.job.panorama_controller = self.panorama_integration
        self.adapter.job.panorama_controller = self.panorama_integration
        self.adapter.job.filtered_device_serials = None

    def tearDown(self):
        """Teardown test case."""
        self.patcher.stop()
        super().tearDown()

    def test_adapter_init(self):
        """Test Nautobot Adapter initialization."""
        self.assertEqual(self.adapter._backend, "Panorama")  # pylint: disable=protected-access
        self.assertEqual(self.adapter.job, self.job)

    def test_load_controllermanageddevicegroup(self):
        """Test loading ControllerManagedDeviceGroup."""
        self.adapter.job.panorama_controller = self.panorama_integration

        controller_name = self.panorama_integration.name

        self.adapter.load_controllermanageddevicegroup()

        expected_identifier = f"{controller_name} - Panorama Devices__{controller_name}"
        stored = self.adapter.store.get(model="controllermanageddevicegroup", identifier=expected_identifier)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.name, f"{controller_name} - Panorama Devices")

    def test_load_firewall(self):
        """Test that load_firewall creates multiple items."""
        fw_names = [fw["name"] for fw in self.fixture["firewalls"]]

        for fw_data in self.fixture["firewalls"]:
            fw_name = fw_data["name"]
            fw_index = fw_names.index(fw_name)
            firewall = self.adapter.pano.firewall.firewalls[fw_index]["value"]
            firewall_system_info = firewall.show_system_info()
            load_firewall_to_diffsync(self.adapter, firewall, firewall_system_info)

            # Test Firewall creation
            stored = self.adapter.store.get(model="firewall", identifier=firewall.serial)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.serial, firewall.serial)

            # Test Model creation
            model = firewall_system_info["system"]["model"]
            identifier = f"{model}__Palo Alto"
            stored = self.adapter.store.get(model="device_type", identifier=identifier)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.model, model)

            # Test Interface creation
            identifier = f"{firewall.serial}__management"
            stored = self.adapter.store.get(model="firewall_interface", identifier=identifier)
            self.assertIsNotNone(stored)

            # Test IP creation
            mgmt_interface, mgmt_ip_cidr = self.adapter.pano.firewall.get_management_interface_name_and_ip(firewall)
            host, mask = mgmt_ip_cidr.split("/")
            identifier = f"{firewall.serial}__{mgmt_interface}__{host}__{mask}"
            stored = self.adapter.store.get(model="ip_address_to_interface", identifier=identifier)
            self.assertIsNotNone(stored)

            # Software
            identifier = f"paloalto_panos__{firewall_system_info['system']['sw-version']}__Active"
            stored = self.adapter.store.get(model="softwareversion", identifier=identifier)
            self.assertIsNotNone(stored)
            identifier = f"{firewall.serial}__paloalto_panos__{firewall_system_info['system']['sw-version']}"
            stored = self.adapter.store.get(model="softwareversiontodevice", identifier=identifier)
            self.assertIsNotNone(stored)

    def test_load_interface_creates_firewall_interface(self):
        # pylint: disable=unused-variable
        """Test that vsys interface is created."""
        for serial, vsys_dict in self.adapter.pano.firewall.vsys.items():
            for vsys_name, vsys_data in vsys_dict.items():
                for interface_obj in vsys_data["interfaces"]:
                    interface_data = self.fixture["interfaces"][interface_obj.name]

                    load_vsys_interface_to_diffsync(self.adapter, interface_obj, interface_data, vsys_data)

                    identifier = f"{vsys_data['firewall_obj'].serial}__{interface_data['name']}"
                    stored = self.adapter.store.get(model="firewall_interface", identifier=identifier)
                    self.assertIsNotNone(stored)
                    self.assertEqual(stored.name, interface_data["name"])

    def test_load_interface_duplicate_handled(self):
        # pylint: disable=unused-variable
        """Test that duplicate interface is handled gracefully."""
        for serial, vsys_dict in self.adapter.pano.firewall.vsys.items():
            for vsys_name, vsys_data in vsys_dict.items():
                for interface_obj in vsys_data["interfaces"]:
                    interface_data = self.fixture["interfaces"][interface_obj.name]

                    load_vsys_interface_to_diffsync(self.adapter, interface_obj, interface_data, vsys_data)
                    load_vsys_interface_to_diffsync(self.adapter, interface_obj, interface_data, vsys_data)

                    identifier = f"{vsys_data['firewall_obj'].serial}__{interface_data['name']}"
                    stored = self.adapter.store.get(model="firewall_interface", identifier=identifier)
                    self.assertIsNotNone(stored)

    def test_load_ip_with_cidr(self):
        # pylint: disable=unused-variable
        """Test IP with CIDR notation."""
        for serial, vsys_dict in self.adapter.pano.firewall.vsys.items():
            for vsys_name, vsys_data in vsys_dict.items():
                for interface_obj in vsys_data["interfaces"]:
                    interface_name = interface_obj.name
                    interface_data = self.fixture["interfaces"].get(interface_name, {})
                    ips_with_cidr = [ip for ip in interface_data.get("ip", []) if "/" in ip]
                    if not ips_with_cidr:
                        continue

                    ip_with_cidr = ips_with_cidr[0]
                    ip_host, ip_mask = ip_with_cidr.split("/")

                    load_ipaddress_to_interface_to_diffsync(self.adapter, interface_obj, interface_data, vsys_data)

                    stored = self.adapter.store.get(
                        model="ip_address_to_interface", identifier=f"{serial}__{interface_name}__{ip_host}__{ip_mask}"
                    )
                    self.assertIsNotNone(stored)

    def test_load_ip_without_cidr_defaults_to_32(self):
        # pylint: disable=unused-variable
        """Test IP without CIDR defaults to /32."""
        for serial, vsys_dict in self.adapter.pano.firewall.vsys.items():
            for vsys_name, vsys_data in vsys_dict.items():
                for interface_obj in vsys_data["interfaces"]:
                    interface_name = interface_obj.name
                    interface_data = self.fixture["interfaces"].get(interface_name, {})
                    valid_ips_without_cidr = [ip for ip in interface_data.get("ip", []) if ip and "/" not in ip]
                    if not valid_ips_without_cidr:
                        continue

                    ip_host = valid_ips_without_cidr[0]

                    load_ipaddress_to_interface_to_diffsync(self.adapter, interface_obj, interface_data, vsys_data)

                    stored = self.adapter.store.get(
                        model="ip_address_to_interface", identifier=f"{serial}__{interface_name}__{ip_host}__32"
                    )
                    self.assertIsNotNone(stored)

    def test_load_multiple_ips(self):
        # pylint: disable=unused-variable
        """Test multiple IPs on same interface."""
        for serial, vsys_dict in self.adapter.pano.firewall.vsys.items():
            for vsys_name, vsys_data in vsys_dict.items():
                for interface_obj in vsys_data["interfaces"]:
                    interface_data = self.fixture["interfaces"][interface_obj.name]
                    if not interface_data.get("ip"):
                        continue

                    load_ipaddress_to_interface_to_diffsync(self.adapter, interface_obj, interface_data, vsys_data)

                    for ip_with_cidr in interface_data["ip"]:
                        if not ip_with_cidr or "/" not in ip_with_cidr:
                            continue
                        ip_host, ip_mask = ip_with_cidr.split("/")
                        identifier = f"{serial}__{interface_obj.name}__{ip_host}__{ip_mask}"
                        stored = self.adapter.store.get(model="ip_address_to_interface", identifier=identifier)
                        self.assertIsNotNone(stored)
