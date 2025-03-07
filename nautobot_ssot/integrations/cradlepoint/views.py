"""Views implementing the Cradlepoint integration."""

# pylint: disable=duplicate-code
from nautobot.apps.views import (
    ObjectChangeLogViewMixin,
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectEditViewMixin,
    ObjectListViewMixin,
    ObjectNotesViewMixin,
)
from nautobot.extras.views import ObjectChangeLogView, ObjectNotesView

from .api.serializers import SSOTCradlepointConfigSerializer
from .filters import SSOTCradlepointConfigFilterSet
from .forms import SSOTCradlepointConfigFilterForm, SSOTCradlepointConfigForm
from .models import SSOTCradlepointConfig
from .tables import SSOTCradlepointConfigTable


class SSOTCradlepointConfigUIViewSet(
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectEditViewMixin,
    ObjectChangeLogViewMixin,
    ObjectNotesViewMixin,
):  # pylint: disable=abstract-method
    """SSOTCradlepointConfig UI ViewSet."""

    queryset = SSOTCradlepointConfig.objects.all()
    table_class = SSOTCradlepointConfigTable
    filterset_class = SSOTCradlepointConfigFilterSet
    filterset_form_class = SSOTCradlepointConfigFilterForm
    form_class = SSOTCradlepointConfigForm
    serializer_class = SSOTCradlepointConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)

    def get_template_name(self):
        """Override inherited method to allow custom location for templates."""
        action = self.action
        app_label = "nautobot_ssot_cradlepoint"
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


class SSOTCradlepointConfigChangeLogView(ObjectChangeLogView):
    """SSOTCradlepointConfig ChangeLog View."""

    base_template = "nautobot_ssot_cradlepoint/ssotcradlepointconfig_retrieve.html"


class SSOTCradlepointConfigNotesView(ObjectNotesView):
    """SSOTCradlepointConfig Notes View."""

    base_template = "nautobot_ssot_cradlepoint/ssotcradlepointconfig_retrieve.html"
