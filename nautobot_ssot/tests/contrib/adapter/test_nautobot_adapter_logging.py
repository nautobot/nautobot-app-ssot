"""Tests for contrib.NautobotModel."""

# from nautobot.core.testing import TestCase
from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock

from nautobot.dcim.models import LocationType

from nautobot_ssot.contrib.adapter import NautobotAdapter
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.jobs.examples import ExampleDataSource


class LocationTypeModel(NautobotModel):
    """Demo Lcoation Type Model."""

    _model = LocationType
    _modelname = "location_type"


class DemoAdapter(NautobotAdapter):
    """Demo Nautobot Adapter."""

    top_level = ["location_type"]
    location_type = LocationTypeModel


class TestLogLoadedObjects(TestCase):
    """Unittests for `nautobot_ssot.contrib.adapter.NautobotAdapter.log_loaded_objects`."""

    def setUp(self):
        """Setup the test cases."""
        self.adapter = DemoAdapter(
            job=ExampleDataSource(),
            sync=MagicMock(),
        )
        self.adapter.enable_progress_logger = True

    def test_counter_increment_by_one(self):
        """Test incrementing counter by one."""
        start_count = deepcopy(self.adapter.objects_loaded)
        self.adapter.log_loaded_objects()
        self.assertEqual(self.adapter.objects_loaded, start_count + 1)

    def test_counter_increment_by_five(self):
        """Test incrementing counter by five."""
        start_count = deepcopy(self.adapter.objects_loaded)
        self.adapter.log_loaded_objects(5)
        self.assertEqual(self.adapter.objects_loaded, start_count + 5)

    def test_print_log_message(self):
        """Test log message triggered."""
        self.adapter.objects_loaded = 999
        with self.assertLogs(self.adapter.job.logger.name):
            self.adapter.log_loaded_objects()

    def test_disabled_logging(self):
        """Test that no log message is made with logging disabled."""
        self.adapter.enable_progress_logger = False
        self.adapter.objects_loaded = 999
        with self.assertNoLogs(self.adapter.job.logger.name):
            self.adapter.log_loaded_objects()
        self.assertEqual(self.adapter.objects_loaded, 999)
