"""Filtering logic for Sync and SyncLogEntry records."""

import django_filters
from django.db.models import Q

from nautobot.utilities.filters import BaseFilterSet

from .models import Sync, SyncLogEntry


class SyncFilter(BaseFilterSet):
    """Filter capabilities for SyncOverview instances."""

    class Meta:
        """Metaclass attributes of SyncFilter."""

        model = Sync
        fields = ["dry_run", "job_result"]


class SyncLogEntryFilter(BaseFilterSet):
    """Filter capabilities for SyncLogEntry instances."""

    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        """Metaclass attributes of SyncLogEntryFilter."""

        model = SyncLogEntry
        fields = ["sync", "action", "status", "synced_object_type"]

    def search(self, queryset, _name, value):  # pylint: disable=no-self-use
        """String search of SyncLogEntry records."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(diff__icontains=value) | Q(message__icontains=value))
