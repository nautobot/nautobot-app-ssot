"""Itential SSoT Views."""

from nautobot.apps import views
from nautobot_ssot.integrations.itential import forms, filters, tables, models
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
