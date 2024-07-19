"""Itential SSoT Forms."""

from django import forms

from nautobot.apps.forms import BootstrapMixin, BulkEditForm, NautobotModelForm

from nautobot_ssot.integrations.itential import models


class AutomationGatewayModelBulkEditForm(BootstrapMixin, BulkEditForm):
    """AutomationGatewayModel BulkEdit form."""

    pk = forms.ModelMultipleChoiceField(
        queryset=models.AutomationGatewayModel.objects.all(), widget=forms.MultipleHiddenInput
    )
    enabled = forms.BooleanField(required=False)

    class Meta:
        """Meta class definition."""

        nullable_fields = []


class AutomationGatewayModelFilterForm(BootstrapMixin, forms.Form):
    """AutotmationGatewayModel FilterForm form."""

    class Meta:
        """Meta class definition."""

        model = models.AutomationGatewayModel
        q = forms.CharField(required=False, label="Search")
        name = forms.CharField(required=False)
        enabled = forms.BooleanField(required=False)


class AutomationGatewayModelForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """AutomationGatewayModel Form form."""

    class Meta:
        """Meta class definition."""

        model = models.AutomationGatewayModel
        fields = ["name", "description", "location", "location_descendants", "gateway", "enabled"]
