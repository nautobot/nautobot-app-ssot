"""Unit test for Nautobot object models."""

import json
from unittest.mock import MagicMock

from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType, LocationType, Manufacturer, Platform
from nautobot.dcim.models import Location as ORMLocation
from nautobot.extras.models import JobResult, Role, Status
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.librenms.constants import (
    librenms_status_map,
    os_manufacturer_map,
)
from nautobot_ssot.integrations.librenms.diffsync.adapters.nautobot import (
    NautobotAdapter,
)
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataSource
from nautobot_ssot.integrations.librenms.utils import build_device_unique_id


def load_json(path):
    """Load a JSON file."""
    with open(path, encoding="utf-8") as file:
        return json.load(file)


DEVICE_FIXTURE = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_devices.json")["devices"]
LOCATION_FIXTURE = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_locations.json")["locations"]


class TestNautobotAdapterTestCase(TestCase):
    """Test NautobotAdapter class for loading devices from the ORM."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Initialize test case and populate the database."""
        cls.active_status, _ = Status.objects.get_or_create(name="Active")
        cls.active_status.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        cls.site_type, _ = LocationType.objects.get_or_create(name="Site")
        cls.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        for location in LOCATION_FIXTURE:
            ORMLocation.objects.create(
                name=location["location"],
                location_type=cls.site_type,
                latitude=location.get("lat"),
                longitude=location.get("lng"),
                status=cls.active_status,
            )

        for device in DEVICE_FIXTURE[:1]:
            location = ORMLocation.objects.get(name=device["location"])
            _manufacturer, _ = Manufacturer.objects.get_or_create(name=os_manufacturer_map[device["os"]])
            _role, _role_created = Role.objects.get_or_create(name=device["type"])
            if _role_created:
                _role.content_types.add(ContentType.objects.get_for_model(ORMDevice))
            _status, _ = Status.objects.get_or_create(name=librenms_status_map[device["status"]])
            _device_type, _ = DeviceType.objects.get_or_create(model=device["hardware"], manufacturer=_manufacturer)
            _platform, _ = Platform.objects.get_or_create(name=device["os"], manufacturer=_manufacturer)
            ORMDevice.objects.create(
                name=device["sysName"],
                device_type=_device_type,
                role=_role,
                location=location,
                status=_status,
                serial=device["serial"],
                platform=_platform,
            )

        cls.job = LibrenmsDataSource()
        cls.job.logger.warning = MagicMock()
        cls.job.sync_locations = True
        cls.job.job_result = JobResult.objects.create(name=cls.job.class_path, task_name="fake task", worker="default")

        cls.nautobot_adapter = NautobotAdapter(job=cls.job, sync=None)

    def test_load_devices(self):
        """Test that devices are correctly loaded from the Nautobot ORM."""
        self.nautobot_adapter.load()

        loaded_devices = {device.name for device in self.nautobot_adapter.get_all("device")}

        expected_devices = {device["sysName"] for device in DEVICE_FIXTURE[:1]}

        self.assertEqual(expected_devices, loaded_devices, "Devices were not loaded correctly.")

        for device in DEVICE_FIXTURE[:1]:
            unique_id = build_device_unique_id(None, None, device["sysName"])
            loaded_device = self.nautobot_adapter.get("device", {"unique_id": unique_id})
            print(f"Loaded device: {loaded_device}")
            print(f"Loaded device type: {type(loaded_device)}")
            self.assertIsNotNone(loaded_device, f"Device {device['sysName']} not found in the adapter.")

    def test_load_devices_skips_device_without_platform(self):
        """Test that a device with no Platform assigned is skipped instead of crashing the load."""
        location = ORMLocation.objects.get(name=DEVICE_FIXTURE[0]["location"])
        manufacturer, _ = Manufacturer.objects.get_or_create(name=os_manufacturer_map[DEVICE_FIXTURE[0]["os"]])
        role, _ = Role.objects.get_or_create(name=DEVICE_FIXTURE[0]["type"])
        status, _ = Status.objects.get_or_create(name=librenms_status_map[DEVICE_FIXTURE[0]["status"]])
        device_type, _ = DeviceType.objects.get_or_create(model="Passive Patch Panel", manufacturer=manufacturer)
        ORMDevice.objects.create(
            name="passive-patch-panel-01",
            device_type=device_type,
            role=role,
            location=location,
            status=status,
            serial="PP-0001",
            platform=None,
        )

        self.nautobot_adapter.job.logger.warning.reset_mock()
        self.nautobot_adapter.load_device()

        loaded_devices = {device.name for device in self.nautobot_adapter.get_all("device")}
        self.assertNotIn(
            "passive-patch-panel-01",
            loaded_devices,
            "Device without a Platform should not have been loaded.",
        )
        self.nautobot_adapter.job.logger.warning.assert_called_once_with(
            "Skipping device passive-patch-panel-01: no Platform assigned, cannot be synced with LibreNMS."
        )

    def test_load_locations(self):
        """Test that locations are correctly loaded from the Nautobot ORM."""
        self.nautobot_adapter.load_location()

        loaded_locations = {location.get_unique_id() for location in self.nautobot_adapter.get_all("location")}

        expected_locations = {location["location"] for location in LOCATION_FIXTURE}

        self.assertEqual(expected_locations, loaded_locations, "Locations were not loaded correctly.")

        for location in LOCATION_FIXTURE:
            loaded_location = self.nautobot_adapter.get("location", {"name": location["location"]})
            self.assertIsNotNone(loaded_location, f"Location {location['location']} not found in the adapter.")

            # gps coordinates need to be truncated to 6 decimal places
            _latitude = None
            _longitude = None
            if isinstance(location.get("lng"), float):
                _longitude = round(location.get("lng"), 6)
            else:
                _longitude = location.get("lng")
            if isinstance(location.get("lat"), float):
                _latitude = round(location.get("lat"), 6)
            else:
                _latitude = location.get("lat")

            self.assertEqual(
                loaded_location.latitude,
                _latitude,
                f"Latitude mismatch for {location['location']}.",
            )
            self.assertEqual(
                loaded_location.longitude,
                _longitude,
                f"Longitude mismatch for {location['location']}.",
            )
            self.assertEqual(
                loaded_location.status,
                "Active",
                f"Status mismatch for {location['location']}.",
            )
            self.assertEqual(
                loaded_location.location_type,
                "Site",
                f"Location type mismatch for {location['location']}.",
            )


