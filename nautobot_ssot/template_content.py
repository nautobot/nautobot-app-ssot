"""App template content extensions of base Nautobot views."""

from django.urls import reverse
from nautobot.apps.ui import Button, TemplateExtension
from nautobot.core.views.utils import get_obj_from_context
from nautobot.extras.models import Job

from nautobot_ssot.models import Sync

# pylint: disable=abstract-method


class JobResultSyncLink(TemplateExtension):
    """Add button linking to Sync data for relevant JobResults."""

    model = "extras.jobresult"

    def buttons(self):
        """Inject a custom button into the JobResult detail view, if applicable."""
        try:
            sync = Sync.objects.get(job_result=self.context["object"])
            return f"""
                <div class="btn-group">
                    <a href="{reverse('plugins:nautobot_ssot:sync', kwargs={'pk': sync.pk})}" class="btn btn-primary">
                        <span class="mdi mdi-database-sync-outline"></span> SSoT Sync Details
                    </a>
                </div>
            """
        except Sync.DoesNotExist:
            return ""


class ProcessRecordButton(Button):  # pylint: disable=abstract-method
    """Button for processing a Sync Record."""

    def __init__(self, *args, **kwargs):
        """Initialize the Process Record button."""
        super().__init__(label="Process Record", icon="mdi-import", color="info", weight=100, *args, **kwargs)

    def get_link(self, context):
        """Generate the URL to run Job with Sync Record pre-selected."""
        record = get_obj_from_context(context)
        job = Job.objects.get(name="Process Sync Records")
        # _job_result = JobResult.enqueue_job(job, context["request"].user, records=[record.id])
        # Generate a URL for Process Sync Records Job with the record ID as a parameter
        return f"/extras/jobs/{job.id}/run/?records={record.id}"

    def should_render(self, context):
        """Only render if the user has permissions to change SyncRecords."""
        user = context["request"].user
        # Check if user has permission to add a layout
        return user.has_perm("nautobot_ssot.change_syncrecord")


class SyncRecordsJobButton(TemplateExtension):  # pylint: disable=abstract-method
    """Class to modify FailedSSoT list view."""

    model = "nautobot_ssot.syncrecord"

    object_detail_buttons = [ProcessRecordButton()]


template_extensions = [JobResultSyncLink, SyncRecordsJobButton]
