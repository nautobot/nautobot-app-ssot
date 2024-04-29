"""Test the Job classes in nautobot_ssot."""

import os.path
from unittest.mock import Mock, call

from django.db.utils import IntegrityError, OperationalError
from django.test import override_settings

from nautobot.extras.models import JobResult
from nautobot.core.testing import TransactionTestCase

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.tests.jobs import DataSyncBaseJob, DataSource, DataTarget
from nautobot_ssot.models import SyncLogEntry


@override_settings(JOBS_ROOT=os.path.join(os.path.dirname(__file__), "jobs"))
class BaseJobTestCase(TransactionTestCase):
    """Test the DataSyncBaseJob class."""

    job_class = DataSyncBaseJob
    databases = (
        "default",
        "job_logs",
    )

    def setUp(self):
        """Per-test setup."""
        super().setUp()
        self.job = self.job_class()

        self.job.job_result = JobResult.objects.create(
            name="fake job",
            task_name="fake job",
            worker="default",
        )

        self.job.load_source_adapter = lambda *x, **y: None
        self.job.load_target_adapter = lambda *x, **y: None

    def test_sync_log(self):
        """Test the sync_log() method."""
        self.job.run(dryrun=True, memory_profiling=False)
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
        self.assertTrue(form.fields["dryrun"].initial)

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
        self.job.run(dryrun=True, memory_profiling=False)
        self.assertIsNotNone(self.job.sync)
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)
        self.assertIsNotNone(self.job.sync.diff_time)
        self.assertIsNone(self.job.sync.sync_time)
        self.assertEqual(self.job.sync.source, self.job.data_source)
        self.assertEqual(self.job.sync.target, self.job.data_target)
        self.assertTrue(self.job.dryrun)
        self.assertEqual(self.job.job_result, self.job.sync.job_result)

    def test_calculate_diff(self):
        """Test calculate_diff() method."""
        self.job.sync = Mock()
        self.job.source_adapter = Mock()
        self.job.target_adapter = Mock()
        self.job.source_adapter.diff_to().dict.return_value = {}
        self.job.calculate_diff()
        self.job.source_adapter.diff_to.assert_called()
        self.job.sync.save.assert_has_calls([call(), call()])

    def test_calculate_diff_fail_diff_save_too_large(self):
        """Test calculate_diff() method logs failure."""
        self.job.sync = Mock()
        self.job.sync.save.side_effect = [None, OperationalError("Fail")]
        self.job.source_adapter = Mock()
        self.job.target_adapter = Mock()
        self.job.logger.info = Mock()
        self.job.logger.warning = Mock()
        self.job.source_adapter.diff_to().dict.return_value = {}
        self.job.calculate_diff()
        self.job.logger.warning.assert_any_call(
            "Unable to save JSON diff to the database; likely the diff is too large."
        )

    def test_calculate_diff_fail_diff_save_generic(self):
        """Test calculate_diff() method logs failure."""
        self.job.sync = Mock()
        self.job.sync.save.side_effect = [None, IntegrityError("Fail")]
        self.job.source_adapter = Mock()
        self.job.target_adapter = Mock()
        self.job.logger.info = Mock()
        self.job.logger.warning = Mock()
        self.job.source_adapter.diff_to().dict.return_value = {}
        with self.assertRaises(IntegrityError):
            self.job.calculate_diff()


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
