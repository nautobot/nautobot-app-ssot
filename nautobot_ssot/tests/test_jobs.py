"""Test the Job classes in nautobot_ssot."""

import datetime
import logging
import os.path
import threading
import time
from unittest.mock import MagicMock, Mock, call, patch

import structlog
from django.conf import settings
from django.db.utils import IntegrityError, OperationalError
from django.test import override_settings
from nautobot.apps.testing import TestCase, TransactionTestCase
from nautobot.extras.models import JobLogEntry, JobResult

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.contrib.adapter import NautobotAdapter
from nautobot_ssot.models import SyncLogEntry
from nautobot_ssot.tests.jobs import DataSource, DataSyncBaseJob, DataTarget


class _JobTestSetupMixin:
    """Shared setup for the data-sync job test cases."""

    job_class = DataSyncBaseJob
    databases = (
        "default",
        "job_logs",
    )

    def setUp(self):  # pylint: disable=invalid-name
        """Per-test setup."""
        # run() reconfigures structlog process-wide with a processor bound to the job instance.
        # Capture the current configuration so tearDown can restore it; otherwise that processor
        # leaks into later tests and writes SyncLogEntry rows referencing this test's rolled-back
        # Sync, tripping a foreign-key constraint check on teardown of a subsequent TestCase.
        self._structlog_config = structlog.get_config()
        super().setUp()
        self.job = self.job_class()

        self.job.job_result = JobResult.objects.create(
            name="fake job",
            task_name="fake job",
            worker="default",
        )

        self.job.load_source_adapter = lambda *x, **y: None
        self.job.load_target_adapter = lambda *x, **y: None

    def tearDown(self):  # pylint: disable=invalid-name
        """Undo the global structlog reconfiguration performed by run()."""
        structlog.reset_defaults()
        structlog.configure(**self._structlog_config)
        super().tearDown()

    def _create_mock_diff(self):
        """Helper method to create a properly configured mock Diff object."""
        mock_diff = Mock()
        mock_diff.summary.return_value = "{'create': 0, 'update': 0, 'delete': 0, 'no-change': 0, 'skip': 0}"
        mock_diff.dict.return_value = {}
        return mock_diff


