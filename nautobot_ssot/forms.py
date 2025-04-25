"""Forms for working with Sync and SyncLogEntry models."""

from django import forms
from nautobot.apps.forms import BootstrapMixin, add_blank_choice
from nautobot.core.forms import BOOLEAN_WITH_BLANK_CHOICES

from .choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from .models import Sync, SyncLogEntry


class SyncFilterForm(BootstrapMixin, forms.ModelForm):
    """Form for filtering SyncOverview records."""

    dry_run = forms.ChoiceField(choices=BOOLEAN_WITH_BLANK_CHOICES, required=False)

    class Meta:
        """Metaclass attributes of SyncFilterForm."""

        model = models.Sync
        fields = "__all__"


class SyncLogEntryFilterForm(BootstrapMixin, forms.ModelForm):
    """Form for filtering SyncLogEntry records."""

    q = forms.CharField(required=False, label="Search")
    sync = forms.ModelChoiceField(queryset=Sync.objects.defer("diff").all(), required=False)
    action = forms.ChoiceField(choices=add_blank_choice(SyncLogEntryActionChoices), required=False)
    status = forms.ChoiceField(choices=add_blank_choice(SyncLogEntryStatusChoices), required=False)

    class Meta:
        """Metaclass attributes of SyncLogEntryFilterForm."""

        model = SyncLogEntry
        fields = ["sync", "action", "status"]


class SyncForm(BootstrapMixin, forms.Form):  # pylint: disable=nb-incorrect-base-class
    """Base class for dynamic form generation for a SyncWorker."""

    dry_run = forms.BooleanField(
        required=False,
        label="Search",
        help_text="Search within Name.",
    )
