"""User-facing forms for nautobot-ssot-servicenow."""

from django import forms

from nautobot.extras.models import SecretsGroup
from nautobot.core.forms import DynamicModelChoiceField

from .models import SSOTServiceNowConfig


class SSOTServiceNowConfigForm(forms.ModelForm):
    """App configuration form for nautobot-ssot-servicenow."""

    servicenow_instance = forms.CharField(
        required=True,
        help_text="ServiceNow instance name, will be used as <code>&lt;instance&gt;.servicenow.com</code>.",
    )
    servicenow_secrets = DynamicModelChoiceField(
        queryset=SecretsGroup.objects.all(),
        required=True,
        null_option="None",
        help_text="Secrets group for authentication to ServiceNow. Should contain a REST username and REST password.",
    )

    class Meta:
        """Meta class properties."""

        model = SSOTServiceNowConfig
        fields = ["servicenow_instance", "servicenow_secrets"]
