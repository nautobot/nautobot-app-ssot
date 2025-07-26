"""Views for OpenShift integration."""
from nautobot.apps.views import (
    ObjectChangeLogViewMixin,
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectEditViewMixin,
    ObjectListViewMixin,
    ObjectNotesViewMixin,
)
from nautobot.extras.views import ObjectChangeLogView, ObjectNotesView

from .api.serializers import SSOTOpenshiftConfigSerializer
from .filters import SSOTOpenshiftConfigFilterSet
from .forms import SSOTOpenshiftConfigFilterForm, SSOTOpenshiftConfigForm
from .models import SSOTOpenshiftConfig
from .tables import SSOTOpenshiftConfigTable


class SSOTOpenshiftConfigUIViewSet(
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectEditViewMixin,
    ObjectChangeLogViewMixin,
    ObjectNotesViewMixin,
):
    """ViewSet for SSOTOpenshiftConfig model."""
    
    model = SSOTOpenshiftConfig
    filterset_class = SSOTOpenshiftConfigFilterSet
    filterset_form_class = SSOTOpenshiftConfigFilterForm
    form_class = SSOTOpenshiftConfigForm
    serializer_class = SSOTOpenshiftConfigSerializer
    table_class = SSOTOpenshiftConfigTable
    
    lookup_field = "pk"
    
    def get_extra_context(self, request, instance=None):
        """Add extra context."""
        context = super().get_extra_context(request, instance)
        if instance:
            context["sync_jobs_url"] = "/plugins/nautobot-ssot/jobs/"
        return context


# For explicit URL registration
class SSOTOpenshiftConfigListView(SSOTOpenshiftConfigUIViewSet):
    """List view."""
    pass


class SSOTOpenshiftConfigView(SSOTOpenshiftConfigUIViewSet):
    """Detail view."""
    pass


class SSOTOpenshiftConfigEditView(SSOTOpenshiftConfigUIViewSet):
    """Edit view."""
    pass


class SSOTOpenshiftConfigDeleteView(SSOTOpenshiftConfigUIViewSet):
    """Delete view."""
    pass


class SSOTOpenshiftConfigBulkDeleteView(SSOTOpenshiftConfigUIViewSet):
    """Bulk delete view."""
    pass


class SSOTOpenshiftConfigChangeLogView(ObjectChangeLogView):
    """Change log view."""
    base_template = "nautobot_ssot/openshift/config.html"


class SSOTOpenshiftConfigNotesView(ObjectNotesView):
    """Notes view."""
    base_template = "nautobot_ssot/openshift/config.html"
