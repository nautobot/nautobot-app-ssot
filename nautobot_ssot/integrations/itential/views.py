"""Itential SSoT Views."""

from nautobot.apps import views
from nautobot.apps.ui import (
    Breadcrumbs,
    ModelBreadcrumbItem,
    ObjectDetailContent,
    ObjectFieldsPanel,
    SectionChoices,
    ViewNameBreadcrumbItem,
)

from nautobot_ssot.integrations.itential import filters, forms, models, tables
from nautobot_ssot.integrations.itential.api import serializers


class AutomationGatewayModelUIViewSet(views.NautobotUIViewSet):
    """Automation Gateway Model UI ViewSet class."""

    bulk_update_form_class = forms.AutomationGatewayModelBulkEditForm
    filterset_class = filters.AutomationGatewayModelFilterSet
    filterset_form_class = forms.AutomationGatewayModelFilterForm
    form_class = forms.AutomationGatewayModelForm
    queryset = models.AutomationGatewayModel.objects.all()
    serializer_class = serializers.AutomationGatewayModelSerializer
    table_class = tables.AutomationGatewayModelTable
    lookup_field = "pk"
    breadcrumbs = Breadcrumbs(
        items={
            "list": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ModelBreadcrumbItem(model=models.AutomationGatewayModel),
            ],
            "detail": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ModelBreadcrumbItem(),
            ],
        }
    )

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields="__all__",
            ),
        )
    )
