"""Tests for the JobResultSyncLink template extension."""

from nautobot.apps.testing import TestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.template_content import JobResultSyncLink
from nautobot_ssot.tests.utils.job_helpers import create_example_sync


class TestJobResultSyncLink(TestCase):
    """Tests for the JobResultSyncLink template extension buttons()."""

    def test_buttons_without_sync_returns_empty(self):
        """A JobResult with no associated Sync renders no button."""
        job_result = JobResult.objects.create(name="NoSync", task_name="nosync", worker="default")
        extension = JobResultSyncLink({"object": job_result})
        self.assertEqual(extension.buttons(), "")

    def test_buttons_with_sync_renders_link(self):
        """A JobResult with an associated Sync renders a link to the Sync detail view."""
        job_result = JobResult.objects.create(name="WithSync", task_name="withsync", worker="default")
        sync = create_example_sync(job_result=job_result)
        extension = JobResultSyncLink({"object": job_result})
        result = extension.buttons()
        self.assertIn("SSoT Sync Details", result)
        self.assertIn(str(sync.pk), result)
