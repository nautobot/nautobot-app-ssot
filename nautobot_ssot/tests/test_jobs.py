"""Test the Job classes in nautobot_ssot."""
import uuid
from django.contrib.contenttypes.models import ContentType

from django.forms import HiddenInput
from django.test import TestCase

from nautobot.extras.models import JobResult

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.jobs.base import DataSyncBaseJob
from nautobot_ssot.jobs import DataSource, DataTarget
from nautobot_ssot.models import SyncLogEntry


class BaseJobTestCase(TestCase):
    """Test the DataSyncBaseJob class."""

    job_class = DataSyncBaseJob

    def setUp(self):
        """Per-test setup."""
        self.job = self.job_class()

        self.job.job_result = JobResult.objects.create(
            name="fake job",
            obj_type=ContentType.objects.get(app_label="extras", model="job"),
            job_id=uuid.uuid4(),
        )

        self.job.load_source_adapter = lambda *x, **y: None
        self.job.load_target_adapter = lambda *x, **y: None

    def test_sync_log(self):
        """Test the sync_log() method."""
        self.job.run(data={"dry_run": True, "memory_profiling": False}, commit=True)
        self.assertIsNotNone(self.job.sync)
        # Minimal parameters
        self.job.sync_log(
            action=SyncLogEntryActionChoices.ACTION_CREATE,
            status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
        )
        # Maximal parameters
        self.job.sync_log(
            action=SyncLogEntryActionChoices.ACTION_DELETE,
            status=SyncLogEntryStatusChoices.STATUS_ERROR,
            message="Whoops!",
            diff={"-": {"everything": "goodbye"}},
            synced_object=None,
            object_repr="Nothing to delete",
        )

        self.assertEqual(2, SyncLogEntry.objects.count())

    def test_as_form(self):
        """Test the as_form() method."""
        form = self.job.as_form()
        # Dry run flag defaults to true unless configured otherwise
        self.assertTrue(form.fields["dry_run"].initial)
        # Commit field is hidden to reduce user confusion
        self.assertIsInstance(form.fields["_commit"].widget, HiddenInput)

    def test_data_source(self):
        """Test the data_source property."""
        self.assertEqual(self.job.data_source, self.job_class.__name__)

    def test_data_target(self):
        """Test the data_target property."""
        self.assertEqual(self.job.data_target, self.job_class.__name__)

    def test_data_source_icon(self):
        """Test the data_source_icon property."""
        self.assertIsNone(self.job.data_source_icon)

    def test_data_target_icon(self):
        """Test the data_target_icon property."""
        self.assertIsNone(self.job.data_target_icon)

    def test_run(self):
        """Test the run() method."""
        self.job.run(data={"dry_run": True, "memory_profiling": False}, commit=True)
        self.assertIsNotNone(self.job.sync)
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)
        self.assertIsNotNone(self.job.sync.diff_time)
        self.assertIsNone(self.job.sync.sync_time)
        self.assertEqual(self.job.sync.source, self.job.data_source)
        self.assertEqual(self.job.sync.target, self.job.data_target)
        self.assertTrue(self.job.sync.dry_run)
        self.assertEqual(self.job.job_result, self.job.sync.job_result)


class DataSourceTestCase(BaseJobTestCase):
    """Test the DataSource class."""

    job_class = DataSource

    def test_data_target(self):
        """Test the override of the data_target property."""
        self.assertEqual(self.job.data_target, "Nautobot")

    def test_data_target_icon(self):
        """Test the override of the data_target_icon property."""
        self.assertEqual(self.job.data_target_icon, "/static/img/nautobot_logo.png")


class DataTargetTestCase(BaseJobTestCase):
    """Test the DataTarget class."""

    job_class = DataTarget

    def test_data_source(self):
        """Test the override of the data_source property."""
        self.assertEqual(self.job.data_source, "Nautobot")

    def test_data_source_icon(self):
        """Test the override of the data_source_icon property."""
        self.assertEqual(self.job.data_source_icon, "/static/img/nautobot_logo.png")
