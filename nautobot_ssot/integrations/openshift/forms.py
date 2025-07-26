"""Forms for OpenShift integration."""
from django import forms
from nautobot.core.forms import BootstrapMixin
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigForm(BootstrapMixin, forms.ModelForm):
    """Form for SSOTOpenshiftConfig model."""
    
    api_token = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
        required=True,
        help_text="Service account token for authentication",
    )
    
    class Meta:
        """Meta class for form."""
        model = SSOTOpenshiftConfig
        fields = "__all__"
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class SSOTOpenshiftConfigFilterForm(BootstrapMixin, forms.Form):
    """Filter form for SSOTOpenshiftConfig."""
    
    q = forms.CharField(required=False, label="Search")
    name = forms.CharField(required=False)
    url = forms.CharField(required=False)
