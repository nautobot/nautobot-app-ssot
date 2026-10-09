"""Filtering implementation for SSOT Proxmox VE."""

import django_filters
from django.db.models import Q
from nautobot.apps.filters import NautobotFilterSet

from .models import SSOTProxmoxConfig


class SSOTProxmoxConfigFilterSet(NautobotFilterSet):
    """FilterSet for SSOTProxmoxConfig model."""

    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        """Meta attributes for filter."""

        model = SSOTProxmoxConfig

        fields = "__all__"

    def search(self, queryset, _name, value):
        """Filter SSOTProxmoxConfig records by name.

        Args:
            queryset (QuerySet): The queryset to filter.
            _name (str): The filter field name (unused).
            value (str): The search string.

        Returns:
            QuerySet: The filtered queryset.
        """
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value))  # pylint: disable=unsupported-binary-operation
