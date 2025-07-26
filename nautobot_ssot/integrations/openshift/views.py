"""Views for OpenShift integration."""
from django.urls import reverse
from nautobot.core.views import generic
from nautobot_ssot.integrations.openshift import filters, forms, models, tables


class SSOTOpenshiftConfigListView(generic.ObjectListView):
    """List view for SSOTOpenshiftConfig."""
    
    queryset = models.SSOTOpenshiftConfig.objects.all()
    table = tables.SSOTOpenshiftConfigTable
    filterset = filters.SSOTOpenshiftConfigFilterSet
    filterset_form = forms.SSOTOpenshiftConfigFilterForm


class SSOTOpenshiftConfigView(generic.ObjectView):
    """Detail view for SSOTOpenshiftConfig."""
    
    queryset = models.SSOTOpenshiftConfig.objects.all()
    
    def get_extra_context(self, request, instance):
        """Add extra context."""
        return {
            "sync_jobs_url": reverse("plugins:nautobot_ssot:job_list"),
        }


class SSOTOpenshiftConfigEditView(generic.ObjectEditView):
    """Edit view for SSOTOpenshiftConfig."""
    
    queryset = models.SSOTOpenshiftConfig.objects.all()
    model_form = forms.SSOTOpenshiftConfigForm


class SSOTOpenshiftConfigDeleteView(generic.ObjectDeleteView):
    """Delete view for SSOTOpenshiftConfig."""
    
    queryset = models.SSOTOpenshiftConfig.objects.all()


class SSOTOpenshiftConfigBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete view for SSOTOpenshiftConfig."""
    
    queryset = models.SSOTOpenshiftConfig.objects.all()
    table = tables.SSOTOpenshiftConfigTable
