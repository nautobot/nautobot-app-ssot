"""Forms implementation for SSOT Infoblox."""

from django import forms

from nautobot.extras.forms import NautobotModelForm, NautobotFilterForm
from nautobot.apps.forms import add_blank_choice, JSONField, StaticSelect2, StaticSelect2Multiple

from .models import SSOTInfobloxConfig
from .choices import (
    FixedAddressTypeChoices,
    DNSRecordTypeChoices,
    InfobloxDeletableModelChoices,
    NautobotDeletableModelChoices,
)


class SSOTInfobloxConfigForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """SSOTInfobloxConfig creation/edit form."""

    infoblox_sync_filters = JSONField(
        required=True, label="Infoblox Sync Filters", help_text="Filters controlling data loaded from both systems."
    )
    infoblox_dns_view_mapping = JSONField(
        required=False,
        label="Infoblox Network View to DNS Mapping",
        help_text="Maps Network View to a single DNS View. This DNS View is used when creating DNS records.",
    )
    cf_fields_ignore = JSONField(
        required=False,
        label="Extensible Attributes/Custom Fields to Ignore",
        help_text="Provide list of Extensible Attributes and Custom Fields to ignore during sync."
        " Assign lists to keys `extensible_attributes` and `custom_fields`.",
    )
    fixed_address_type = forms.ChoiceField(
        choices=FixedAddressTypeChoices,
        required=True,
        label="Fixed Address type",
        widget=StaticSelect2(),
    )
    dns_record_type = forms.ChoiceField(
        choices=DNSRecordTypeChoices,
        required=True,
        label="DNS record type",
        widget=StaticSelect2(),
    )
    infoblox_deletable_models = forms.MultipleChoiceField(
        required=False,
        label="Models that can be deleted in Infoblox",
        choices=add_blank_choice(InfobloxDeletableModelChoices),
        widget=StaticSelect2Multiple(),
    )
    nautobot_deletable_models = forms.MultipleChoiceField(
        required=False,
        label="Models that can be deleted in Nautobot",
        choices=add_blank_choice(NautobotDeletableModelChoices),
        widget=StaticSelect2Multiple(),
    )

    class Meta:
        """Meta attributes for the SSOTInfobloxConfigForm class."""

        model = SSOTInfobloxConfig
        fields = "__all__"


class SSOTInfobloxConfigFilterForm(NautobotFilterForm):
    """Filter form for SSOTInfobloxConfig filter searches."""

    model = SSOTInfobloxConfig

    class Meta:
        """Meta attributes for the SSOTInfobloxConfigFilterForm class."""

        model = SSOTInfobloxConfig
        fields = "__all__"
