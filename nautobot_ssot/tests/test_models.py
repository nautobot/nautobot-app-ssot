"""Model test cases for nautobot_ssot."""

import datetime
import time
import uuid
from django.test import TestCase
from django.utils.timezone import now

from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import Job, JobResult

from nautobot_ssot.models import Sync


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

        self.source_sync.job_result = JobResult(
            name="ExampleDataSource",
            job_model=Job.objects.get(module_name="nautobot_ssot.jobs.examples", job_class_name="ExampleDataSource"),
            task_name="nautobot_ssot.jobs.examples.ExampleDataSource",
            worker="default",
        )
        self.target_sync.job_result = JobResult(
            name="ExampleDataTarget",
            job_model=Job.objects.get(module_name="nautobot_ssot.jobs.examples", job_class_name="ExampleDataTarget"),
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
