"""Filtering implementation for Generic SSoT Integration."""

import django_filters
from django.db.models import Q
from nautobot.apps.filters import BaseFilterSet, NautobotFilterSet, SearchFilter

from .models import (
    SSOTDataSample,
    SSOTEndpoint,
    SSOTEndpointJoin,
    SSOTFieldMapping,
    SSOTSyncConfig,
    SSOTSyncConfigEndpoint,
    SSOTValueMap,
)


class SSOTEndpointFilterSet(BaseFilterSet):
    """FilterSet for SSOTEndpoint model."""

    q = SearchFilter(filter_predicates={"name": "icontains", "api_path": "icontains"})

    class Meta:
        """Meta attributes for filter."""

        model = SSOTEndpoint
        fields = ["name", "integration", "pagination_type"]


class SSOTSyncConfigFilterSet(BaseFilterSet):
    """FilterSet for SSOTSyncConfig model."""

    q = SearchFilter(filter_predicates={"name": "icontains", "description": "icontains"})

    class Meta:
        """Meta attributes for filter."""

        model = SSOTSyncConfig
        fields = ["name", "sync_direction", "enabled", "delete_unmatched"]


class SSOTSyncConfigEndpointFilterSet(NautobotFilterSet):
    """FilterSet for SSOTSyncConfigEndpoint model."""

    sync_config = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTSyncConfig.objects.all(),
        label="Sync Config",
    )
    endpoint = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTEndpoint.objects.all(),
        label="Endpoint",
    )

    class Meta:
        """Meta attributes for filter."""

        model = SSOTSyncConfigEndpoint
        fields = ["sync_config", "endpoint"]


class SSOTFieldMappingFilterSet(NautobotFilterSet):
    """FilterSet for SSOTFieldMapping model."""

    q = django_filters.CharFilter(method="search", label="Search")
    sync_config = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTSyncConfig.objects.all(),
        label="Sync Config",
    )
    endpoint = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTEndpoint.objects.all(),
        label="Endpoint",
    )

    class Meta:
        """Meta attributes for filter."""

        model = SSOTFieldMapping
        fields = "__all__"

    def search(self, queryset, _name, value):
        """String search of SSOTFieldMapping records."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(source_field__icontains=value) | Q(nautobot_field__icontains=value))


class SSOTEndpointJoinFilterSet(NautobotFilterSet):
    """FilterSet for SSOTEndpointJoin model."""

    sync_config = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTSyncConfig.objects.all(),
        label="Sync Config",
    )
    source_endpoint = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTEndpoint.objects.all(),
        label="Source Endpoint",
    )
    target_endpoint = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTEndpoint.objects.all(),
        label="Target Endpoint",
    )

    class Meta:
        """Meta attributes for filter."""

        model = SSOTEndpointJoin
        fields = ["sync_config", "source_endpoint", "target_endpoint", "join_type"]


class SSOTValueMapFilterSet(NautobotFilterSet):
    """FilterSet for SSOTValueMap model."""

    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        """Meta attributes for filter."""

        model = SSOTValueMap
        fields = "__all__"

    def search(self, queryset, _name, value):
        """String search of SSOTValueMap records."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class SSOTDataSampleFilterSet(NautobotFilterSet):
    """FilterSet for SSOTDataSample model."""

    endpoint = django_filters.ModelMultipleChoiceFilter(
        queryset=SSOTEndpoint.objects.all(),
        label="Endpoint",
    )

    class Meta:
        """Meta attributes for filter."""

        model = SSOTDataSample
        fields = "__all__"
