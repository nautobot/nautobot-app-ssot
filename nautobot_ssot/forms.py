"""Forms for working with Sync and SyncLogEntry models."""

from django import forms
from nautobot.apps.forms import (
    BootstrapMixin,
    DynamicModelMultipleChoiceField,
    NautobotBulkEditForm,
    NautobotFilterForm,
    add_blank_choice,
)
from nautobot.core.forms import BOOLEAN_WITH_BLANK_CHOICES

from .choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from .models import Sync, SyncLogEntry


class SyncFilterForm(NautobotFilterForm):  # pylint: disable=too-many-ancestors
    """Form for filtering SyncOverview records."""

    model = Sync
    q = forms.CharField(required=False, label="Search")
    dry_run = forms.ChoiceField(choices=BOOLEAN_WITH_BLANK_CHOICES, required=False)


class SyncLogEntryFilterForm(NautobotFilterForm):  # pylint: disable=too-many-ancestors
    """Form for filtering SyncLogEntry records."""

    model = SyncLogEntry
    q = forms.CharField(required=False, label="Search")
    sync = DynamicModelMultipleChoiceField(
        queryset=Sync.objects.defer("diff").all(),
        required=False,
        label="Sync",
    )
    action = forms.ChoiceField(choices=add_blank_choice(SyncLogEntryActionChoices), required=False)
    status = forms.ChoiceField(choices=add_blank_choice(SyncLogEntryStatusChoices), required=False)


class SyncForm(BootstrapMixin, forms.Form):  # pylint: disable=nb-incorrect-base-class
    """Base class for dynamic form generation for a SyncWorker."""

    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label="Dry run",
        help_text="Perform a dry run, making no actual changes to the database.",
    )


class SyncBulkEditForm(NautobotBulkEditForm):  # pylint: disable=too-many-ancestors
    """Form for bulk editing Sync records."""

    dry_run = forms.NullBooleanField(
        required=False,
        label="Dry run",
        help_text="Perform a dry run, making no actual changes to the database.",
    )

    class Meta:
        """Metaclass attributes of SyncBulkEditForm."""

        model = Sync