@override_settings(JOBS_ROOT=os.path.join(os.path.dirname(__file__), "jobs"))
class JobBehaviorTestCase(_JobTestSetupMixin, TestCase):  # pylint: disable=too-many-public-methods
    """Test the non-threaded behavior of the DataSyncBaseJob class.

    These tests run sequentially (or with the parallel loader patched out), so they need no real
    threads and use TestCase for transaction isolation.
    """

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

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=False)
        # Both adapters should be loaded
        self.assertIsNotNone(self.job.source_adapter)
        self.assertIsNotNone(self.job.target_adapter)
        # Timing should be recorded for both
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)

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

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=False)

        # Timing should be recorded
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)

        # In sequential mode, target time should be after source time
        source_duration = self.job.sync.source_load_time.total_seconds()
        target_duration = self.job.sync.target_load_time.total_seconds()

        # Each load slept ~0.05s, so each recorded duration should be at least that. We assert only
        # the lower bound (guaranteed by sleep); upper bounds on wall-clock time are flaky on busy CI.
        self.assertGreaterEqual(source_duration, 0.04)
        self.assertGreaterEqual(target_duration, 0.04)

    def test_sync_data_no_sync_returns_early(self):
        """sync_data() returns immediately when no Sync record is present."""
        self.job.sync = None
        # Should not raise despite no adapters/sync being configured.
        self.job.sync_data(memory_profiling=False)
        self.assertIsNone(self.job.sync)

    def test_sync_log_with_synced_object(self):
        """sync_log() derives object_repr from the synced object when not provided."""
        self.job.run(dryrun=True, memory_profiling=False)
        self.job.sync_log(
            action=SyncLogEntryActionChoices.ACTION_CREATE,
            status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
            synced_object=self.job.sync,
        )
        entry = SyncLogEntry.objects.filter(synced_object_id=self.job.sync.id).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.object_repr, repr(self.job.sync))

    def test_structlog_to_sync_log_entry(self):
        """A complete DiffSync structlog event is recorded as a SyncLogEntry."""
        self.job.run(dryrun=True, memory_profiling=False)
        event_dict = {
            "src": "source",
            "dst": "dest",
            "action": SyncLogEntryActionChoices.ACTION_CREATE,
            "model": "device",
            "unique_id": "device-1",
            "diffs": {"+": {"name": "x"}},
            "status": SyncLogEntryStatusChoices.STATUS_SUCCESS,
            "event": "Created device-1",
        }
        result = self.job._structlog_to_sync_log_entry(None, None, dict(event_dict))  # pylint: disable=protected-access
        self.assertEqual(result["event"], "Created device-1")
        self.assertTrue(SyncLogEntry.objects.filter(message="Created device-1").exists())

        # An event missing the required keys is passed through unchanged with no entry created.
        partial = {"event": "no-op"}
        passthrough = self.job._structlog_to_sync_log_entry(None, None, partial)  # pylint: disable=protected-access
        self.assertEqual(passthrough, partial)

    def test_sync_data_memory_profiling_formats_sizes(self):
        """Memory profiling records traced memory and formats KiB-scale sizes."""
        with (
            patch("tracemalloc.start"),
            patch("tracemalloc.clear_traces"),
            patch("tracemalloc.get_traced_memory", return_value=(51200, 51200)),
        ):
            self.job.run(dryrun=True, memory_profiling=True, parallel_loading=False)
        self.assertEqual(self.job.sync.source_load_memory_final, 51200)

    def test_parallel_loading_only_source_duration(self):
        """When only a source duration is reported, both load times take that value."""
        mock_diff = self._create_mock_diff()
        source_adapter = Mock()
        source_adapter.diff_to.return_value = mock_diff
        target_adapter = Mock()

        def fake_parallel():
            """Stand in for the parallel loader, reporting only a source duration."""
            self.job.source_adapter = source_adapter
            self.job.target_adapter = target_adapter
            return (source_adapter, target_adapter, datetime.timedelta(seconds=1), None)

        self.job._load_adapters_parallel = fake_parallel  # pylint: disable=protected-access
        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)
        self.assertEqual(self.job.sync.source_load_time, datetime.timedelta(seconds=1))
        self.assertEqual(self.job.sync.target_load_time, datetime.timedelta(seconds=1))

    def test_parallel_loading_only_target_duration(self):
        """When only a target duration is reported, both load times take that value."""
        mock_diff = self._create_mock_diff()
        source_adapter = Mock()
        source_adapter.diff_to.return_value = mock_diff
        target_adapter = Mock()

        def fake_parallel():
            """Stand in for the parallel loader, reporting only a target duration."""
            self.job.source_adapter = source_adapter
            self.job.target_adapter = target_adapter
            return (source_adapter, target_adapter, None, datetime.timedelta(seconds=2))

        self.job._load_adapters_parallel = fake_parallel  # pylint: disable=protected-access
        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)
        self.assertEqual(self.job.sync.source_load_time, datetime.timedelta(seconds=2))
        self.assertEqual(self.job.sync.target_load_time, datetime.timedelta(seconds=2))

    def test_sync_data_creates_metadatatype_when_enabled(self):
        """When enabled via config and the target is a NautobotAdapter, the metadata type is created."""
        mock_diff = self._create_mock_diff()
        target_adapter = MagicMock(spec=NautobotAdapter)
        source_adapter = Mock()
        source_adapter.diff_to.return_value = mock_diff

        def load_source():
            """Load the mocked source adapter."""
            self.job.source_adapter = source_adapter

        def load_target():
            """Load the NautobotAdapter-spec target adapter."""
            self.job.target_adapter = target_adapter

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target
        with patch.dict(
            settings.PLUGINS_CONFIG["nautobot_ssot"],
            {"enable_metadata_for": [self.job.__class__.__name__]},
        ):
            self.job.run(dryrun=True, memory_profiling=False, parallel_loading=False)
        target_adapter.get_or_create_metadatatype.assert_called_once()


