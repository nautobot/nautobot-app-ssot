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
        self.client.get_inventory = MagicMock(return_value=fixtures.INVENTORY_FIXTURE)
        self.client.get_version = MagicMock(return_value="2024.3.0")

        self.cloudvision = MagicMock()
        self.cloudvision.get_tags_by_type = MagicMock()
        self.cloudvision.get_tags_by_type.return_value = []
        self.cloudvision.get_device_type = MagicMock()
        self.cloudvision.get_device_type.return_value = "fixedSystem"
        self.cloudvision.get_interfaces_fixed = MagicMock()
        self.cloudvision.get_interfaces_fixed.return_value = fixtures.FIXED_INTERFACE_FIXTURE
        self.cloudvision.get_interfaces_port_channel = MagicMock()
        self.cloudvision.get_interfaces_port_channel.return_value = fixtures.PORT_CHANNEL_INTERFACE_FIXTURE
        self.cloudvision.get_port_channel_members = MagicMock()
        self.cloudvision.get_port_channel_members.return_value = fixtures.PORT_CHANNEL_MEMBERS_FIXTURE
        self.cloudvision.get_interface_mode = MagicMock()
        self.cloudvision.get_interface_mode.return_value = "access"
        self.cloudvision.get_interface_transceiver = MagicMock()
        self.cloudvision.get_interface_transceiver.side_effect = lambda client, dId, interface: (
            "Unknown" if interface.startswith("Port-Channel") else "1000BASE-T"
        )
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
        self.job.app_config = self.job.app_config._replace(create_controller=False, import_active=False)
        with (
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_device_type",
                self.cloudvision.get_device_type,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_fixed",
                self.cloudvision.get_interfaces_fixed,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_port_channel",
                self.cloudvision.get_interfaces_port_channel,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_port_channel_members",
                self.cloudvision.get_port_channel_members,
            ),
        ):
            self.cvp.load_devices()
        expected_hostnames = {dev["hostname"] for dev in fixtures.INVENTORY_FIXTURE if dev["hostname"]}
        self.assertEqual(
            expected_hostnames,
            {dev.get_unique_id() for dev in self.cvp.get_all("device")},
        )

    def test_load_interfaces(self):
        """Test the load_interfaces() adapter method."""
        mock_device = MagicMock()
        mock_device.name = "mock_device"
        mock_device.serial = "JPE12345678"
        mock_device.device_model = "DCS-7280CR2-60"

        with patch(
            "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_device_type",
            self.cloudvision.get_device_type,
        ):
            with patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_fixed",
                self.cloudvision.get_interfaces_fixed,
            ):
                with patch(
                    "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_port_channel",
                    self.cloudvision.get_interfaces_port_channel,
                ):
                    with patch(
                        "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_port_channel_members",
                        self.cloudvision.get_port_channel_members,
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
        expected_ports = {
            f"{port['interface']}__mock_device"
            for port in (*fixtures.PORT_CHANNEL_INTERFACE_FIXTURE, *fixtures.FIXED_INTERFACE_FIXTURE)
        }
        self.assertEqual(expected_ports, {port.get_unique_id() for port in self.cvp.get_all("port")})

        port_channel = self.cvp.get(self.cvp.port, {"name": "Port-Channel100", "device": "mock_device"})
        self.assertEqual(port_channel.port_type, "lag")
        self.assertIsNone(port_channel.lag)

        member = self.cvp.get(self.cvp.port, {"name": "Ethernet1/1", "device": "mock_device"})
        self.assertEqual(member.lag, "Port-Channel100")

    def test_load_interfaces_orders_port_channels_before_members(self):
        """Regression: source store must list every Port-Channel before its members.

        NautobotPort.create relies on diffsync's insertion-order iteration to ensure
        the lag parent already exists when a member's create runs (it now calls
        OrmInterface.objects.get with no DoesNotExist fallback). If a future refactor
        appends physical interfaces before the LAGs they belong to, this assertion
        fires before any actual sync attempt and surfaces the regression.
        """
        fake_device = self.cvp.device(
            name="mock_device",
            serial="JPE12345678",
            status="Active",
            device_model="DCS-7280CR2-60",
            version="",
            uuid=None,
        )
        self.cvp.add(fake_device)

        with (
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_device_type",
                self.cloudvision.get_device_type,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_fixed",
                self.cloudvision.get_interfaces_fixed,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interfaces_port_channel",
                self.cloudvision.get_interfaces_port_channel,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_port_channel_members",
                self.cloudvision.get_port_channel_members,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_mode",
                self.cloudvision.get_interface_mode,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_transceiver",
                self.cloudvision.get_interface_transceiver,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_description",
                self.cloudvision.get_interface_description,
            ),
        ):
            self.cvp.load_interfaces(fake_device)

        # `device.ports` holds child port unique_ids in the order they were added.
        for member_name, pc_name in fixtures.PORT_CHANNEL_MEMBERS_FIXTURE.items():
            pc_uid = f"{pc_name}__mock_device"
            member_uid = f"{member_name}__mock_device"
            self.assertLess(
                fake_device.ports.index(pc_uid),
                fake_device.ports.index(member_uid),
                f"Port-Channel {pc_name} must precede member {member_name} in the source store",
            )

    def test_load_ip_addresses(self):
        """Test the load_ip_addresses() adapter method."""
        mock_device = MagicMock()
        mock_device.name = "mock_device"
        mock_device.serial = "JPE12345678"

        with (
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_ip_interfaces",
                self.cloudvision.get_ip_interfaces,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_description",
                self.cloudvision.get_interface_description,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_vrf",
                self.cloudvision.get_interface_vrf,
            ),
        ):
            self.cvp.load_ip_addresses(dev=mock_device, primary_ip="192.0.2.1")
        self.assertEqual(
            {
                f"{ipaddr['address']}__{ipaddress.ip_interface(ipaddr['address']).network.with_prefixlen}__Global"
                for ipaddr in fixtures.IP_INTF_FIXTURE
            },
            {ipaddr.get_unique_id() for ipaddr in self.cvp.get_all("ipaddr")},
        )

    def test_load_ip_addresses_marks_matching_address_primary(self):
        """Regression test for #1174: only the IP equal to primary_ip is marked primary.

        CloudVision's inventory ``ipAddress`` is a bare IP (no mask), while interface
        addresses include a prefix length, so the comparison must strip the mask.
        """
        mock_device = MagicMock()
        mock_device.name = "mock_device"
        mock_device.serial = "JPE12345678"
        primary_ip = "203.0.113.2"

        with (
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_ip_interfaces",
                self.cloudvision.get_ip_interfaces,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_description",
                self.cloudvision.get_interface_description,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_interface_vrf",
                self.cloudvision.get_interface_vrf,
            ),
        ):
            self.cvp.load_ip_addresses(dev=mock_device, primary_ip=primary_ip)

        primary_by_interface = {a.interface: a.primary for a in self.cvp.get_all("ipassignment")}
        self.assertTrue(primary_by_interface["Loopback2"])
        self.assertFalse(primary_by_interface["Loopback1"])
