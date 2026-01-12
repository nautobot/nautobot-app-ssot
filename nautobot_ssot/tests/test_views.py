"""View test cases for nautobot_ssot."""

from datetime import datetime
from unittest import skip

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from nautobot.apps.testing import ViewTestCases
from nautobot.core.testing.utils import disable_warnings
from nautobot.extras.models import Job, JobResult
from nautobot.users.models import ObjectPermission

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.models import Sync, SyncLogEntry
from nautobot_ssot.views import SyncLogEntryUIViewSet


class SyncViewsTestCase(  # pylint: disable=too-many-ancestors
    ViewTestCases.ListObjectsViewTestCase,
    ViewTestCases.GetObjectViewTestCase,
    ViewTestCases.DeleteObjectViewTestCase,
    ViewTestCases.BulkDeleteObjectsViewTestCase,
):
    """Test various views associated with the Sync model."""

    model = Sync

    @classmethod
    def setUpTestData(cls):
        """One-time setup of test data for this class."""
        for i in range(0, 3):
            job_result = JobResult.objects.create(
                name="ExampleDataSource",
                job_model=Job.objects.get(
                    module_name="nautobot_ssot.jobs.examples", job_class_name="ExampleDataSource"
                ),
                task_name="nautobot_ssot.jobs.examples.ExampleDataSource",
                worker="default",
            )
            cls.sync = Sync.objects.create(
                source="Example Data Source",
                target="Nautobot",
                start_time=datetime.now(),
                dry_run=bool(i % 2),
                diff={},
                job_result=job_result,
            )

    def test_dashboard_without_permission(self):
        """Test that the dashboard view enforces permissions correctly."""
        with disable_warnings("django.request"):
            self.assertHttpStatus(self.client.get(reverse("plugins:nautobot_ssot:dashboard")), 403)

    def test_dashboard_with_permission(self):
        """Test the dashboard view."""
        obj_perm = ObjectPermission(name="Test permission", actions=["view"])
        obj_perm.save()
        obj_perm.users.add(self.user)
        obj_perm.object_types.add(ContentType.objects.get_for_model(self.model))

        self.assertHttpStatus(self.client.get(reverse("plugins:nautobot_ssot:dashboard")), 200)

    def test_data_source_target_view_without_permission(self):
        """Test that the DataSourceTargetView enforces permissions correctly."""
        with disable_warnings("django.request"):
            self.assertHttpStatus(
                self.client.get(
                    reverse(
                        "plugins:nautobot_ssot:data_source",
                        kwargs={"class_path": "plugins/nautobot_ssot.jobs.examples/ExampleDataSource"},
                    )
                ),
                403,
            )

        # Just access to Sync isn't sufficient - also need view_job permissions
        obj_perm = ObjectPermission(name="Test permission", actions=["view"])
        obj_perm.save()
        obj_perm.users.add(self.user)
        obj_perm.object_types.add(ContentType.objects.get_for_model(self.model))

        with disable_warnings("django.request"):
            self.assertHttpStatus(
                self.client.get(
                    reverse(
                        "plugins:nautobot_ssot:data_source",
                        kwargs={"class_path": "nautobot_ssot.jobs.examples.ExampleDataSource"},
                    )
                ),
                403,
            )

    def test_data_source_target_view_with_permission(self):
        """Test the DataSourceTargetView."""
        obj_perm = ObjectPermission(name="Test permission", actions=["view"])
        obj_perm.save()
        obj_perm.users.add(self.user)
        obj_perm.object_types.add(ContentType.objects.get_for_model(self.model))
        obj_perm.object_types.add(ContentType.objects.get_for_model(Job))
        self.assertHttpStatus(
            self.client.get(
                reverse(
                    "plugins:nautobot_ssot:data_source",
                    kwargs={"class_path": "nautobot_ssot.jobs.examples.ExampleDataSource"},
                )
            ),
            200,
        )

    @override_settings(EXEMPT_VIEW_PERMISSIONS=["*"])
    def test_sync_diff_tab(self):
        self.add_permissions("nautobot_ssot.view_sync")

        url = reverse("plugins:nautobot_ssot:sync_diff", kwargs={"pk": self.sync.pk})
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    @override_settings(EXEMPT_VIEW_PERMISSIONS=["*"])
    def test_sync_logentries_tab(self):
        self.add_permissions("nautobot_ssot.view_synclogentry")

        url = reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": self.sync.pk})
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    @override_settings(EXEMPT_VIEW_PERMISSIONS=["*"])
    def test_sync_jobresult_tab(self):
        self.add_permissions("extras.view_jobresult")

        url = reverse("plugins:nautobot_ssot:sync_jobresult", kwargs={"pk": self.sync.pk})
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)


class SyncLogEntryViewsTestCase(ViewTestCases.ListObjectsViewTestCase):  # pylint: disable=too-many-ancestors
    """Test views related to the SyncLogEntry model."""

    model = SyncLogEntry

    @classmethod
    def setUpTestData(cls):
        """One-time setup of test data for this class."""
        job_result = JobResult.objects.create(
            name="ExampleDataSource",
            task_name="nautobot_ssot.jobs.examples.ExampleDataSource",
            worker="default",
        )
        sync = Sync.objects.create(
            source="Example Data Source",
            target="Nautobot",
            start_time=datetime.now(),
            dry_run=False,
            diff={"foo": "bar"},
            job_result=job_result,
        )

        for i in range(0, 3):
            SyncLogEntry.objects.create(
                sync=sync,
                action=SyncLogEntryActionChoices.ACTION_NO_CHANGE,
                status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
                diff={"+": {"i": i}},
                synced_object=None,
                object_repr="Placeholder",
                message="Log message",
            )

    # This test is skipped because their is no object detail view for the SyncLogEntry model to get a url for.
    @skip("Not implemented")
    def test_list_objects_with_constrained_permission(self):
        pass

    def test_queryset_optimization(self):
        """Test that the SyncLogEntry queryset uses select_related and only() correctly."""
        # Get the queryset from the viewset
        queryset = SyncLogEntryUIViewSet.queryset

        # Evaluate the queryset to get all log entries
        # This should trigger a single query with select_related
        with CaptureQueriesContext(connection) as ctx:
            log_entries = list(queryset.all())

        # Should have exactly 1 query (the main query with select_related)
        self.assertEqual(len(ctx.captured_queries), 1, "Queryset should use select_related to fetch in one query")

        # Verify we have log entries
        self.assertGreater(len(log_entries), 0)

        # Test that accessing sync-related fields doesn't trigger additional queries
        with CaptureQueriesContext(connection) as ctx:
            for entry in log_entries:
                # Access all the sync fields that are specified in the only() clause
                _ = entry.sync.id
                _ = entry.sync.source
                _ = entry.sync.target
                _ = entry.sync.start_time
                # Also test accessing the sync object itself (for __str__)
                _ = str(entry.sync)

        # Should have 0 additional queries since select_related was used
        self.assertEqual(len(ctx.captured_queries), 0, "Accessing sync fields should not trigger additional queries")

        # Verify that sync.diff was NOT loaded (it's not in the only() clause)
        # Accessing it should trigger an additional query
        with CaptureQueriesContext(connection) as ctx:
            _ = log_entries[0].sync.diff

        # Should have 1 additional query to fetch the deferred diff field
        self.assertEqual(
            len(ctx.captured_queries),
            1,
            "Accessing sync.diff should trigger an additional query since it wasn't loaded in the original queryset",
        )
