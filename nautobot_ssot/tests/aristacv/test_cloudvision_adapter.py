"""Unit tests for the CloudVision DiffSync adapter class."""

import ipaddress
from unittest.mock import MagicMock, patch

from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.aristacv.diffsync.adapters.cloudvision import (
    CloudvisionAdapter,
)
from nautobot_ssot.integrations.aristacv.jobs import CloudVisionDataSource
from nautobot_ssot.tests.aristacv.fixtures import fixtures


class CloudvisionAdapterTestCase(TransactionTestCase):
    """Test the CloudvisionAdapter class."""

    job_class = CloudVisionDataSource
    databases = ("default", "job_logs")

    def setUp(self):
        """Method to initialize test case."""
        super().setUp()
        self.client = MagicMock()
        self.client.comm_channel = MagicMock()

        self.cloudvision = MagicMock()
        self.cloudvision.get_devices = MagicMock()
        self.cloudvision.get_devices.return_value = fixtures.DEVICE_FIXTURE
        self.cloudvision.get_tags_by_type = MagicMock()
        self.cloudvision.get_tags_by_type.return_value = []
        self.cloudvision.get_device_type = MagicMock()
        self.cloudvision.get_device_type.return_value = "fixedSystem"
        self.cloudvision.get_interfaces_fixed = MagicMock()
        self.cloudvision.get_interfaces_fixed.return_value = fixtures.FIXED_INTERFACE_FIXTURE
        self.cloudvision.get_interface_mode = MagicMock()
        self.cloudvision.get_interface_mode.return_value = "access"
        self.cloudvision.get_interface_transceiver = MagicMock()
        self.cloudvision.get_interface_transceiver.return_value = "1000BASE-T"
        self.cloudvision.get_interface_description = MagicMock()
        self.cloudvision.get_interface_description.return_value = "Uplink to DC1"
        self.cloudvision.get_ip_interfaces = MagicMock()
        self.cloudvision.get_ip_interfaces.return_value = fixtures.IP_INTF_FIXTURE
        self.cloudvision.get_interface_vrf = MagicMock()
        self.cloudvision.get_interface_vrf.return_value = "Global"

        self.job = self.job_class()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.cvp = CloudvisionAdapter(job=self.job, conn=self.client)

    def test_load_devices(self):
        """Test the load_devices() adapter method."""
        # Update config namedtuple `create_controller` to False
        self.job.app_config = self.job.app_config._replace(create_controller=False)
        with patch(
            "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_devices",
            self.cloudvision.get_devices,
        ):
            with patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_device_type",
                self.cloudvision.get_device_type,
            ):
                with patch(
                    "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_fixed",
                    self.cloudvision.get_interfaces_fixed,
                ):
                    self.cvp.load_devices()
        self.assertEqual(
            {dev["hostname"] for dev in fixtures.DEVICE_FIXTURE},
            {dev.get_unique_id() for dev in self.cvp.get_all("device")},
        )

    def test_load_interfaces(self):
        """Test the load_interfaces() adapter method."""
        mock_device = MagicMock()
        mock_device.name = "mock_device"
        mock_device.serial = MagicMock()
        mock_device.serial.return_value = "JPE12345678"
        mock_device.device_model = MagicMock()
        mock_device.device_model.return_value = "DCS-7280CR2-60"

        with patch(
            "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_device_type",
            self.cloudvision.get_device_type,
        ):
            with patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_fixed",
                self.cloudvision.get_interfaces_fixed,
            ):
                with patch(
                    "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_mode",
                    self.cloudvision.get_interface_mode,
                ):
                    with patch(
                        "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_transceiver",
                        self.cloudvision.get_interface_transceiver,
                    ):
                        with patch(
                            "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_description",
                            self.cloudvision.get_interface_description,
                        ):
                            self.cvp.load_interfaces(mock_device)
        self.assertEqual(
            {f"{port['interface']}__mock_device" for port in fixtures.FIXED_INTERFACE_FIXTURE},
            {port.get_unique_id() for port in self.cvp.get_all("port")},
        )

    def test_load_ip_addresses(self):
        """Test the load_ip_addresses() adapter method."""
        mock_device = MagicMock()
        mock_device.name = "mock_device"
        mock_device.serial = MagicMock()
        mock_device.serial.return_value = "JPE12345678"

        with patch(
            "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_ip_interfaces",
            self.cloudvision.get_ip_interfaces,
        ):
            with patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_description",
                self.cloudvision.get_interface_description,
            ):
                with patch(
                    "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_vrf",
                    self.cloudvision.get_interface_vrf,
                ):
                    self.cvp.load_ip_addresses(dev=mock_device)
        self.assertEqual(
            {
                f"{ipaddr['address']}__{ipaddress.ip_interface(ipaddr['address']).network.with_prefixlen}__Global"
                for ipaddr in fixtures.IP_INTF_FIXTURE
            },
            {ipaddr.get_unique_id() for ipaddr in self.cvp.get_all("ipaddr")},
        )
