"""Unit test for LibreNMS Location and Device models."""

import json
import os
import uuid
from unittest.mock import MagicMock, patch
from typing import List, Optional
from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import Job, JobResult
from nautobot_ssot.integrations.librenms.diffsync.adapters.librenms import LibrenmsAdapter
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataSource
from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import Location, Device
from nautobot.extras.models import Status


def load_json(path):
    """Load a JSON file."""
    with open(path, encoding="utf-8") as file:
        return json.load(file)


DEVICE_FIXTURE = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_devices.json")["devices"]
LOCATION_FIXTURE = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_locations.json")["locations"]

class TestLibreNMSAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotLibreNMSAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize test case."""
        self.librenms_client = MagicMock()

        # Mock device and location data
        self.librenms_client.get_librenms_devices_from_file.return_value = {
            "devices": DEVICE_FIXTURE,
            "count": len(DEVICE_FIXTURE),
        }
        self.librenms_client.get_librenms_locations_from_file.return_value = {
            "locations": LOCATION_FIXTURE,
            "count": len(LOCATION_FIXTURE),
        }

        self.job = LibrenmsDataSource()
        self.job.logger.warning = MagicMock()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.librenms_adapter = LibrenmsAdapter(job=self.job, sync=None, librenms_api=self.librenms_client)

    def test_data_loading(self):
        """Test that devices and locations are loaded correctly."""
        self.librenms_adapter.load()

        # Debugging outputs
        print("Adapter Devices:", list(self.librenms_adapter.get_all("device")))

        expected_locations = {loc["location"].strip() for loc in LOCATION_FIXTURE}
        loaded_locations = {loc.get_unique_id() for loc in self.librenms_adapter.get_all("location")}
        self.assertEqual(expected_locations, loaded_locations, "Locations are not loaded correctly.")

        expected_devices = {dev["sysName"].strip() for dev in DEVICE_FIXTURE}
        loaded_devices = {dev.get_unique_id() for dev in self.librenms_adapter.get_all("device")}
        self.assertEqual(expected_devices, loaded_devices, "Devices are not loaded correctly.")