class TestNautobotAdapterTenantRenameLiveLookup(TestCase):
    """Confirm a Tenant rename between runs is picked up live, not cached anywhere."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up a Tenant and a Device assigned to it with a known librenms_device_id."""
        super().setUp()
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        self.active_status.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        self.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.location = ORMLocation.objects.create(
            name="Test Site", location_type=self.site_type, status=self.active_status
        )

        manufacturer, _ = Manufacturer.objects.get_or_create(name="Generic")
        device_type, _ = DeviceType.objects.get_or_create(model="Test Device Type", manufacturer=manufacturer)
        role, _ = Role.objects.get_or_create(name="Test Role")
        role.content_types.add(ContentType.objects.get_for_model(ORMDevice))
        platform, _ = Platform.objects.get_or_create(name="linux", defaults={"manufacturer": manufacturer})

        self.tenant = Tenant.objects.create(name="Old Name")

        self.device = ORMDevice.objects.create(
            name="tenant-rename-device",
            device_type=device_type,
            status=self.active_status,
            role=role,
            location=self.location,
            platform=platform,
            tenant=self.tenant,
        )
        self.device.custom_field_data["librenms_device_id"] = 77
        self.device.validated_save()

        self.job = LibrenmsDataSource()
        self.job.logger.warning = MagicMock()
        self.job.debug = False

    def test_rename_between_runs_is_read_live_not_cached(self):
        """The device resolves under the tenant's current name on every fresh load, before and after a rename."""
        adapter_before = NautobotAdapter(job=self.job, sync=None, tenant=self.tenant)
        adapter_before.load_device()

        old_unique_id = build_device_unique_id("Old Name", 77, "tenant-rename-device")
        self.assertIsNotNone(adapter_before.get("device", {"unique_id": old_unique_id}))

        self.tenant.name = "New Name"
        self.tenant.save()

        adapter_after = NautobotAdapter(job=self.job, sync=None, tenant=self.tenant)
        adapter_after.load_device()

        new_unique_id = build_device_unique_id("New Name", 77, "tenant-rename-device")
        self.assertIsNotNone(adapter_after.get("device", {"unique_id": new_unique_id}))

        with self.assertRaises(ObjectNotFound):
            adapter_after.get("device", {"unique_id": old_unique_id})
