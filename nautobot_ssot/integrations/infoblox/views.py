"""Views implementation for SSOT Infoblox."""

from nautobot.extras.views import ObjectChangeLogView, ObjectNotesView
from nautobot.apps.views import (
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectEditViewMixin,
    ObjectListViewMixin,
)

from .api.serializers import SSOTInfobloxConfigSerializer
from .filters import SSOTInfobloxConfigFilterSet
from .forms import SSOTInfobloxConfigFilterForm, SSOTInfobloxConfigForm
from .models import SSOTInfobloxConfig
from .tables import SSOTInfobloxConfigTable


class SSOTInfobloxConfigUIViewSet(
    ObjectDestroyViewMixin, ObjectDetailViewMixin, ObjectListViewMixin, ObjectEditViewMixin
):  # pylint: disable=abstract-method
    """SSOTInfobloxConfig UI ViewSet."""

    queryset = SSOTInfobloxConfig.objects.all()
    table_class = SSOTInfobloxConfigTable
    filterset_class = SSOTInfobloxConfigFilterSet
    filterset_form_class = SSOTInfobloxConfigFilterForm
    form_class = SSOTInfobloxConfigForm
    serializer_class = SSOTInfobloxConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)

    def get_template_name(self):
        """Override inherited method to allow custom location for templates."""
        action = self.action
        app_label = "nautobot_ssot_infoblox"
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


class SSOTInfobloxConfigChangeLogView(ObjectChangeLogView):
    """SSOTInfobloxConfig ChangeLog View."""

    base_template = "nautobot_ssot_infoblox/ssotinfobloxconfig_retrieve.html"


class SSOTInfobloxConfigNotesView(ObjectNotesView):
    """SSOTInfobloxConfig Notes View."""

    base_template = "nautobot_ssot_infoblox/ssotinfobloxconfig_retrieve.html"
