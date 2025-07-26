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
    """SSOTOpenshiftConfig UI ViewSet."""
    
    queryset = SSOTOpenshiftConfig.objects.all()
    table_class = SSOTOpenshiftConfigTable
    filterset_class = SSOTOpenshiftConfigFilterSet
    filterset_form_class = SSOTOpenshiftConfigFilterForm
    form_class = SSOTOpenshiftConfigForm
    serializer_class = SSOTOpenshiftConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)
    
    def get_template_name(self):
        """Override inherited method to allow custom location for templates."""
        action = self.action
        app_label = "nautobot_ssot_openshift"
        model_opts = self.queryset.model._meta
        if action in ["create", "update"]:
            template_name = f"{app_label}/{model_opts.model_name}_update.html"
        elif action == "retrieve":
            template_name = f"{app_label}/{model_opts.model_name}_retrieve.html"
        elif action == "list":
            template_name = f"{app_label}/{model_opts.model_name}_list.html"
        else:
            template_name = super().get_template_name()

        return template_name


class SSOTOpenshiftConfigChangeLogView(ObjectChangeLogView):
    """SSOTOpenshiftConfig ChangeLog View."""
    
    base_template = "nautobot_ssot_openshift/ssotopenshiftconfig_retrieve.html"


class SSOTOpenshiftConfigNotesView(ObjectNotesView):
    """SSOTOpenshiftConfig Notes View."""
    
    base_template = "nautobot_ssot_openshift/ssotopenshiftconfig_retrieve.html"