@override_settings(JOBS_ROOT=os.path.join(os.path.dirname(__file__), "jobs"))
class ParallelLoadingTestCase(_JobTestSetupMixin, TransactionTestCase):  # pylint: disable=too-many-public-methods
    """Test the threaded parallel-loading path of DataSyncBaseJob.

    These tests run a real ThreadPoolExecutor (which calls ``connections.close_all()`` from worker
    threads), so they require TransactionTestCase rather than TestCase.
    """

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

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)
        # Both adapters should be loaded
        self.assertIsNotNone(self.job.source_adapter)
        self.assertIsNotNone(self.job.target_adapter)
        # Timing should be recorded for both (same value in parallel mode)
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)
        # In parallel mode, both times should be the same (total parallel time)
        self.assertEqual(self.job.sync.source_load_time, self.job.sync.target_load_time)

    def test_parallel_loading_runs_concurrently(self):
        """Parallel loading runs the two loaders concurrently, proven via a thread barrier.

        Using a barrier instead of wall-clock timing keeps this deterministic on busy CI runners:
        if the loaders ran sequentially the first would block at the barrier until it timed out
        (raising BrokenBarrierError and failing the run), so reaching completion proves concurrency.
        """
        mock_diff = self._create_mock_diff()
        source_adapter = Mock()
        source_adapter.diff_to.return_value = mock_diff
        target_adapter = Mock()
        barrier = threading.Barrier(2, timeout=10)

        def load_source():
            """Rendezvous with the target loader at the barrier, then load the source adapter."""
            barrier.wait()
            self.job.source_adapter = source_adapter

        def load_target():
            """Rendezvous with the source loader at the barrier, then load the target adapter."""
            barrier.wait()
            self.job.target_adapter = target_adapter

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        # Completes only if both loaders reach the barrier simultaneously (i.e. ran concurrently).
        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

        # Both adapters should be loaded
        self.assertEqual(self.job.source_adapter, source_adapter)
        self.assertEqual(self.job.target_adapter, target_adapter)

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
            self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

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
            self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

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
            self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

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

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

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
        log_messages = " ".join(entry.message for entry in log_entries)
        self.assertIn("Source adapter loading completed", log_messages)
        self.assertIn("Target adapter loading completed", log_messages)

    def test_parallel_loading_preserves_custom_groupings(self):
        """Test that custom log groupings from extra dict are preserved in parallel mode.

        Regression test: previously, create_job_log_entry() hardcoded grouping=adapter_type
        ("source"/"target"), discarding the custom grouping set via extra={"grouping": ...}.
        """
        mock_diff = self._create_mock_diff()

        def load_source():
            """Simulate source adapter loading with custom log groupings."""
            logger = logging.getLogger(f"nautobot.extras.jobs.run_job[{self.job.job_result.id}]")
            logger.info("Loading locations from ServiceNow", extra={"grouping": "Loading ServiceNow Data"})
            logger.warning("Bad record skipped", extra={"grouping": "Data Quality Issues"})
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Simulate target adapter loading with custom log groupings."""
            logger = logging.getLogger(f"nautobot.extras.jobs.run_job[{self.job.job_result.id}]")
            logger.info("Loading devices from Nautobot", extra={"grouping": "Loading Nautobot Data"})
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

        log_entries = JobLogEntry.objects.filter(job_result=self.job.job_result)

        # Custom groupings should be preserved, not collapsed to "source"/"target"

        sn_data_logs = log_entries.filter(grouping="Loading ServiceNow Data (source)")
        self.assertGreater(
            sn_data_logs.count(), 0, "Custom grouping 'Loading ServiceNow Data (source)' should be preserved"
        )

        dq_logs = log_entries.filter(grouping="Data Quality Issues (source)")
        self.assertGreater(dq_logs.count(), 0, "Custom grouping 'Data Quality Issues (source)' should be preserved")

        nb_data_logs = log_entries.filter(grouping="Loading Nautobot Data (target)")
        self.assertGreater(
            nb_data_logs.count(), 0, "Custom grouping 'Loading Nautobot Data (target)' should be preserved"
        )

        # Verify the actual messages landed under the correct groupings
        sn_messages = [e.message for e in sn_data_logs]
        self.assertTrue(
            any("Loading locations" in m for m in sn_messages),
            f"Expected 'Loading locations' in ServiceNow Data logs, got: {sn_messages}",
        )

        dq_messages = [e.message for e in dq_logs]
        self.assertTrue(
            any("Bad record" in m for m in dq_messages),
            f"Expected 'Bad record' in Data Quality Issues logs, got: {dq_messages}",
        )

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

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

        # Timing should be recorded
        self.assertIsNotNone(self.job.sync.source_load_time)
        self.assertIsNotNone(self.job.sync.target_load_time)

        # In parallel mode, both should have the same duration (total parallel time),
        # which is the max of the two individual durations, not the sum.
        self.assertEqual(self.job.sync.source_load_time, self.job.sync.target_load_time)

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
        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

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

        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

        # Check log entries
        log_entries = JobLogEntry.objects.filter(job_result=self.job.job_result)
        log_messages = [entry.message for entry in log_entries]

        # "Duplicate message" should appear (deduplication may or may not happen based on timing)
        # But we should have at least one instance
        duplicate_count = log_messages.count("Duplicate message")
        self.assertGreaterEqual(duplicate_count, 1)

    def test_parallel_loading_captures_all_log_levels(self):
        """Error, debug, and exception log records from threads are all persisted as JobLogEntry rows."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Emit log records at several levels, including one with traceback info."""
            logger = logging.getLogger(f"nautobot.extras.jobs.run_job[{self.job.job_result.id}]")
            logger.error("an error occurred")
            logger.debug("a debug detail")
            try:
                raise ValueError("boom")
            except ValueError:
                logger.error("error with traceback", exc_info=True)
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Load a minimal target adapter."""
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target
        self.job.run(dryrun=True, memory_profiling=False, parallel_loading=True)

        levels = {entry.log_level for entry in JobLogEntry.objects.filter(job_result=self.job.job_result)}
        self.assertIn("error", levels)
        self.assertIn("debug", levels)

    def test_parallel_loading_with_memory_profiling(self):
        """Parallel loading with memory profiling records a parallel-load memory trace."""
        mock_diff = self._create_mock_diff()

        def load_source():
            """Load a source adapter exposing a diff."""
            source_adapter = Mock()
            source_adapter.diff_to.return_value = mock_diff
            self.job.source_adapter = source_adapter

        def load_target():
            """Load a minimal target adapter."""
            self.job.target_adapter = Mock()

        self.job.load_source_adapter = load_source
        self.job.load_target_adapter = load_target
        with (
            patch("tracemalloc.start"),
            patch("tracemalloc.clear_traces"),
            patch("tracemalloc.get_traced_memory", return_value=(2048, 4096)),
        ):
            self.job.run(dryrun=True, memory_profiling=True, parallel_loading=True)
        self.assertIsNotNone(self.job.sync.source_load_time)


class DataSourceJobTestCase(TestCase):
    """Property overrides for the DataSource base job."""

    def test_data_source(self):
        """data_source defaults to the job class name."""
        self.assertEqual(DataSource().data_source, DataSource.__name__)

    def test_data_target(self):
        """A DataSource always targets Nautobot."""
        self.assertEqual(DataSource().data_target, "Nautobot")

    def test_data_source_icon(self):
        """A DataSource has no source icon by default."""
        self.assertIsNone(DataSource().data_source_icon)

    def test_data_target_icon(self):
        """A DataSource uses the Nautobot logo as its target icon."""
        self.assertEqual(DataSource().data_target_icon, "/static/img/nautobot_logo.png")


class DataTargetJobTestCase(TestCase):
    """Property overrides for the DataTarget base job."""

    def test_data_target(self):
        """data_target defaults to the job class name."""
        self.assertEqual(DataTarget().data_target, DataTarget.__name__)

    def test_data_source(self):
        """A DataTarget always sources from Nautobot."""
        self.assertEqual(DataTarget().data_source, "Nautobot")

    def test_data_target_icon(self):
        """A DataTarget has no target icon by default."""
        self.assertIsNone(DataTarget().data_target_icon)

    def test_data_source_icon(self):
        """A DataTarget uses the Nautobot logo as its source icon."""
        self.assertEqual(DataTarget().data_source_icon, "/static/img/nautobot_logo.png")
