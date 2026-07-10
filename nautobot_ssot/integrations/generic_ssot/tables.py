"""Tables for Generic SSoT Integration."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ToggleColumn

from .models import (
    SSOTEndpoint,
    SSOTEndpointJoin,
    SSOTFieldMapping,
    SSOTSyncConfig,
    SSOTSyncConfigEndpoint,
)


class SSOTEndpointTable(BaseTable):
    """Table for SSoT Endpoints."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    integration = tables.Column()
    api_path = tables.Column()
    data_path = tables.Column()
    weight = tables.Column()

    class Meta(BaseTable.Meta):
        """Meta class."""

        model = SSOTEndpoint
        fields = ("pk", "name", "integration", "api_path", "data_path", "http_method_read", "pagination_type", "weight")
        default_columns = ("pk", "name", "integration", "api_path", "data_path", "weight")


class SSOTSyncConfigTable(BaseTable):
    """Table for SSOTSyncConfig."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    sync_direction = tables.Column()
    enabled = tables.BooleanColumn()
    delete_unmatched = tables.BooleanColumn(verbose_name="Delete Unmatched")

    class Meta(BaseTable.Meta):
        """Meta class."""

        model = SSOTSyncConfig
        fields = (
            "pk",
            "name",
            "description",
            "sync_direction",
            "enabled",
            "dry_run_default",
            "delete_unmatched",
        )
        default_columns = ("pk", "name", "sync_direction", "enabled", "delete_unmatched")


class SSOTSyncConfigEndpointTable(BaseTable):
    """Table for Sync Config Endpoints (through model)."""

    pk = ToggleColumn()
    endpoint = tables.LinkColumn()
    weight = tables.Column()

    class Meta(BaseTable.Meta):
        """Meta class."""

        model = SSOTSyncConfigEndpoint
        fields = ("pk", "sync_config", "endpoint", "weight")
        default_columns = ("pk", "endpoint", "weight")


class SSOTEndpointJoinTable(BaseTable):
    """Table for SSoT Endpoint Joins."""

    pk = ToggleColumn()
    source_endpoint = tables.LinkColumn()
    source_key = tables.Column()
    target_endpoint = tables.LinkColumn()
    target_key = tables.Column()
    join_type = tables.Column()

    class Meta(BaseTable.Meta):
        """Meta class."""

        model = SSOTEndpointJoin
        fields = ("pk", "sync_config", "source_endpoint", "source_key", "target_endpoint", "target_key", "join_type")
        default_columns = ("pk", "source_endpoint", "source_key", "target_endpoint", "target_key", "join_type")


class SSOTFieldMappingTable(BaseTable):
    """Table for SSOTFieldMapping."""

    pk = ToggleColumn()
    sync_config = tables.LinkColumn()
    endpoint = tables.LinkColumn()
    source_field = tables.Column()
    nautobot_field = tables.Column()
    is_identifier = tables.BooleanColumn()
    enabled = tables.BooleanColumn()

    class Meta(BaseTable.Meta):
        """Meta class."""

        model = SSOTFieldMapping
        fields = (
            "pk",
            "sync_config",
            "endpoint",
            "nautobot_content_type",
            "source_field",
            "nautobot_field",
            "is_identifier",
            "is_required",
            "transformation_type",
            "enabled",
        )
        default_columns = (
            "pk",
            "sync_config",
            "endpoint",
            "source_field",
            "nautobot_field",
            "is_identifier",
            "enabled",
        )
