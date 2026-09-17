"""App template content extensions of base Nautobot views."""

from django.urls import reverse
from nautobot.extras.plugins import TemplateExtension

from nautobot_ssot.models import Sync

# pylint: disable=abstract-method


class JobResultSyncLink(TemplateExtension):
    """Add button linking to Sync data for relevant JobResults."""

    model = "extras.jobresult"

    def buttons(self):
        """Inject a custom button into the JobResult detail view, if applicable."""
        # Fetch only the pk; the full Sync row includes the `diff` JSON, which can be hundreds of MB.
        sync_pk = Sync.objects.filter(job_result=self.context["object"]).values_list("pk", flat=True).first()
        if sync_pk is None:
            return ""
        return f"""
            <div class="btn-group">
                <a href="{reverse('plugins:nautobot_ssot:sync', kwargs={'pk': sync_pk})}" class="btn btn-primary">
                    <span class="mdi mdi-database-sync-outline"></span> SSoT Sync Details
                </a>
            </div>
        """


template_extensions = [JobResultSyncLink]
