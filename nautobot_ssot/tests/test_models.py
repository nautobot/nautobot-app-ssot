"""Model test cases for nautobot_ssot."""

from datetime import timedelta
import time
import uuid

from django.contrib.contenttypes.models import ContentType
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
        self.assertEqual(self.source_sync.duration, timedelta())
        self.source_sync.start_time = now()
        time.sleep(1)
        self.assertGreater(self.source_sync.duration, timedelta())
        self.source_sync.job_result = JobResult(
            name="/plugins/nautobot_ssot.jobs.examples/ExampleDataSource",
            obj_type=ContentType.objects.get_for_model(Job),
            job_id=uuid.uuid4(),
        )
        # Still running
        time.sleep(1)
        self.assertGreater(self.source_sync.duration, timedelta(seconds=1))
        # Completed
        self.source_sync.job_result.set_status(JobResultStatusChoices.STATUS_COMPLETED)
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
            name="/plugins/nautobot_ssot.jobs.examples/ExampleDataSource",
            obj_type=ContentType.objects.get_for_model(Job),
            job_id=uuid.uuid4(),
        )
        self.target_sync.job_result = JobResult(
            name="/plugins/nautobot_ssot.jobs.examples/ExampleDataTarget",
            obj_type=ContentType.objects.get_for_model(Job),
            job_id=uuid.uuid4(),
        )

        self.assertIsNotNone(self.source_sync.get_source_url())
        self.assertIsNotNone(self.target_sync.get_target_url())
        # Source/target is Nautobot, so still None
        self.assertIsNone(self.target_sync.get_source_url())
        self.assertIsNone(self.source_sync.get_target_url())
