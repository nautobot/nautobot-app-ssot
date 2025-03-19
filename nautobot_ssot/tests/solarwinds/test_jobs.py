"""Tests to validate Job functions."""

import uuid
from unittest.mock import MagicMock

from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import LocationType
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.solarwinds.jobs import JobConfigError, SolarWindsDataSource


class SolarWindsDataSourceTestCase(TransactionTestCase):
    """Test the SolarWindsDataSource class."""

    job_class = SolarWindsDataSource
    databases = ("default", "job_logs")

    def setUp(self):
        """Per-test setup."""
        super().setUp()
        self.job = self.job_class()
        self.job.logger.error = MagicMock()

        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="Fake task", user=None, id=uuid.uuid4()
        )

    def test_validate_containers_blank(self):
        """Validate handling of no containers being defined in Job form."""
        self.job.containers = ""
        with self.assertRaises(JobConfigError):
            self.job.validate_containers()
        self.job.logger.error.assert_called_once_with(
            "Containers variable must be defined with container name(s) or 'ALL'."
        )

    def test_validate_containers_missing_top(self):
        """Validate handling of top container not defined when 'ALL' containers specified."""
        self.job.containers = "ALL"
        self.job.top_container = ""
        self.job.pull_from = "Containers"
        with self.assertRaises(JobConfigError):
            self.job.validate_containers()
        self.job.logger.error.assert_called_once_with(
            "Top Container must be specified if `ALL` Containers are to be imported."
        )

    def test_validate_location_configuration_missing_parent(self):
        """Validate handling of validate_location_configuration() when parent Location isn't specified but required."""
        reg_lt = LocationType.objects.create(name="Region")
        site_lt = LocationType.objects.create(name="Site", parent=reg_lt)
        self.job.location_type = site_lt
        self.job.parent = None
        with self.assertRaises(JobConfigError):
            self.job.validate_location_configuration()
        self.job.logger.error.assert_called_once_with("LocationType %s requires Parent Location be specified.", site_lt)

    def test_validate_location_configuration_extra_parent(self):
        """Validate handling of validate_location_configuration() when parent Location is specified, but not required."""
        reg_lt = LocationType.objects.create(name="Region")
        site_lt = LocationType.objects.create(name="Site")
        self.job.location_type = site_lt
        self.job.parent = reg_lt
        with self.assertRaises(JobConfigError):
            self.job.validate_location_configuration()
        self.job.logger.error.assert_called_once_with(
            "LocationType %s does not require a Parent location, but a Parent location was chosen.", site_lt
        )

    def test_validate_location_configuration_missing_location_type(self):
        self.job.pull_from = "Containers"
        self.job.location_type = None
        self.job.location_override = None
        with self.assertRaises(JobConfigError):
            self.job.validate_location_configuration()
        self.job.logger.error.assert_called_once_with(
            "A Location Type must be specified, unless using Location Override."
        )

    def test_validate_location_configuration_missing_device_contenttype(self):
        """Validate handling of validate_location_configuration() when Device ContentType on the specified LocationType."""
        site_lt = LocationType.objects.create(name="Site")
        self.job.location_type = site_lt
        self.job.parent = None
        with self.assertRaises(JobConfigError):
            self.job.validate_location_configuration()
        self.job.logger.error.assert_called_once_with(
            "Specified LocationType %s is missing Device ContentType. Please change LocationType or add Device ContentType to %s LocationType and re-run Job.",
            site_lt,
            site_lt,
        )

    def test_validate_role_map(self):
        """Validate handling of validate_role_map() when Role choice isn't specified."""
        self.job.role_map = {"ASR1001": "Router"}
        self.job.role_choice = None
        with self.assertRaises(JobConfigError):
            self.job.validate_role_map()
        self.job.logger.error.assert_called_once_with(
            "Role Map Matching Attribute must be defined if Role Map is specified."
        )
