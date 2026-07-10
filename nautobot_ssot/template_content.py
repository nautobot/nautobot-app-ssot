"""App template content extensions of base Nautobot views."""

from django.urls import NoReverseMatch, reverse
from nautobot.extras.plugins import TemplateExtension

from nautobot_ssot.models import Sync

# pylint: disable=abstract-method


def _sync_detail_url(pk):
    """Resolve SSoT sync detail URL; Nautobot uses base_url ('ssot') as URL namespace."""
    for namespace in ("ssot", "nautobot_ssot"):
        try:
            return reverse(f"plugins:{namespace}:sync", kwargs={"pk": pk})
        except NoReverseMatch:
            continue
    return None


class JobResultSyncLink(TemplateExtension):
    """Add button linking to Sync data for relevant JobResults."""

    model = "extras.jobresult"

    def buttons(self):
        """Inject a custom button into the JobResult detail view, if applicable."""
        sync_objects = Sync.objects.filter(job_result=self.context["object"])
        if not sync_objects.exists():
            return ""
        url = _sync_detail_url(sync_objects.first().pk)
        if not url:
            return ""
        return f"""
            <div class="btn-group">
                <a href="{url}" class="btn btn-primary">
                    <span class="mdi mdi-database-sync-outline"></span> SSoT Sync Details
                </a>
            </div>
        """


template_extensions = [JobResultSyncLink]
