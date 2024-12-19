"""Unit test for Nautobot object models."""

import json
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import DeviceType, LocationType, Manufacturer, Platform
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import Location as ORMLocation
from nautobot.extras.models import Job, JobResult, Role, Status

from nautobot_ssot.integrations.librenms.constants import (
    librenms_status_map,
    os_manufacturer_map,
)
from nautobot_ssot.integrations.librenms.diffsync.adapters.librenms import (
    LibrenmsAdapter,
)
from nautobot_ssot.integrations.librenms.diffsync.adapters.nautobot import (
    NautobotAdapter,
)
from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import (
    Device,
    Location,
)
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataSource


def load_json(path):
    """Load a JSON file."""
    with open(path, encoding="utf-8") as file:
        return json.load(file)


DEVICE_FIXTURE = load_json(
    "./nautobot_ssot/tests/librenms/fixtures/get_librenms_devices.json"
)["devices"]
LOCATION_FIXTURE = load_json(
    "./nautobot_ssot/tests/librenms/fixtures/get_librenms_locations.json"
)["locations"]


class TestNautobotAdapterTestCase(TransactionTestCase):
    """Test NautobotAdapter class for loading devices from the ORM."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize test case and populate the database."""
        self.active_status, _ = Status.objects.get_or_create(
            name="Active", defaults={"slug": "active"}
        )

        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        self.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        for location in LOCATION_FIXTURE:
            ORMLocation.objects.create(
                name=location["location"],
                location_type=self.site_type,
                latitude=location.get("lat"),
                longitude=location.get("lng"),
                status=self.active_status,
            )

        for device in DEVICE_FIXTURE:
            location = ORMLocation.objects.get(name=device["location"])
            _manufacturer, _ = Manufacturer.objects.get_or_create(
                name=os_manufacturer_map[device["os"]]
            )
            _role, _role_created = Role.objects.get_or_create(name=device["type"])
            if _role_created:
                _role.content_types.add(ContentType.objects.get_for_model(ORMDevice))
            _status, _ = Status.objects.get_or_create(
                name=librenms_status_map[device["status"]]
            )
            _device_type, _ = DeviceType.objects.get_or_create(
                model=device["hardware"], manufacturer=_manufacturer
            )
            _platform, _ = Platform.objects.get_or_create(
                name=device["os"], manufacturer=_manufacturer
            )
            ORMDevice.objects.create(
                name=device["sysName"],
                device_type=_device_type,
                role=_role,
                location=location,
                status=_status,
                serial=device["serial"],
                platform=_platform,
            )

        self.job = LibrenmsDataSource()
        self.job.logger.warning = MagicMock()
        self.job.sync_locations = True
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )

        self.nautobot_adapter = NautobotAdapter(job=self.job, sync=None)

    def test_load_devices(self):
        """Test that devices are correctly loaded from the Nautobot ORM."""
        self.nautobot_adapter.load()

        # Get all devices from the adapter
        loaded_devices = {
            device.get_unique_id() for device in self.nautobot_adapter.get_all("device")
        }

        # Expected devices from the fixture
        expected_devices = {device["sysName"] for device in DEVICE_FIXTURE}

        # Verify that all expected devices were loaded
        self.assertEqual(
            expected_devices, loaded_devices, "Devices were not loaded correctly."
        )

        # Verify attributes for each device
        for device in DEVICE_FIXTURE:
            loaded_device = self.nautobot_adapter.get("device", {"name": device["sysName"]})
            print(f"Loaded device: {loaded_device}")
            print(f"Loaded device type: {type(loaded_device)}")
            self.assertIsNotNone(
                loaded_device, f"Device {device['sysName']} not found in the adapter."
            )
