"""Unit tests for the CloudVision DiffSync adapter class."""

import ipaddress
from unittest.mock import MagicMock, patch

from nautobot.apps.testing import TestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.aristacv.diffsync.adapters.cloudvision import (
    CloudvisionAdapter,
)
from nautobot_ssot.integrations.aristacv.jobs import CloudVisionDataSource
from nautobot_ssot.tests.aristacv.fixtures import fixtures


class CloudvisionAdapterTestCase(TestCase):
    """Test the CloudvisionAdapter class."""

    job_class = CloudVisionDataSource
    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Method to initialize test case."""
        super().setUpTestData()
        cls.client = MagicMock()
        cls.client.comm_channel = MagicMock()
        cls.client.get_inventory = MagicMock(return_value=fixtures.INVENTORY_FIXTURE)
        cls.client.get_version = MagicMock(return_value="2024.3.0")

        cls.cloudvision = MagicMock()
        cls.cloudvision.get_tags_by_type = MagicMock()
        cls.cloudvision.get_tags_by_type.return_value = []
        cls.cloudvision.get_device_type = MagicMock()
        cls.cloudvision.get_device_type.return_value = "fixedSystem"
        cls.cloudvision.get_interfaces_fixed = MagicMock()
        cls.cloudvision.get_interfaces_fixed.return_value = fixtures.FIXED_INTERFACE_FIXTURE
        cls.cloudvision.get_interfaces_port_channel = MagicMock()
        cls.cloudvision.get_interfaces_port_channel.return_value = fixtures.PORT_CHANNEL_INTERFACE_FIXTURE
        cls.cloudvision.get_port_channel_members = MagicMock()
        cls.cloudvision.get_port_channel_members.return_value = fixtures.PORT_CHANNEL_MEMBERS_FIXTURE
        all_intf_names = [
            port["interface"] for port in (*fixtures.PORT_CHANNEL_INTERFACE_FIXTURE, *fixtures.FIXED_INTERFACE_FIXTURE)
        ]
        cls.cloudvision.get_all_interface_modes = MagicMock()
        cls.cloudvision.get_all_interface_modes.return_value = {name: "access" for name in all_intf_names}
        cls.cloudvision.get_all_interface_transceivers = MagicMock()
        cls.cloudvision.get_all_interface_transceivers.return_value = {
            name: "1000BASE-T" for name in all_intf_names if not name.startswith("Port-Channel")
        }
        cls.cloudvision.get_all_interface_descriptions = MagicMock()
        cls.cloudvision.get_all_interface_descriptions.return_value = {name: "Uplink to DC1" for name in all_intf_names}
        cls.cloudvision.get_routed_interface_description = MagicMock()
        cls.cloudvision.get_routed_interface_description.return_value = "hello!"
        cls.cloudvision.get_ip_interfaces = MagicMock()
        cls.cloudvision.get_ip_interfaces.return_value = fixtures.IP_INTF_FIXTURE
        cls.cloudvision.get_interface_vrf = MagicMock()
        cls.cloudvision.get_interface_vrf.return_value = "Global"

        cls.job = cls.job_class()
        cls.job.job_result = JobResult.objects.create(name=cls.job.class_path, task_name="fake task", worker="default")
        cls.cvp = CloudvisionAdapter(job=cls.job, conn=cls.client)

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
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_all_interface_modes",
                self.cloudvision.get_all_interface_modes,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_all_interface_transceivers",
                self.cloudvision.get_all_interface_transceivers,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_all_interface_descriptions",
                self.cloudvision.get_all_interface_descriptions,
            ),
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
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_all_interface_modes",
                self.cloudvision.get_all_interface_modes,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_all_interface_transceivers",
                self.cloudvision.get_all_interface_transceivers,
            ),
            patch(
                "nautobot_ssot.integrations.aristacv.utils.cloudvision.get_all_interface_descriptions",
                self.cloudvision.get_all_interface_descriptions,
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
