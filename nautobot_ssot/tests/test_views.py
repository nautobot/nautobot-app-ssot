"""View test cases for nautobot_ssot."""

from datetime import datetime
from unittest import skip

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from nautobot.extras.models import Job, JobResult
from nautobot.users.models import ObjectPermission
from nautobot.apps.testing import ViewTestCases
from nautobot.core.testing.utils import disable_warnings

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.models import Sync, SyncLogEntry


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
            Sync.objects.create(
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

    def test_has_advanced_tab(self):
        pass

    @skip("Not implemented")
    def test_list_objects_with_permission(self):
        pass


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
            diff={},
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

    def test_has_advanced_tab(self):
        pass

    @skip("Not implemented")
    def test_list_objects_with_permission(self):
        pass

    @skip("Not implemented")
    def test_list_objects_anonymous(self):
        pass

    @skip("Not implemented")
    def test_list_objects_filtered(self):
        pass

    @skip("Not implemented")
    def test_list_objects_with_constrained_permission(self):
        pass

    @skip("Not implemented")
    def test_list_objects_unknown_filter_no_strict_filtering(self):
        pass
