"""Unit test for Nautobot object models."""

import json
from unittest.mock import MagicMock

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

        loaded_devices = {device.get_unique_id() for device in self.nautobot_adapter.get_all("device")}

        expected_devices = {device["sysName"] for device in DEVICE_FIXTURE[:1]}

        self.assertEqual(expected_devices, loaded_devices, "Devices were not loaded correctly.")

        for device in DEVICE_FIXTURE[:1]:
            loaded_device = self.nautobot_adapter.get("device", {"name": device["sysName"]})
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

        loaded_devices = {device.get_unique_id() for device in self.nautobot_adapter.get_all("device")}
        self.assertNotIn(
            "passive-patch-panel-01",
            loaded_devices,
            "Device without a Platform should not have been loaded.",
        )
        self.nautobot_adapter.job.logger.warning.assert_called_once_with(
            "Skipping device passive-patch-panel-01: no Platform assigned, cannot be synced with LibreNMS."
        )

    def test_load_devices_with_tenant_filter(self):
        """Test that a tenant filter loads only that tenant's devices, with the tenant populated."""
        tenant = Tenant.objects.create(name="Filter Tenant")
        device = ORMDevice.objects.get(name=DEVICE_FIXTURE[0]["sysName"])
        device.tenant = tenant
        device.validated_save()

        # A second device outside the tenant that would otherwise load fine.
        ORMDevice.objects.create(
            name="untenanted-device",
            device_type=device.device_type,
            role=device.role,
            location=device.location,
            status=device.status,
            platform=device.platform,
        )

        adapter = NautobotAdapter(job=self.job, sync=None, tenant=tenant)
        adapter.load_device()

        loaded_devices = {loaded.get_unique_id() for loaded in adapter.get_all("device")}
        self.assertEqual(loaded_devices, {device.name}, "Only devices in the selected tenant should be loaded.")
        self.assertEqual(adapter.get("device", {"name": device.name}).tenant, "Filter Tenant")

    def test_load_devices_without_tenant_filter_loads_all(self):
        """Test that omitting the tenant filter loads devices with and without a tenant."""
        tenant = Tenant.objects.create(name="Some Tenant")
        device = ORMDevice.objects.get(name=DEVICE_FIXTURE[0]["sysName"])
        tenanted_device = ORMDevice.objects.create(
            name="tenanted-device",
            device_type=device.device_type,
            role=device.role,
            location=device.location,
            status=device.status,
            platform=device.platform,
            tenant=tenant,
        )

        adapter = NautobotAdapter(job=self.job, sync=None)
        adapter.load_device()

        loaded_devices = {loaded.get_unique_id() for loaded in adapter.get_all("device")}
        self.assertEqual(
            loaded_devices,
            {device.name, tenanted_device.name},
            "Without a tenant filter, all devices should be loaded.",
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
