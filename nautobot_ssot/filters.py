"""Filtering logic for Sync and SyncLogEntry records."""

from django_filters import ModelMultipleChoiceFilter
from nautobot.apps.filters import BaseFilterSet, NautobotFilterSet, SearchFilter

from nautobot_ssot import models
from nautobot_ssot.integrations.infoblox.filters import SSOTInfobloxConfigFilterSet
from nautobot_ssot.integrations.itential.filters import AutomationGatewayModelFilterSet


class SyncFilterSet(BaseFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for Sync."""

    q = SearchFilter(
        filter_predicates={
            "source": "icontains",
            "target": "icontains",
            "diff": "icontains",
        }
    )

    class Meta:
        """Meta attributes for filter."""

        model = models.Sync

        # add any fields from the model that you would like to filter your searches by using those
        fields = ["dry_run", "job_result"]  # pylint: disable=nb-use-fields-all


class SyncLogEntryFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """Filter capabilities for SyncLogEntry instances."""

    q = SearchFilter(
        filter_predicates={
            "diff": "icontains",
            "message": "icontains",
            "object_repr": "icontains",
        }
    )

    sync = ModelMultipleChoiceFilter(
        queryset=models.Sync.objects.all(),
        label="Sync (name or ID)",
    )

    class Meta:
        """Metaclass attributes of SyncLogEntryFilter."""

        model = models.SyncLogEntry
        fields = ["sync", "action", "status", "synced_object_type"]  # pylint: disable=nb-use-fields-all


__all__ = (
    "AutomationGatewayModelFilterSet",
    "SSOTInfobloxConfigFilterSet",
    "SyncFilterSet",
    "SyncLogEntryFilterSet",
)
