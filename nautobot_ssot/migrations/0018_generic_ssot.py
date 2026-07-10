"""Single consolidated migration for Generic SSoT integration (final state)."""

import django.core.serializers.json
import django.db.models.deletion
import nautobot.core.models.fields
import nautobot.extras.models.mixins
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0017_ssotvsphereconfig_sync_vsphere_tags"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("extras", "0102_set_null_objectchange_contenttype"),
    ]

    operations = [
        # ── SSOTEndpoint ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="SSOTEndpoint",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "name",
                    models.CharField(
                        help_text="Friendly name (used as key in the discovery master dictionary)",
                        max_length=255,
                    ),
                ),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ssot_endpoints",
                        to="extras.externalintegration",
                    ),
                ),
                ("api_path", models.CharField(blank=True, max_length=500)),
                ("data_path", models.CharField(blank=True, max_length=255)),
                (
                    "http_method_read",
                    models.CharField(
                        choices=[("GET", "GET"), ("POST", "POST")],
                        default="GET",
                        max_length=10,
                    ),
                ),
                (
                    "http_method_write",
                    models.CharField(
                        choices=[("POST", "POST"), ("PUT", "PUT"), ("PATCH", "PATCH")],
                        default="POST",
                        max_length=10,
                    ),
                ),
                (
                    "request_headers",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                (
                    "query_parameters",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("request_body_template", models.TextField(blank=True)),
                (
                    "pagination_type",
                    models.CharField(
                        choices=[
                            ("none", "No Pagination"),
                            ("offset", "Offset-based (limit/offset)"),
                            ("page", "Page-based (page/per_page)"),
                            ("cursor", "Cursor-based"),
                            ("link", "Link Header (RFC 5988)"),
                        ],
                        default="none",
                        max_length=50,
                    ),
                ),
                (
                    "pagination_config",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("weight", models.PositiveIntegerField(default=100)),
                (
                    "endpoint_type",
                    models.CharField(
                        choices=[
                            ("bulk", "Bulk (list endpoint)"),
                            ("child", "Child (per-parent endpoint)"),
                        ],
                        default="bulk",
                        max_length=10,
                    ),
                ),
                (
                    "parent_endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="child_endpoints",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
                ("parent_key_field", models.CharField(blank=True, max_length=500)),
                ("url_param_name", models.CharField(blank=True, max_length=255)),
            ],
            options={
                "verbose_name": "SSoT Endpoint",
                "verbose_name_plural": "SSoT Endpoints",
                "ordering": ["weight", "name"],
                "unique_together": {("integration", "name")},
            },
        ),
        # ── SSOTValueMap ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="SSOTValueMap",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "_custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("name", models.CharField(max_length=255, unique=True)),
                ("description", models.TextField(blank=True)),
                (
                    "mappings",
                    models.JSONField(
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("default_value", models.JSONField(blank=True, null=True)),
                ("case_sensitive", models.BooleanField(default=False)),
                ("tags", nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "SSOT Value Map",
                "verbose_name_plural": "SSOT Value Maps",
            },
            bases=(
                models.Model,
                nautobot.extras.models.mixins.DynamicGroupMixin,
                nautobot.extras.models.mixins.NotesMixin,
            ),
        ),
        # ── SSOTSyncConfig ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="SSOTSyncConfig",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "_custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("name", models.CharField(max_length=255, unique=True)),
                ("description", models.TextField(blank=True)),
                (
                    "primary_endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="primary_for_sync_configs",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
                (
                    "sync_direction",
                    models.CharField(
                        choices=[
                            ("import", "Import (External → Nautobot)"),
                            ("export", "Export (Nautobot → External)"),
                            ("bidirectional", "Bidirectional"),
                        ],
                        default="import",
                        max_length=50,
                    ),
                ),
                ("dry_run_default", models.BooleanField(default=True)),
                ("enabled", models.BooleanField(default=True)),
                ("delete_unmatched", models.BooleanField(default=False)),
                (
                    "synced_content_types",
                    models.ManyToManyField(
                        blank=True,
                        limit_choices_to=models.Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"]),
                        related_name="ssot_sync_configs",
                        to="contenttypes.ContentType",
                    ),
                ),
                ("tags", nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "SSOT Sync Config",
                "verbose_name_plural": "SSOT Sync Configs",
            },
            bases=(
                models.Model,
                nautobot.extras.models.mixins.DynamicGroupMixin,
                nautobot.extras.models.mixins.NotesMixin,
            ),
        ),
        # ── SSOTSyncConfigEndpoint (through model) ────────────────────────────
        migrations.CreateModel(
            name="SSOTSyncConfigEndpoint",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("weight", models.PositiveIntegerField(default=100)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sync_config_endpoints",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
                (
                    "sync_config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sync_config_endpoints",
                        to="nautobot_ssot.ssotsyncconfig",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sync Config Endpoint",
                "verbose_name_plural": "Sync Config Endpoints",
                "ordering": ["weight", "endpoint__name"],
                "unique_together": {("sync_config", "endpoint")},
            },
        ),
        # Add M2M endpoints field to SSOTSyncConfig via through model
        migrations.AddField(
            model_name="ssotsyncconfig",
            name="endpoints",
            field=models.ManyToManyField(
                blank=True,
                related_name="sync_configs",
                through="nautobot_ssot.SSOTSyncConfigEndpoint",
                to="nautobot_ssot.SSOTEndpoint",
            ),
        ),
        # ── SSOTEndpointJoin ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="SSOTEndpointJoin",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "sync_config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="endpoint_joins",
                        to="nautobot_ssot.ssotsyncconfig",
                    ),
                ),
                (
                    "source_endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="joins_as_source",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
                ("source_key", models.CharField(max_length=500)),
                (
                    "target_endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="joins_as_target",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
                ("target_key", models.CharField(max_length=500)),
                (
                    "join_type",
                    models.CharField(
                        choices=[
                            ("left", "Left Join (keep all source records)"),
                            ("inner", "Inner Join (only matching records)"),
                        ],
                        default="left",
                        max_length=10,
                    ),
                ),
            ],
            options={
                "verbose_name": "SSoT Endpoint Join",
                "verbose_name_plural": "SSoT Endpoint Joins",
                "unique_together": {("sync_config", "source_endpoint", "target_endpoint")},
            },
        ),
        # ── SSOTFieldMapping ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="SSOTFieldMapping",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "sync_config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="field_mappings",
                        to="nautobot_ssot.ssotsyncconfig",
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="field_mappings",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
                (
                    "nautobot_content_type",
                    models.ForeignKey(
                        limit_choices_to=models.Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"]),
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
                ("source_field", models.CharField(max_length=500)),
                ("nautobot_field", models.CharField(max_length=255)),
                ("is_identifier", models.BooleanField(default=False)),
                ("is_required", models.BooleanField(default=False)),
                ("default_value", models.JSONField(blank=True, null=True)),
                (
                    "transformation_type",
                    models.CharField(
                        choices=[
                            ("none", "No Transformation"),
                            ("static", "Static Value"),
                            ("value_map", "Value Mapping"),
                            ("type_cast", "Type Conversion"),
                        ],
                        default="none",
                        max_length=50,
                    ),
                ),
                (
                    "transformation_config",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                (
                    "value_map",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="field_mappings",
                        to="nautobot_ssot.ssotvaluemap",
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                (
                    "source_endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_field_mappings",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
            ],
            options={
                "verbose_name": "SSOT Field Mapping",
                "verbose_name_plural": "SSOT Field Mappings",
                "ordering": ["sync_config", "endpoint", "-is_identifier", "nautobot_field"],
                "unique_together": {("sync_config", "nautobot_content_type", "nautobot_field")},
            },
        ),
        # ── SSOTFKCreateRule ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="SSOTFKCreateRule",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "sync_config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fk_create_rules",
                        to="nautobot_ssot.ssotsyncconfig",
                    ),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        limit_choices_to=models.Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"]),
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "on_missing",
                    models.CharField(
                        choices=[
                            ("skip_record", "Skip this record"),
                            ("create", "Create it automatically"),
                        ],
                        default="skip_record",
                        max_length=20,
                    ),
                ),
                ("creation_defaults", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "FK Create Rule",
                "verbose_name_plural": "FK Create Rules",
                "unique_together": {("sync_config", "target_content_type")},
            },
        ),
        # ── SSOTDataSample ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="SSOTDataSample",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="data_samples",
                        to="nautobot_ssot.ssotendpoint",
                    ),
                ),
                (
                    "sample_data",
                    models.JSONField(
                        default=list,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                (
                    "discovered_fields",
                    models.JSONField(
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("collected_at", models.DateTimeField(auto_now=True)),
                ("total_record_count", models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "SSOT Data Sample",
                "verbose_name_plural": "SSOT Data Samples",
                "ordering": ["-collected_at"],
            },
        ),
    ]
