"""Model test cases for nautobot_ssot."""

import datetime
import time
import uuid

from django.utils.timezone import now
from nautobot.apps.testing import TestCase
from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import JobResult

from nautobot_ssot.jobs.examples import ExampleDataSource, ExampleDataTarget
from nautobot_ssot.models import Sync
from nautobot_ssot.tests.utils.job_helpers import get_test_job_model


class SyncTestCase(TestCase):
    """Tests for the Sync model."""

    def setUp(self):
        """Per-test setup function."""
        self.source_sync = Sync(
            source="Some other system",
            target="Nautobot",
            dry_run=False,
            start_time=None,
            diff={},
        )
        self.source_sync.validated_save()
        self.target_sync = Sync(
            source="Nautobot",
            target="Another system",
            dry_run=False,
            start_time=None,
            diff={},
        )
        self.target_sync.validated_save()

    def test_duration(self):
        """Test the duration property."""
        # Hasn't started yet, so no applicable duration
        self.assertEqual(self.source_sync.duration, datetime.timedelta())
        self.source_sync.start_time = now()
        time.sleep(1)
        self.assertGreater(self.source_sync.duration, datetime.timedelta())
        self.source_sync.job_result = JobResult(
            name="ExampleDataSource",
            task_name="nautobot_ssot.jobs.examples.ExampleDataSource",
            worker="default",
        )
        # Still running
        time.sleep(1)
        self.assertGreater(self.source_sync.duration, datetime.timedelta(seconds=1))
        # Completed
        self.source_sync.job_result.set_status(JobResultStatusChoices.STATUS_SUCCESS)
        duration = self.source_sync.duration
        time.sleep(1)
        self.assertEqual(duration, self.source_sync.duration)

    def test_get_source_target_url(self):
        """Test the get_source_url() and get_target_url() methods."""
        # No JobResult
        self.assertIsNone(self.source_sync.get_source_url())
        self.assertIsNone(self.target_sync.get_target_url())
        # Source/target is Nautobot
        self.assertIsNone(self.target_sync.get_source_url())
        self.assertIsNone(self.source_sync.get_target_url())

        source_job_model = get_test_job_model(ExampleDataSource)
        target_job_model = get_test_job_model(ExampleDataTarget)
        self.source_sync.job_result = JobResult(
            name="ExampleDataSource",
            job_model=source_job_model,
            task_name="nautobot_ssot.jobs.examples.ExampleDataSource",
            worker="default",
        )
        self.target_sync.job_result = JobResult(
            name="ExampleDataTarget",
            job_model=target_job_model,
            task_name="nautobot_ssot.jobs.examples.ExampleDataTarget",
            worker="default",
        )

        self.assertIsNotNone(self.source_sync.get_source_url())
        self.assertIsNotNone(self.target_sync.get_target_url())
        # Source/target is Nautobot, so still None
        self.assertIsNone(self.target_sync.get_source_url())
        self.assertIsNone(self.source_sync.get_target_url())

    def test_diff_with_datetime(self):
        """Test datetime objects in diff are serializable."""
        earliest_datetime = datetime.datetime(1, 1, 1)
        self.source_sync.diff = {"datetime": earliest_datetime}
        self.source_sync.validated_save()
        self.source_sync.refresh_from_db()
        actual = self.source_sync.diff["datetime"]
        expected = earliest_datetime.isoformat()
        self.assertEqual(actual, expected)

    def test_diff_with_uuid(self):
        """Test UUID objects in diff are serializable."""
        expected = "12345678-1234-5678-1234-567812345678"
        self.source_sync.diff = {"uuid": uuid.UUID(expected)}
        self.source_sync.validated_save()
        self.source_sync.refresh_from_db()
        actual = self.source_sync.diff["uuid"]
        self.assertEqual(actual, expected)

    def test_diff_with_set(self):
        """Test set objects in diff are serialized via the custom encoder."""
        self.source_sync.diff = {"items": {42}}
        self.source_sync.validated_save()
        self.source_sync.refresh_from_db()
        self.assertEqual(self.source_sync.diff["items"], "[42]")

    def test_end_time(self):
        """Test the end_time property."""
        # No JobResult -> no end time
        self.assertIsNone(self.source_sync.end_time)
        job_result = JobResult.objects.create(
            name="ExampleDataSource",
            task_name="nautobot_ssot.jobs.examples.ExampleDataSource",
            worker="default",
        )
        job_result.date_done = now()
        job_result.save()
        self.source_sync.job_result = job_result
        self.assertEqual(self.source_sync.end_time, job_result.date_done)

    def test_get_source_display_plain(self):
        """get_source_display() returns plain text when there is no source URL."""
        # No JobResult -> get_source_url() is None -> plain source string
        self.assertEqual(self.source_sync.get_source_display(), "Some other system")

    def test_get_target_display_plain(self):
        """get_target_display() returns plain text when there is no target URL."""
        # No JobResult -> get_target_url() is None -> plain target string
        self.assertEqual(self.target_sync.get_target_display(), "Another system")

    def test_get_target_display_with_link(self):
        """get_target_display() renders an HTML link when a target URL is available."""
        target_job_model = get_test_job_model(ExampleDataTarget)
        self.target_sync.job_result = JobResult(
            name="ExampleDataTarget",
            job_model=target_job_model,
            task_name="nautobot_ssot.jobs.examples.ExampleDataTarget",
            worker="default",
        )
        result = self.target_sync.get_target_display()
        self.assertIn("<a href", result)
        self.assertIn("Another system", result)
