"""Tests for the Cisco SD-WAN Nautobot (target) adapter."""

from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import (
    Controller,
    ControllerManagedDeviceGroup,
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.cisco_sdwan.diffsync.adapters.nautobot import CiscoSdwanNautobotAdapter


class TestCiscoSdwanNautobotAdapter(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test the CiscoSdwanNautobotAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Create the Nautobot objects shared by the tests."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        self.status_retired = Status.objects.get_or_create(name="Retired")[0]
        for model in [Controller, Device, Interface]:
            self.status_active.content_types.add(ContentType.objects.get_for_model(model))
            self.status_retired.content_types.add(ContentType.objects.get_for_model(model))

        location_type = LocationType.objects.get_or_create(name="Site")[0]
        location_type.content_types.add(ContentType.objects.get_for_model(Device))
        location_type.content_types.add(ContentType.objects.get_for_model(Controller))
        self.location = Location.objects.create(name="Staging", location_type=location_type, status=self.status_active)

        manufacturer = Manufacturer.objects.get_or_create(name="Cisco")[0]
        self.device_type = DeviceType.objects.get_or_create(model="C8000V", manufacturer=manufacturer)[0]
        self.platform = Platform.objects.get_or_create(name="cisco_ios", manufacturer=manufacturer)[0]
        self.device_role = Role.objects.get_or_create(name="Router")[0]
        self.device_role.content_types.add(ContentType.objects.get_for_model(Device))

        controller = Controller.objects.create(name="SD-WAN Manager", status=self.status_active, location=self.location)
        self.managed_device_group = ControllerManagedDeviceGroup.objects.create(
            name="SD-WAN Managed Devices", controller=controller
        )

        self.active_device = self._create_device("sdwan-edge-01", self.status_active, in_group=True)
        self.retired_device = self._create_device("sdwan-edge-rtd", self.status_retired, in_group=True)
        self.unmanaged_device = self._create_device("other-device-01", self.status_active, in_group=False)

        Interface.objects.create(
            name="GigabitEthernet1",
            device=self.active_device,
            status=self.status_active,
            type="other",
            mtu=1500,
            enabled=True,
        )
        Interface.objects.create(
            name="GigabitEthernet1",
            device=self.unmanaged_device,
            status=self.status_active,
            type="other",
        )

        self.job = MagicMock()
        self.job.devices = None
        self.job.managed_device_group = self.managed_device_group
        self.adapter = CiscoSdwanNautobotAdapter(job=self.job, sync=None)

    def _create_device(self, name, status, in_group):
        """Create a Device, optionally assigned to the managed device group."""
        device = Device.objects.create(
            name=name,
            status=status,
            role=self.device_role,
            device_type=self.device_type,
            platform=self.platform,
            location=self.location,
        )
        if in_group:
            device.controller_managed_device_group = self.managed_device_group
            device.validated_save()
        return device

    def test_load_devices_scoped_to_group_and_status(self):
        """Validate only non-retired Devices in the managed device group are loaded."""
        self.adapter.load()
        self.assertEqual(
            {"sdwan-edge-01"},
            {device.get_unique_id() for device in self.adapter.get_all("device")},
        )

    def test_load_devices_with_device_filter(self):
        """Validate the Job device filter is honored."""
        self.job.devices = [self.retired_device.id]
        self.adapter.load()
        self.assertEqual(set(), {device.get_unique_id() for device in self.adapter.get_all("device")})

    def test_load_interfaces_scoped_to_group(self):
        """Validate only Interfaces of Devices in the managed device group are loaded."""
        self.adapter.load()
        self.assertEqual(
            {"sdwan-edge-01__GigabitEthernet1"},
            {interface.get_unique_id() for interface in self.adapter.get_all("interface")},
        )

    def test_load_device_types_requires_metadata(self):
        """Validate DeviceTypes are not loaded without integration metadata present."""
        self.adapter.load()
        self.assertEqual([], list(self.adapter.get_all("device_type")))

    def test_load_software_versions_requires_metadata(self):
        """Validate SoftwareVersions are not loaded without integration metadata present."""
        self.adapter.load()
        self.assertEqual([], list(self.adapter.get_all("software_version")))
