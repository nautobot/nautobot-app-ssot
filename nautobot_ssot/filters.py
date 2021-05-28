"""Filtering logic for Sync and SyncLogEntry records."""

import django_filters
from django.db.models import Q

from nautobot.utilities.filters import BaseFilterSet

from .models import Sync, SyncLogEntry


class SyncFilter(BaseFilterSet):
    """Filter capabilities for SyncOverview instances."""

    class Meta:
        model = Sync
        fields = ["dry_run", "job_result"]


class SyncLogEntryFilter(BaseFilterSet):
    """Filter capabilities for SyncLogEntry instances."""

    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        model = SyncLogEntry
        fields = ["sync", "action", "status", "changed_object_type"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(diff__icontains=value) | Q(message_icontains=value))
