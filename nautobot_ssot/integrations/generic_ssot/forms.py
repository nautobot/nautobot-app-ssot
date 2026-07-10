"""Forms for Generic SSoT Integration."""

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from nautobot.apps.forms import NautobotBulkEditForm

from .models import (
    SSOTEndpoint,
    SSOTEndpointJoin,
    SSOTFieldMapping,
    SSOTSyncConfig,
    SSOTSyncConfigEndpoint,
)


class SSOTEndpointForm(forms.ModelForm):
    """Form for SSoT Endpoint (add/edit)."""

    class Meta:
        """Meta class."""

        model = SSOTEndpoint
        fields = "__all__"


class SSOTEndpointFilterForm(forms.Form):
    """Filter form for SSOTEndpoint."""

    q = forms.CharField(required=False, label="Search")


class SSOTEndpointBulkEditForm(NautobotBulkEditForm):
    """Bulk edit form for SSOTEndpoint."""

    pk = forms.ModelMultipleChoiceField(
        queryset=SSOTEndpoint.objects.all(),
        widget=forms.MultipleHiddenInput,
    )
    weight = forms.IntegerField(required=False, min_value=0)
    pagination_type = forms.ChoiceField(
        choices=[("", "---------")]
        + [
            ("none", "No Pagination"),
            ("offset", "Offset-based (limit/offset)"),
            ("page", "Page-based (page/per_page)"),
            ("cursor", "Cursor-based"),
            ("link", "Link Header (RFC 5988)"),
        ],
        required=False,
    )
    http_method_read = forms.ChoiceField(
        choices=[("", "---------"), ("GET", "GET"), ("POST", "POST")],
        required=False,
    )

    class Meta:
        """Meta class."""

        model = SSOTEndpoint
        nullable_fields = []


class SSOTSyncConfigForm(forms.ModelForm):
    """Form for SSOTSyncConfig."""

    class Meta:
        """Meta class."""

        model = SSOTSyncConfig
        fields = "__all__"


class SSOTSyncConfigFilterForm(forms.Form):
    """Filter form for SSOTSyncConfig."""

    q = forms.CharField(required=False, label="Search")


class SSOTSyncConfigBulkEditForm(NautobotBulkEditForm):
    """Bulk edit form for SSOTSyncConfig."""

    pk = forms.ModelMultipleChoiceField(
        queryset=SSOTSyncConfig.objects.all(),
        widget=forms.MultipleHiddenInput,
    )
    sync_direction = forms.ChoiceField(
        choices=[("", "---------")]
        + [
            ("import", "Import (External → Nautobot)"),
            ("export", "Export (Nautobot → External)"),
            ("bidirectional", "Bidirectional"),
        ],
        required=False,
    )
    enabled = forms.NullBooleanField(required=False)
    dry_run_default = forms.NullBooleanField(required=False)
    delete_unmatched = forms.NullBooleanField(required=False)

    class Meta:
        """Meta class."""

        model = SSOTSyncConfig
        nullable_fields = []


class SSOTSyncConfigEndpointForm(forms.ModelForm):
    """Form for SSOTSyncConfigEndpoint (add endpoint to a sync config)."""

    class Meta:
        """Meta class."""

        model = SSOTSyncConfigEndpoint
        fields = "__all__"


class SSOTSyncConfigEndpointFilterForm(forms.Form):
    """Filter form for SSOTSyncConfigEndpoint."""

    sync_config = forms.ModelChoiceField(
        queryset=SSOTSyncConfig.objects.all(),
        required=False,
        label="Sync Config",
    )


class SSOTFieldMappingForm(forms.ModelForm):
    """Form for SSOTFieldMapping."""

    class Meta:
        """Meta class."""

        model = SSOTFieldMapping
        fields = "__all__"


class SSOTFieldMappingFilterForm(forms.Form):
    """Filter form for SSOTFieldMapping."""

    q = forms.CharField(required=False, label="Search")
    sync_config = forms.ModelChoiceField(
        queryset=SSOTSyncConfig.objects.all(),
        required=False,
        label="Sync Config",
    )
    endpoint = forms.ModelChoiceField(
        queryset=SSOTEndpoint.objects.all(),
        required=False,
        label="Endpoint",
    )


