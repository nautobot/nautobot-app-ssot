"""Models for Generic SSoT Integration."""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255

from nautobot.core.models.generics import BaseModel, PrimaryModel

ENDPOINT_TYPE_CHOICES = [
    ("bulk", "Bulk (list endpoint)"),
    ("child", "Child (per-parent endpoint)"),
]


class SSOTEndpoint(BaseModel):
    """
    Reusable endpoint definition tied to an External Integration.

    Used for both sample collection and sync operations.  Create under
    Plugins > SSoT > Endpoints; then add to a Sync Config.
    """

    clone_fields = [
        "integration",
        "api_path",
        "data_path",
        "http_method_read",
        "http_method_write",
        "request_headers",
        "query_parameters",
        "request_body_template",
        "pagination_type",
        "pagination_config",
        "weight",
        "endpoint_type",
        "parent_endpoint",
        "parent_key_field",
        "url_param_name",
    ]

    name = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        help_text="Friendly name (used as key in the discovery master dictionary)",
    )
    integration = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.CASCADE,
        related_name="ssot_endpoints",
    )
    api_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="API path to append to the integration's base URL (e.g., /api/v1/devices). "
        "For child endpoints, use {param_name} placeholders (e.g., /api/devices/{hostname}/ports).",
    )
    data_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="JMESPath to the data array in the response (e.g., results or data.items)",
    )
    http_method_read = models.CharField(
        max_length=10,
        choices=[("GET", "GET"), ("POST", "POST")],
        default="GET",
    )
    http_method_write = models.CharField(
        max_length=10,
        choices=[("POST", "POST"), ("PUT", "PUT"), ("PATCH", "PATCH")],
        default="POST",
        help_text="HTTP method for write operations (export direction)",
    )
    request_headers = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Additional request headers (JSON object)",
    )
    query_parameters = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Query parameters for GET (JSON object)",
    )
    request_body_template = models.TextField(
        blank=True,
        help_text="JSON body for POST read requests (leave blank for GET)",
    )
    pagination_type = models.CharField(
        max_length=50,
        choices=[
            ("none", "No Pagination"),
            ("offset", "Offset-based (limit/offset)"),
            ("page", "Page-based (page/per_page)"),
            ("cursor", "Cursor-based"),
            ("link", "Link Header (RFC 5988)"),
        ],
        default="none",
    )
    pagination_config = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text='Pagination config: e.g. {"limit_param": "limit", "offset_param": "offset", "page_size": 100}',
    )
    normalize_config = models.JSONField(
        default=list,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text=(
            "Ordered list of canonical field definitions used to normalize raw API records "
            'before mapping. Each entry: {"name": str, "source": JMESPath, "fallback": JMESPath, '
            '"transforms": [{"type": str, "config": {...}}, ...]}.'
        ),
    )
    weight = models.PositiveIntegerField(
        default=100,
        help_text="Order when running multiple endpoints (lower first)",
    )

    # -- Child/dependency endpoint fields --
    endpoint_type = models.CharField(
        max_length=10,
        choices=ENDPOINT_TYPE_CHOICES,
        default="bulk",
        help_text="Bulk endpoints fetch a list; child endpoints are called per-parent record.",
    )
    parent_endpoint = models.ForeignKey(
        to="self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_endpoints",
        help_text="Parent endpoint (required when endpoint_type is 'child').",
    )
    parent_key_field = models.CharField(
        max_length=500,
        blank=True,
        help_text="JMESPath to extract the key value from each parent record (e.g., 'hostname').",
    )
    url_param_name = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        blank=True,
        help_text="Placeholder name in api_path for substitution (e.g., 'hostname' for /api/devices/{hostname}/ports).",
    )

    class Meta:
        """Meta class for SSOTEndpoint."""

        app_label = "nautobot_ssot"
        ordering = ["weight", "name"]
        unique_together = [["integration", "name"]]
        verbose_name = "SSoT Endpoint"
        verbose_name_plural = "SSoT Endpoints"

    def __str__(self):
        """String representation."""
        return f"{self.integration.name} - {self.name}"

    def clean(self):
        """Validate child endpoint configuration."""
        from django.core.exceptions import ValidationError  # pylint: disable=import-outside-toplevel

        super().clean()
        if self.endpoint_type == "child":
            errors = {}
            if not self.parent_endpoint:
                errors["parent_endpoint"] = "Parent endpoint is required for child endpoints."
            if not self.parent_key_field:
                errors["parent_key_field"] = "Parent key field is required for child endpoints."
            if errors:
                raise ValidationError(errors)

    def to_endpoint_dict(self):
        """Return a dict suitable for fetch_data_from_endpoint_definition."""
        return {
            "name": self.name,
            "api_path": self.api_path or "",
            "data_path": self.data_path or "",
            "http_method_read": self.http_method_read or "GET",
            "request_headers": self.request_headers or {},
            "query_parameters": self.query_parameters or {},
            "request_body_template": self.request_body_template or "",
            "pagination_type": self.pagination_type or "none",
            "pagination_config": self.pagination_config or {},
        }


