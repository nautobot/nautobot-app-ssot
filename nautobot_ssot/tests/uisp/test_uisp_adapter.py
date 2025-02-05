"""Test UISP adapter."""

import json
import uuid
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models import Job, JobResult
from nautobot.core.testing import TransactionTestCase
from nautobot_ssot_uisp.diffsync.adapters.uisp import UispAdapter
from nautobot_ssot_uisp.jobs import UispDataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


DEVICE_FIXTURE = load_json("./nautobot_ssot_uisp/tests/fixtures/get_devices.json")


class TestUispAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotUispAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):  # pylint: disable=invalid-name
        """Initialize test case."""
        self.uisp_client = MagicMock()
        self.uisp_client.get_devices.return_value = DEVICE_FIXTURE

        self.job = UispDataSource()
        self.job.job_result = JobResult.objects.create(name=self.job.class_path)
        self.uisp = UispAdapter(job=self.job, sync=None, client=self.uisp_client)

    def test_data_loading(self):
        """Test Nautobot Ssot Uisp load() function."""
        # self.uisp.load()
        # self.assertEqual(
        #     {dev["name"] for dev in DEVICE_FIXTURE},
        #     {dev.get_unique_id() for dev in self.uisp.get_all("device")},
        # )
