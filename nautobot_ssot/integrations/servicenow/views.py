"""UI view classes and methods for nautobot-ssot-servicenow."""

from django.contrib import messages
from django.views.generic import UpdateView

from nautobot.core.forms import restrict_form_fields

from .forms import SSOTServiceNowConfigForm
from .models import SSOTServiceNowConfig


class SSOTServiceNowConfigView(UpdateView):
    """App configuration view for nautobot-ssot-servicenow."""

    form_class = SSOTServiceNowConfigForm
    template_name = "nautobot_ssot_servicenow/config.html"

    def get_object(self, queryset=None):  # pylint: disable=unused-argument
        """Retrieve the SSOTServiceNowConfig singleton instance."""
        return SSOTServiceNowConfig.load()

    def get_context_data(self, **kwargs):
        """Get all necessary context for the view."""
        context = super().get_context_data(**kwargs)
        restrict_form_fields(context["form"], self.request.user)
        context["editing"] = True
        context["obj"] = self.get_object()
        return context

    def form_valid(self, form):
        """Callback when the form is submitted successfully."""
        messages.success(self.request, "Successfully updated configuration")
        return super().form_valid(form)
