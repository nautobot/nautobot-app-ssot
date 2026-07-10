"""Forms for the Data Import integration."""

from django import forms
from nautobot.apps.forms import NautobotBulkEditForm

from nautobot_ssot.integrations.data_import.models import ImportPlan


class ImportPlanForm(forms.ModelForm):
    """Add/edit form for ImportPlan.

    The document, cached tables, and CSV data are managed by the builder UI,
    not this form.
    """

    class Meta:
        """Meta class."""

        model = ImportPlan
        fields = ["name", "description", "integration", "enabled"]


class ImportPlanFilterForm(forms.Form):
    """Filter form for ImportPlan."""

    q = forms.CharField(required=False, label="Search")


class ImportPlanBulkEditForm(NautobotBulkEditForm):
    """Bulk edit form for ImportPlan."""

    pk = forms.ModelMultipleChoiceField(
        queryset=ImportPlan.objects.all(),
        widget=forms.MultipleHiddenInput,
    )
    enabled = forms.NullBooleanField(required=False)

    class Meta:
        """Meta class."""

        model = ImportPlan
        nullable_fields = ["description"]
