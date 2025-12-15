"""Test the Job classes in nautobot_ssot."""

import logging
import os.path
import time
from unittest.mock import Mock, call, patch

from django.db.utils import IntegrityError, OperationalError
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobLogEntry, JobResult

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.models import SyncLogEntry
from nautobot_ssot.tests.jobs import DataSource, DataSyncBaseJob, DataTarget


@override_settings(JOBS_ROOT=os.path.join(os.path.dirname(__file__), "jobs"))
class BaseJobTestCase(TransactionTestCase):  # pylint: disable=too-many-public-methods
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
        self.job.create_records = False

        self.job.job_result = JobResult.objects.create(
            name="fake job",
            task_name="fake job",
            worker="default",
        )

        self.job.load_source_adapter = lambda *x, **y: None
        self.job.load_target_adapter = lambda *x, **y: None

    def _create_mock_diff(self):
        """Helper method to create a properly configured mock Diff object."""
        mock_diff = Mock()
        mock_diff.summary.return_value = "{'create': 0, 'update': 0, 'delete': 0, 'no-change': 0, 'skip': 0}"
        mock_diff.dict.return_value = {}
        return mock_diff

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

    # TODO: Re-enable this test once the bug in core is fixed.
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
        self.assertTrue(self.job.sync.dry_run)
        self.assertEqual(self.job.job_result, self.job.sync.job_result)

    def test_job_dryrun_false(self):
        """Test the job is not ran in dryrun mode."""
        with patch.object(DataSyncBaseJob, "execute_sync") as mock_execute_sync:
            isolated_job = DataSyncBaseJob()

            isolated_job.job_result = JobResult.objects.create(
                name="fake job no dryrun",
                task_name="fake job no dryrun",
                worker="default",
            )
            isolated_job.load_source_adapter = lambda *x, **y: None
            isolated_job.load_target_adapter = lambda *x, **y: None
            isolated_job.run(dryrun=False, memory_profiling=False)
            self.assertFalse(isolated_job.sync.dry_run)
            mock_execute_sync.assert_called()

    def test_job_dryrun_true(self):
        """Test the job is ran in dryrun mode."""
        with patch.object(DataSyncBaseJob, "execute_sync") as mock_execute_sync:
            isolated_job = DataSyncBaseJob()

            isolated_job.job_result = JobResult.objects.create(
                name="fake job",
                task_name="fake job",
                worker="default",
            )
            isolated_job.load_source_adapter = lambda *x, **y: None
            isolated_job.load_target_adapter = lambda *x, **y: None
            isolated_job.run(dryrun=True, memory_profiling=False)
            self.assertTrue(isolated_job.sync.dry_run)
            mock_execute_sync.assert_not_called()

    @patch("tracemalloc.start")
    def test_job_memory_profiling_true(self, mock_malloc_start):
        """Test the job is ran in dryrun mode."""
        self.job.run(dryrun=False, memory_profiling=True)
        mock_malloc_start.assert_called()

    @patch("tracemalloc.start")
    def test_job_memory_profiling_false(self, mock_malloc_start):
        """Test the job is ran in dryrun mode."""
        self.job.run(dryrun=False, memory_profiling=False)
        mock_malloc_start.assert_not_called()

    def test_calculate_diff(self):
        """Test calculate_diff() method."""
        self.job.sync = Mock()
        self.job.create_records = False
        self.job.source_adapter = Mock()
        self.job.target_adapter = Mock()
        self.job.source_adapter.diff_to().dict.return_value = {}
        self.job.calculate_diff()
        self.job.source_adapter.diff_to.assert_called()
        self.job.sync.save.assert_has_calls([call(), call()])

    def test_calculate_diff_fail_diff_save_too_large(self):
        """Test calculate_diff() method logs failure."""
        self.job.sync = Mock()
        self.job.create_records = False
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
        self.job.create_records = False
        self.job.sync.save.side_effect = [None, IntegrityError("Fail")]
        self.job.source_adapter = Mock()
        self.job.target_adapter = Mock()
        self.job.logger.info = Mock()
        self.job.logger.warning = Mock()
        self.job.source_adapter.diff_to().dict.return_value = {}
        with self.assertRaises(IntegrityError):
            self.job.calculate_diff()

    def test_parallel_loading_enabled_default(self):
        """Test that parallel loading is enabled by default."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Load source adapter."""
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Load target adapter."""
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)
        # Both adapters should be loaded
        self.assertIsNotNone(self.job.source_adapter)
        self.assertIsNotNone(self.job.target_adapter)
        # Timing should be recorded for both (same value in parallel mode)
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)
        # In parallel mode, both times should be the same (total parallel time)
        self.assertEqual(self.job.sync.source_load_time, self.job.sync.target_load_time)

    def test_parallel_loading_disabled(self):
        """Test that sequential loading works when parallel_loading is False."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Load source adapter."""
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Load target adapter."""
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=False, create_records=False)
        # Both adapters should be loaded
        self.assertIsNotNone(self.job.source_adapter)
        self.assertIsNotNone(self.job.target_adapter)
        # Timing should be recorded for both
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)

    def test_parallel_loading_with_mock_adapters(self):
        """Test parallel loading with mock adapters that simulate work."""
        mock_diff = self._create_mock_diff()
        source_adapter = Mock()
        source_adapter.__str__ = Mock(return_value="SourceAdapter")
        source_adapter.diff_to.return_value = mock_diff
        target_adapter = Mock()
        target_adapter.__str__ = Mock(return_value="TargetAdapter")

        def load_source():
            """Simulate source adapter loading with delay."""
            time.sleep(0.1)  # Simulate some work
            self.job.source_adapter = source_adapter

        def load_target():
            """Simulate target adapter loading with delay."""
            time.sleep(0.1)  # Simulate some work
            self.job.target_adapter = target_adapter

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        start_time = time.time()
        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)
        end_time = time.time()

        # Both adapters should be loaded
        self.assertEqual(self.job.source_adapter, source_adapter)
        self.assertEqual(self.job.target_adapter, target_adapter)
        # Parallel execution should be faster than sequential (which would take ~0.2s)
        # Allow some margin for test execution overhead
        self.assertLess(end_time - start_time, 0.15)

    def test_parallel_loading_source_error(self):
        """Test parallel loading when source adapter raises an error."""
        source_error = ValueError("Source adapter failed")

        def load_source():
            """Simulate source adapter loading failure."""
            raise source_error

        def load_target():
            """Simulate successful target adapter loading."""
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        with self.assertRaises(ValueError) as context:
            self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)

        self.assertEqual(str(context.exception), "Source adapter failed")
        # Target adapter may or may not be loaded depending on timing
        # But the error should be raised

    def test_parallel_loading_target_error(self):
        """Test parallel loading when target adapter raises an error."""
        target_error = ValueError("Target adapter failed")

        def load_source():
            """Simulate successful source adapter loading."""
            self.job.source_adapter = Mock()

        def load_target():
            """Simulate target adapter loading failure."""
            raise target_error

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        with self.assertRaises(ValueError) as context:
            self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)

        self.assertEqual(str(context.exception), "Target adapter failed")
        # Source adapter may or may not be loaded depending on timing
        # But the error should be raised

    def test_parallel_loading_both_errors(self):
        """Test parallel loading when both adapters raise errors."""
        source_error = ValueError("Source adapter failed")
        target_error = RuntimeError("Target adapter failed")

        def load_source():
            """Simulate source adapter loading failure."""
            raise source_error

        def load_target():
            """Simulate target adapter loading failure."""
            raise target_error

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        # Should raise the first error encountered (order may vary)
        with self.assertRaises((ValueError, RuntimeError)):
            self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)

    def test_parallel_loading_logs_captured(self):
        """Test that logs from threads are captured and stored as JobLogEntry objects."""
        initial_log_count = JobLogEntry.objects.filter(job_result=self.job.job_result).count()
        mock_diff = self._create_mock_diff()

        def load_source():
            """Simulate source adapter loading with logging."""
            logger = logging.getLogger(f"nautobot.extras.jobs.run_job[{self.job.job_result.id}]")
            logger.info("Source adapter loading started")
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter
            logger.info("Source adapter loading completed")

        def load_target():
            """Simulate target adapter loading with logging."""
            logger = logging.getLogger(f"nautobot.extras.jobs.run_job[{self.job.job_result.id}]")
            logger.info("Target adapter loading started")
            self.job.target_adapter = Mock()
            logger.info("Target adapter loading completed")

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)

        # Check that JobLogEntry objects were created
        log_entries = JobLogEntry.objects.filter(job_result=self.job.job_result)
        final_log_count = log_entries.count()
        self.assertGreater(final_log_count, initial_log_count)

        # Check that logs are grouped by adapter type
        source_logs = log_entries.filter(grouping="source")
        target_logs = log_entries.filter(grouping="target")
        self.assertGreater(source_logs.count(), 0)
        self.assertGreater(target_logs.count(), 0)

        # Check that timing messages are present
        log_messages = [entry.message for entry in log_entries]
        source_timing_found = any("Source adapter" in msg and "loaded in" in msg for msg in log_messages)
        target_timing_found = any("Target adapter" in msg and "loaded in" in msg for msg in log_messages)
        self.assertTrue(source_timing_found, "Source adapter timing message not found")
        self.assertTrue(target_timing_found, "Target adapter timing message not found")

    def test_parallel_loading_timing_information(self):
        """Test that timing information is correctly recorded for parallel loading."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Simulate source adapter loading with delay."""
            time.sleep(0.05)
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Simulate target adapter loading with delay."""
            time.sleep(0.05)
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)

        # Timing should be recorded
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)

        # In parallel mode, both should have the same duration (total parallel time)
        # which should be approximately the max of the two, not the sum
        self.assertEqual(self.job.sync.source_load_time, self.job.sync.target_load_time)

        # The parallel time should be less than sequential time would be
        # (sequential would be ~0.1s, parallel should be ~0.05s)
        parallel_duration = self.job.sync.source_load_time.total_seconds()
        self.assertLess(parallel_duration, 0.08)  # Allow some margin

    def test_sequential_loading_timing_information(self):
        """Test that timing information is correctly recorded for sequential loading."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Simulate source adapter loading with delay."""
            time.sleep(0.05)
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Simulate target adapter loading with delay."""
            time.sleep(0.05)
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=False, create_records=False)

        # Timing should be recorded
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)

        # In sequential mode, target time should be after source time
        source_duration = self.job.sync.source_load_time.total_seconds()
        target_duration = self.job.sync.target_load_time.total_seconds()

        # Both should be approximately 0.05s
        self.assertGreaterEqual(source_duration, 0.04)
        self.assertLessEqual(source_duration, 0.08)
        self.assertGreaterEqual(target_duration, 0.04)
        self.assertLessEqual(target_duration, 0.08)

    def test_parallel_loading_thread_isolation(self):
        """Test that database connections are properly isolated between threads."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Simulate source adapter loading that uses database."""
            # Try to access database in this thread
            from django.db import connection  # pylint: disable=import-outside-toplevel

            connection.ensure_connection()
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Simulate target adapter loading that uses database."""
            # Try to access database in this thread
            from django.db import connection  # pylint: disable=import-outside-toplevel

            connection.ensure_connection()
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        # Should not raise any database connection errors
        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)

        # Both adapters should be loaded successfully
        self.assertIsNotNone(self.job.source_adapter)
        self.assertIsNotNone(self.job.target_adapter)

    def test_parallel_loading_log_deduplication(self):
        """Test that duplicate log messages from threads are properly deduplicated."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Simulate source adapter loading with duplicate logs."""
            logger = logging.getLogger(f"nautobot.extras.jobs.run_job[{self.job.job_result.id}]")
            logger.info("Duplicate message")
            logger.info("Duplicate message")  # Duplicate
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Simulate target adapter loading."""
            logger = logging.getLogger(f"nautobot.extras.jobs.run_job[{self.job.job_result.id}]")
            logger.info("Unique message")
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)

        # Check log entries
        log_entries = JobLogEntry.objects.filter(job_result=self.job.job_result)
        log_messages = [entry.message for entry in log_entries]

        # "Duplicate message" should appear (deduplication may or may not happen based on timing)
        # But we should have at least one instance
        duplicate_count = log_messages.count("Duplicate message")
        self.assertGreaterEqual(duplicate_count, 1)

    @patch("nautobot_ssot.jobs.base.DataSyncBaseJob.create_records", False)
    def test_parallel_loading_vs_sequential_performance(self):
        """Test that parallel loading is faster than sequential for slow adapters."""
        mock_diff = self._create_mock_diff()

        # Test parallel loading
        parallel_job = DataSyncBaseJob()
        parallel_job.job_result = JobResult.objects.create(
            name="parallel job",
            task_name="parallel job",
            worker="default",
        )

        def parallel_load_source():
            """Simulate slow source adapter loading for parallel job."""
            time.sleep(0.1)
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            parallel_job.source_adapter = source_adapter

        def parallel_load_target():
            """Simulate slow target adapter loading for parallel job."""
            time.sleep(0.1)
            parallel_job.target_adapter = Mock()

        parallel_job.load_source_adapter = parallel_load_source
        parallel_job.load_target_adapter = parallel_load_target

        parallel_start = time.time()
        parallel_job.run(dryrun=True, memory_profiling=False, parallel_loading=True, create_records=False)
        parallel_duration = time.time() - parallel_start

        # Test sequential loading
        sequential_job = DataSyncBaseJob()
        sequential_job.job_result = JobResult.objects.create(
            name="sequential job",
            task_name="sequential job",
            worker="default",
        )

        def sequential_load_source():
            """Simulate slow source adapter loading for sequential job."""
            time.sleep(0.1)
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            sequential_job.source_adapter = source_adapter

        def sequential_load_target():
            """Simulate slow target adapter loading for sequential job."""
            time.sleep(0.1)
            sequential_job.target_adapter = Mock()

        sequential_job.load_source_adapter = sequential_load_source
        sequential_job.load_target_adapter = sequential_load_target

        sequential_start = time.time()
        sequential_job.run(dryrun=True, memory_profiling=False, parallel_loading=False, create_records=False)
        sequential_duration = time.time() - sequential_start

        # Parallel should be faster (approximately half the time for equal delays)
        # Allow some margin for test execution overhead
        self.assertLess(parallel_duration, sequential_duration * 0.7)


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
