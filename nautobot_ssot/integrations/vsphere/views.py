"""Views implementation for SSOT vSphere."""

# pylint: disable=duplicate-code
from nautobot.apps.views import (
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectEditViewMixin,
    ObjectListViewMixin,
)
from nautobot.extras.views import ObjectChangeLogView, ObjectNotesView

from .api.serializers import SSOTvSphereConfigSerializer
from .filters import SSOTvSphereConfigFilterSet
from .forms import SSOTvSphereConfigFilterForm, SSOTvSphereConfigForm
from .models import SSOTvSphereConfig
from .tables import SSOTvSphereConfigTable


class SSOTvSphereConfigUIViewSet(
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectEditViewMixin,
):  # pylint: disable=abstract-method
    """SSOTvSphereConfig UI ViewSet."""

    queryset = SSOTvSphereConfig.objects.all()
    table_class = SSOTvSphereConfigTable
    filterset_class = SSOTvSphereConfigFilterSet
    filterset_form_class = SSOTvSphereConfigFilterForm
    form_class = SSOTvSphereConfigForm
    serializer_class = SSOTvSphereConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)

    def get_template_name(self):
        """Override inherited method to allow custom location for templates."""
        action = self.action
        app_label = "nautobot_ssot_vsphere"
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


class SSOTvSphereConfigChangeLogView(ObjectChangeLogView):
    """SSOTvSphereConfig ChangeLog View."""

    base_template = "nautobot_ssot_infoblox/ssotvsphereconfig_retrieve.html"


class SSOTvSphereConfigNotesView(ObjectNotesView):
    """SSOTvSphereConfig Notes View."""

    base_template = "nautobot_ssot_infoblox/ssotvsphereconfig_retrieve.html"
