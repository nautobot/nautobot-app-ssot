"""Test LibreNMS adapter."""

import json
import uuid
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models import Job, JobResult
from nautobot.core.testing import TransactionTestCase
from nautobot_ssot_librenms.diffsync.adapters.librenms import LibrenmsAdapter
from nautobot_ssot_librenms.jobs import LibrenmsDataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


DEVICE_FIXTURE = load_json("./nautobot_ssot_librenms/tests/fixtures/get_devices.json")


class TestLibrenmsAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotLibrenmsAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):  # pylint: disable=invalid-name
        """Initialize test case."""
        self.librenms_client = MagicMock()
        self.librenms_client.get_devices.return_value = DEVICE_FIXTURE

        self.job = LibrenmsDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, obj_type=ContentType.objects.get_for_model(Job), user=None, job_id=uuid.uuid4()
        )
        self.librenms = LibrenmsAdapter(job=self.job, sync=None, client=self.librenms_client)

    def test_data_loading(self):
        """Test Nautobot Ssot Librenms load() function."""
        # self.librenms.load()
        # self.assertEqual(
        #     {dev["name"] for dev in DEVICE_FIXTURE},
        #     {dev.get_unique_id() for dev in self.librenms.get_all("device")},
        # )
