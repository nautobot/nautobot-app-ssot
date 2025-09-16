"""Forms for nautobot_ssot."""

from django import forms
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm, TagsBulkEditFormMixin

from nautobot_ssot import models


class SyncForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """Sync creation/edit form."""

    class Meta:
        """Meta attributes."""

        model = models.Sync
        fields = "__all__"


class SyncBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):  # pylint: disable=too-many-ancestors
    """Sync bulk edit form."""

    pk = forms.ModelMultipleChoiceField(queryset=models.Sync.objects.all(), widget=forms.MultipleHiddenInput)
    description = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)

    class Meta:
        """Meta attributes."""

        nullable_fields = [
            "description",
        ]


class SyncFilterForm(NautobotFilterForm):
    """Filter form to filter searches."""

    model = models.Sync
    field_order = ["q", "name"]

    q = forms.CharField(
        required=False,
        label="Search",
        help_text="Search within Name.",
    )
    name = forms.CharField(required=False, label="Name")