class SSOTSyncConfig(PrimaryModel):
    """Configuration for a Generic SSoT sync operation."""

    is_saved_view_model = False

    clone_fields = [
        "description",
        "synced_content_types",
        "primary_endpoint",
        "endpoints",
        "sync_direction",
        "dry_run_default",
        "delete_unmatched",
    ]

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    description = models.TextField(blank=True)

    synced_content_types = models.ManyToManyField(
        to="contenttypes.ContentType",
        blank=True,
        limit_choices_to=models.Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"]),
        related_name="ssot_sync_configs",
        help_text="Nautobot content types this config syncs. Drives the field mapping builder.",
    )

    primary_endpoint = models.ForeignKey(
        to="SSOTEndpoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_for_sync_configs",
        help_text="Default endpoint that drives record iteration.",
    )

    endpoints = models.ManyToManyField(
        to="SSOTEndpoint",
        through="SSOTSyncConfigEndpoint",
        related_name="sync_configs",
        blank=True,
        help_text="Endpoints to sync (order controlled by weight on the through model)",
    )

    sync_direction = models.CharField(
        max_length=50,
        choices=[
            ("import", "Import (External → Nautobot)"),
            ("export", "Export (Nautobot → External)"),
            ("bidirectional", "Bidirectional"),
        ],
        default="import",
    )

    dry_run_default = models.BooleanField(
        default=True,
        help_text="Default value for dry-run when running sync jobs",
    )

    enabled = models.BooleanField(
        default=True,
        help_text="Enable this sync configuration",
    )

    delete_unmatched = models.BooleanField(
        default=False,
        help_text="Delete Nautobot objects not present in the external source during sync. "
        "When False (default), existing Nautobot objects are preserved.",
    )

    class Meta:
        """Meta class for SSOTSyncConfig."""

        app_label = "nautobot_ssot"
        verbose_name = "SSOT Sync Config"
        verbose_name_plural = "SSOT Sync Configs"

    def __str__(self):
        """String representation."""
        return self.name

    def get_ordered_endpoints(self):
        """Return endpoints in weight order (for sync)."""
        return [se.endpoint for se in self.sync_config_endpoints.order_by("weight").select_related("endpoint")]


class SSOTSyncConfigEndpoint(BaseModel):
    """Through model: which endpoints a Sync Config uses, and in what order."""

    sync_config = models.ForeignKey(
        to="SSOTSyncConfig",
        on_delete=models.CASCADE,
        related_name="sync_config_endpoints",
    )
    endpoint = models.ForeignKey(
        to="SSOTEndpoint",
        on_delete=models.CASCADE,
        related_name="sync_config_endpoints",
    )
    weight = models.PositiveIntegerField(
        default=100,
        help_text="Order when syncing (lower first)",
    )

    class Meta:
        """Meta class for SSOTSyncConfigEndpoint."""

        app_label = "nautobot_ssot"
        ordering = ["weight", "endpoint__name"]
        unique_together = [["sync_config", "endpoint"]]
        verbose_name = "Sync Config Endpoint"
        verbose_name_plural = "Sync Config Endpoints"

    def __str__(self):
        """String representation."""
        return f"{self.sync_config.name} - {self.endpoint.name}"


