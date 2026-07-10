"""Unit tests for the Nautobot-side LibreNMS DiffSync models (NautobotDevice)."""

from unittest.mock import MagicMock

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType, LocationType, Manufacturer
from nautobot.dcim.models import Location as ORMLocation
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import NautobotDevice


class TestNautobotDeviceLocationSync(TestCase):
    """Test that NautobotDevice.update() honors the sync_locations job flag for the location field."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up a Nautobot Device already assigned to a real Location, plus a second candidate Location."""
        super().setUp()
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        self.active_status.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        self.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.chicago = ORMLocation.objects.create(
            name="Chicago", location_type=self.site_type, status=self.active_status
        )
        self.catch_all = ORMLocation.objects.create(
            name="Catch-All", location_type=self.site_type, status=self.active_status
        )

        manufacturer, _ = Manufacturer.objects.get_or_create(name="Generic")
        device_type, _ = DeviceType.objects.get_or_create(model="Test Device Type", manufacturer=manufacturer)
        role, _ = Role.objects.get_or_create(name="Test Role")
        role.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.orm_device = ORMDevice.objects.create(
            name="test-device",
            device_type=device_type,
            status=self.active_status,
            role=role,
            location=self.chicago,
        )

        self.adapter = Adapter()
        self.adapter.job = MagicMock()
        self.adapter.job.location_type = self.site_type
        self.adapter.job.debug = False
        self.adapter.tenant = None

        self.diffsync_device = NautobotDevice(
            name="test-device",
            location="Chicago",
            status="Active",
            device_type="Test Device Type",
            manufacturer="Generic",
            system_of_record="LibreNMS",
            uuid=self.orm_device.id,
        )
        self.diffsync_device.adapter = self.adapter

    def test_update_does_not_overwrite_location_when_sync_locations_false(self):
        """Reparented devices must not be moved back by a later sync when sync_locations is False."""
        self.adapter.job.sync_locations = False

        self.diffsync_device.update(attrs={"location": "Catch-All", "parent_location": None})

        self.orm_device.refresh_from_db()
        self.assertEqual(self.orm_device.location, self.chicago)

    def test_update_overwrites_location_when_sync_locations_true(self):
        """With sync_locations True, per-device location updates still apply."""
        self.adapter.job.sync_locations = True

        self.diffsync_device.update(attrs={"location": "Catch-All", "parent_location": None})

        self.orm_device.refresh_from_db()
        self.assertEqual(self.orm_device.location, self.catch_all)

    def test_create_assigns_location_regardless_of_sync_locations(self):
        """A brand-new device must still get a location even when sync_locations is False."""
        self.adapter.job.sync_locations = False

        ids = {"name": "new-device"}
        attrs = {
            "location": "Catch-All",
            "parent_location": None,
            "status": "Active",
            "device_type": "Test Device Type",
            "manufacturer": "Linux",
            "platform": "linux",
            "role": "Test Role",
            "serial_no": "SN123",
            "os_version": "1.0",
            "device_id": 1,
            "system_of_record": "LibreNMS",
        }

        NautobotDevice.create(self.adapter, ids, attrs)

        new_orm_device = ORMDevice.objects.get(name="new-device")
        self.assertEqual(new_orm_device.location, self.catch_all)
