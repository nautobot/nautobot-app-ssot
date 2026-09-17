"""Tests for the JobResultSyncLink template extension."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from nautobot.apps.testing import TestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.models import Sync
from nautobot_ssot.template_content import JobResultSyncLink


def create_sync(job_result, **overrides):
    """Create a Sync attached to the given JobResult."""
    fields = {
        "source": "Example Data Source",
        "target": "Nautobot",
        "start_time": timezone.now(),
        "dry_run": False,
        "diff": {},
    }
    fields.update(overrides)
    return Sync.objects.create(job_result=job_result, **fields)


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
        sync = create_sync(job_result)
        extension = JobResultSyncLink({"object": job_result})
        result = extension.buttons()
        self.assertIn("SSoT Sync Details", result)
        self.assertIn(str(sync.pk), result)

    def test_buttons_with_multiple_syncs_renders_link(self):
        """A JobResult that ended up with more than one Sync still renders a single button (see #950)."""
        job_result = JobResult.objects.create(name="MultiSync", task_name="multisync", worker="default")
        create_sync(job_result)
        create_sync(job_result)
        extension = JobResultSyncLink({"object": job_result})
        result = extension.buttons()
        self.assertEqual(result.count("SSoT Sync Details"), 1)

    def test_buttons_query_fetches_only_pk(self):
        """The Sync lookup selects only the primary key, in a single query.

        The `diff` and `summary` JSON columns can be hundreds of megabytes; selecting them alongside the ORDER BY
        that `.first()` adds overflowed MySQL's sort buffer on the JobResult detail view.
        """
        job_result = JobResult.objects.create(name="WithSync", task_name="withsync", worker="default")
        create_sync(job_result, diff={"large": "payload"}, summary={"create": 1})
        extension = JobResultSyncLink({"object": job_result})
        with CaptureQueriesContext(connection) as queries:
            extension.buttons()
        self.assertEqual(len(queries.captured_queries), 1)
        sql = queries.captured_queries[0]["sql"]
        self.assertIn("nautobot_ssot_sync", sql)
        self.assertNotIn("diff", sql)
        self.assertNotIn("summary", sql)