JOIN_TYPE_CHOICES = [
    ("left", "Left Join (keep all source records)"),
    ("inner", "Inner Join (only matching records)"),
]


class SSOTEndpointJoin(BaseModel):
    """Defines how two endpoints are joined for cross-endpoint field mapping."""

    sync_config = models.ForeignKey(
        to="SSOTSyncConfig",
        on_delete=models.CASCADE,
        related_name="endpoint_joins",
    )
    source_endpoint = models.ForeignKey(
        to="SSOTEndpoint",
        on_delete=models.CASCADE,
        related_name="joins_as_source",
        help_text="Driving (left) endpoint whose records are iterated.",
    )
    source_key = models.CharField(
        max_length=500,
        help_text="JMESPath on source records to extract the join key.",
    )
    target_endpoint = models.ForeignKey(
        to="SSOTEndpoint",
        on_delete=models.CASCADE,
        related_name="joins_as_target",
        help_text="Looked-up (right) endpoint whose records are matched.",
    )
    target_key = models.CharField(
        max_length=500,
        help_text="JMESPath on target records to extract the join key.",
    )
    join_type = models.CharField(
        max_length=10,
        choices=JOIN_TYPE_CHOICES,
        default="left",
    )

    class Meta:
        """Meta class for SSOTEndpointJoin."""

        app_label = "nautobot_ssot"
        unique_together = [["sync_config", "source_endpoint", "target_endpoint"]]
        verbose_name = "SSoT Endpoint Join"
        verbose_name_plural = "SSoT Endpoint Joins"

    def __str__(self):
        """String representation."""
        return f"{self.source_endpoint.name}.{self.source_key} → {self.target_endpoint.name}.{self.target_key}"


class SSOTValueMap(PrimaryModel):
    """Reusable value mapping table for field transformations."""

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    description = models.TextField(blank=True)

    mappings = models.JSONField(
        default=dict,
        encoder=DjangoJSONEncoder,
        help_text="Dictionary mapping source values to target values",
    )

    default_value = models.JSONField(
        null=True,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Default value to use if source value is not in the mapping",
    )

    case_sensitive = models.BooleanField(
        default=False,
        help_text="Whether string matching is case-sensitive",
    )

    class Meta:
        """Meta class for SSOTValueMap."""

        app_label = "nautobot_ssot"
        verbose_name = "SSOT Value Map"
        verbose_name_plural = "SSOT Value Maps"

    def __str__(self):
        """String representation."""
        return self.name


class SSOTFieldMapping(BaseModel):
    """Maps a field from external data (for a given endpoint) to a Nautobot model field."""

    sync_config = models.ForeignKey(
        to="SSOTSyncConfig",
        on_delete=models.CASCADE,
        related_name="field_mappings",
    )
    endpoint = models.ForeignKey(
        to="SSOTEndpoint",
        on_delete=models.CASCADE,
        related_name="field_mappings",
    )

    nautobot_content_type = models.ForeignKey(
        to="contenttypes.ContentType",
        on_delete=models.CASCADE,
        limit_choices_to=models.Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"]),
    )

    source_field = models.CharField(
        max_length=500,
        help_text="JMESPath expression to extract data (e.g., 'hostname', 'attributes.location.name')",
    )

    nautobot_field = models.CharField(
        max_length=255,
        help_text="Nautobot model field name (e.g., 'name' or 'location__name' for related fields)",
    )

    is_identifier = models.BooleanField(
        default=False,
        help_text="If True, this field is used to uniquely identify objects for updates",
    )

    is_required = models.BooleanField(
        default=False,
        help_text="If True, records missing this field will be skipped",
    )

    default_value = models.JSONField(
        null=True,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Default value to use if source field is missing or null",
    )

    transformation_type = models.CharField(
        max_length=50,
        choices=[
            ("none", "No Transformation"),
            ("static", "Static Value"),
            ("value_map", "Value Mapping"),
            ("type_cast", "Type Conversion"),
        ],
        default="none",
    )

    transformation_config = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Configuration for the selected transformation type",
    )

    value_map = models.ForeignKey(
        to="SSOTValueMap",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_mappings",
        help_text="Value map to use for transformation (if transformation_type is value_map)",
    )

    enabled = models.BooleanField(default=True)

    source_endpoint = models.ForeignKey(
        to="SSOTEndpoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_field_mappings",
        help_text="Which endpoint this field's data comes from. Null = use section's primary endpoint.",
    )

    class Meta:
        """Meta class for SSOTFieldMapping."""

        app_label = "nautobot_ssot"
        ordering = ["sync_config", "endpoint", "-is_identifier", "nautobot_field"]
        unique_together = [["sync_config", "nautobot_content_type", "nautobot_field"]]
        verbose_name = "SSOT Field Mapping"
        verbose_name_plural = "SSOT Field Mappings"

    def __str__(self):
        """String representation."""
        return f"{self.endpoint.name}: {self.source_field} → {self.nautobot_field}"