class SSOTEndpointJoinForm(forms.ModelForm):
    """Form for SSOTEndpointJoin."""

    class Meta:
        """Meta class."""

        model = SSOTEndpointJoin
        fields = "__all__"


class SSOTEndpointJoinFilterForm(forms.Form):
    """Filter form for SSOTEndpointJoin."""

    sync_config = forms.ModelChoiceField(
        queryset=SSOTSyncConfig.objects.all(),
        required=False,
        label="Sync Config",
    )


TRANSFORMATION_CHOICES = [
    ("none", "No Transformation"),
    ("static", "Static Value"),
    ("value_map", "Value Mapping"),
    ("type_cast", "Type Conversion"),
]

NAUTOBOT_CT_FILTER = Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"])


class FieldMappingRowForm(forms.Form):
    """A single row in the field mapping builder -- one per source field per endpoint.

    Each instance should be created with a unique ``prefix`` of the form
    ``{endpoint_name}__{source_field_name}`` so that HTML field names never
    collide when multiple rows are rendered in the same <form>.
    """

    endpoint_name = forms.CharField(widget=forms.HiddenInput)
    source_field = forms.CharField(widget=forms.HiddenInput)
    existing_mapping_pk = forms.UUIDField(widget=forms.HiddenInput, required=False)

    nautobot_content_type = forms.ModelChoiceField(
        queryset=ContentType.objects.filter(NAUTOBOT_CT_FILTER).order_by("app_label", "model"),
        required=False,
        empty_label="-- select model --",
        label="Nautobot Model",
    )
    nautobot_field = forms.CharField(
        max_length=255,
        required=False,
        label="Nautobot Field",
        widget=forms.TextInput(attrs={"placeholder": "e.g. name or location__name"}),
    )
    is_identifier = forms.BooleanField(required=False, label="Identifier?")
    is_required = forms.BooleanField(required=False, label="Required?")
    default_value = forms.CharField(
        max_length=500,
        required=False,
        label="Default",
        widget=forms.TextInput(attrs={"placeholder": "optional"}),
    )
    transformation_type = forms.ChoiceField(
        choices=TRANSFORMATION_CHOICES,
        required=False,
        initial="none",
        label="Transform",
    )
    enabled = forms.BooleanField(required=False, initial=True, label="Enabled")


class ModelCentricFieldMappingForm(forms.Form):
    """A single row in the model-centric field mapping builder.

    One form instance per Nautobot model field (as discovered by
    ``introspect_nautobot_model``).  The user enters a JMESPath expression
    to pull the value from the discovered data, and marks whether the field
    is an identifier used for matching.
    """

    # Hidden context fields
    nautobot_field = forms.CharField(widget=forms.HiddenInput)
    content_type_id = forms.IntegerField(widget=forms.HiddenInput)
    existing_mapping_pk = forms.UUIDField(widget=forms.HiddenInput, required=False)

    # User-editable fields
    source_field = forms.CharField(
        max_length=500,
        required=False,
        label="JMESPath",
        widget=forms.TextInput(attrs={"placeholder": "e.g. hostname"}),
    )
    is_identifier = forms.BooleanField(required=False, label="ID")
    is_required = forms.BooleanField(required=False, label="Req")
    default_value = forms.CharField(
        max_length=500,
        required=False,
        label="Default",
        widget=forms.TextInput(attrs={"placeholder": "default value"}),
    )
    value_map = forms.CharField(
        required=False,
        label="Value Map",
        widget=forms.Textarea(
            attrs={
                "placeholder": '{"0": "Active", "1": "Inactive"}',
                "rows": 2,
                "style": "font-family: monospace; font-size: 0.85rem;",
            }
        ),
    )
    transform_template = forms.CharField(
        required=False,
        label="Transform (Jinja)",
        widget=forms.Textarea(
            attrs={
                "placeholder": "{{ value | replace('.svg', '') }}",
                "rows": 2,
                "style": "font-family: monospace; font-size: 0.85rem;",
            }
        ),
        help_text="Jinja template — use {{ value }} to reference the source value.",
    )
    source_endpoint = forms.ModelChoiceField(
        queryset=SSOTEndpoint.objects.all(),
        required=False,
        empty_label="(primary)",
        label="Source EP",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
