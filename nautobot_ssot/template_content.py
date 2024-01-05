"""App template content extensions of base Nautobot views."""

from django.urls import reverse

from nautobot.extras.plugins import PluginTemplateExtension

from nautobot_ssot.models import Sync

# pylint: disable=abstract-method


class JobResultSyncLink(PluginTemplateExtension):
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


template_extensions = [JobResultSyncLink]
