"""Forms for working with Sync and SyncLogEntry models."""

from django import forms
<<<<<<< HEAD
from nautobot.apps.forms import BootstrapMixin, add_blank_choice
from nautobot.core.forms import BOOLEAN_WITH_BLANK_CHOICES
=======
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm, TagsBulkEditFormMixin
>>>>>>> 481ce30 (Cookie updated by NetworkToCode Cookie Drift Manager Tool)

from .choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from .models import Sync, SyncLogEntry


class SyncFilterForm(BootstrapMixin, forms.ModelForm):
    """Form for filtering SyncOverview records."""

    dry_run = forms.ChoiceField(choices=BOOLEAN_WITH_BLANK_CHOICES, required=False)

    class Meta:
        """Metaclass attributes of SyncFilterForm."""

        model = Sync
        fields = ["dry_run"]


class SyncLogEntryFilterForm(BootstrapMixin, forms.ModelForm):
    """Form for filtering SyncLogEntry records."""

<<<<<<< HEAD
    q = forms.CharField(required=False, label="Search")
    sync = forms.ModelChoiceField(queryset=Sync.objects.defer("diff").all(), required=False)
    action = forms.ChoiceField(choices=add_blank_choice(SyncLogEntryActionChoices), required=False)
    status = forms.ChoiceField(choices=add_blank_choice(SyncLogEntryStatusChoices), required=False)
=======
    pk = forms.ModelMultipleChoiceField(queryset=models.Sync.objects.all(), widget=forms.MultipleHiddenInput)
    description = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)
>>>>>>> 481ce30 (Cookie updated by NetworkToCode Cookie Drift Manager Tool)

    class Meta:
        """Metaclass attributes of SyncLogEntryFilterForm."""

        model = SyncLogEntry
        fields = ["sync", "action", "status"]


class SyncForm(BootstrapMixin, forms.Form):  # pylint: disable=nb-incorrect-base-class
    """Base class for dynamic form generation for a SyncWorker."""

    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label="Dry run",
        help_text="Perform a dry run, making no actual changes to the database.",
    )
