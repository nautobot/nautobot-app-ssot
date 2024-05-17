"""Forms implementation for SSOT Infoblox."""

from nautobot.extras.forms import NautobotModelForm, NautobotFilterForm
from nautobot.apps.forms import JSONField

from .models import SSOTInfobloxConfig


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
