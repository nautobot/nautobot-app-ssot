"""Filters for OpenShift integration."""
import django_filters
from django.db import models
from nautobot.core.filters import BaseFilterSet
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigFilterSet(BaseFilterSet):
    """Filter set for SSOTOpenshiftConfig."""
    
    q = django_filters.CharFilter(
        method="search",
        label="Search",
    )
    
    name = django_filters.CharFilter(
        lookup_expr="icontains",
    )
    
    url = django_filters.CharFilter(
        lookup_expr="icontains",
    )
    
    verify_ssl = django_filters.BooleanFilter()
    
    class Meta:
        """Meta class for filter set."""
        model = SSOTOpenshiftConfig
        fields = [
            "name",
            "url",
            "verify_ssl",
            "sync_namespaces",
            "sync_nodes",
            "sync_containers",
            "sync_deployments",
            "sync_services",
            "sync_kubevirt_vms",
            "workload_types",
        ]
    
    def search(self, queryset, name, value):
        """Search method."""
        if not value.strip():
            return queryset
        return queryset.filter(
            models.Q(name__icontains=value) |
            models.Q(description__icontains=value) |
            models.Q(url__icontains=value)
        )