FK_ON_MISSING_CHOICES = [
    ("skip_record", "Skip this record"),
    ("create", "Create it automatically"),
]


class SSOTFKCreateRule(BaseModel):
    """Defines what to do when a referenced FK object cannot be found in Nautobot.

    One rule per (sync_config, target model) pair.  When the sync adapter resolves
    a relationship field (e.g. ``location__name``) and the referenced object is
    absent, the rule determines whether to skip the whole source record or
    auto-create the missing object using its name.
    """

    sync_config = models.ForeignKey(
        to="SSOTSyncConfig",
        on_delete=models.CASCADE,
        related_name="fk_create_rules",
    )
    target_content_type = models.ForeignKey(
        to="contenttypes.ContentType",
        on_delete=models.CASCADE,
        limit_choices_to=models.Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"]),
        help_text="The related Nautobot model (e.g. Location, Status, Role).",
    )
    on_missing = models.CharField(
        max_length=20,
        choices=FK_ON_MISSING_CHOICES,
        default="skip_record",
        help_text="What to do when the referenced object cannot be found in Nautobot.",
    )
    creation_defaults = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Static default field values to use when auto-creating a missing related object. "
            "Keys are field names (use __ for FK traversal, e.g. 'manufacturer__name'). "
            'Only used when on_missing=\'create\'. Example: {"manufacturer__name": "Unknown"}'
        ),
    )

    class Meta:
        """Meta class for SSOTFKCreateRule."""

        app_label = "nautobot_ssot"
        unique_together = [["sync_config", "target_content_type"]]
        verbose_name = "FK Create Rule"
        verbose_name_plural = "FK Create Rules"

    def __str__(self):
        """String representation."""
        return f"{self.sync_config.name}: {self.target_content_type} → {self.get_on_missing_display()}"


class SSOTDataSample(BaseModel):
    """Stores sample data from an endpoint for mapping configuration."""

    endpoint = models.ForeignKey(
        to="SSOTEndpoint",
        on_delete=models.CASCADE,
        related_name="data_samples",
    )

    sample_data = models.JSONField(
        default=list,
        encoder=DjangoJSONEncoder,
        help_text="Sample records from the API for field discovery",
    )

    discovered_fields = models.JSONField(
        default=dict,
        encoder=DjangoJSONEncoder,
        help_text="Auto-discovered field names and inferred types",
    )

    collected_at = models.DateTimeField(auto_now=True)

    total_record_count = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        """Meta class for SSOTDataSample."""

        app_label = "nautobot_ssot"
        ordering = ["-collected_at"]
        verbose_name = "SSOT Data Sample"
        verbose_name_plural = "SSOT Data Samples"

    def __str__(self):
        """String representation."""
        return f"{self.endpoint.name} - {self.collected_at}"
