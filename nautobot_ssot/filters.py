"""Filtering logic for Sync and SyncLogEntry records."""

from nautobot.apps.filters import NameSearchFilterSet, NautobotFilterSet, SearchFilter

from nautobot_ssot import models
from nautobot_ssot.integrations.infoblox.filters import SSOTInfobloxConfigFilterSet
from nautobot_ssot.integrations.itential.filters import AutomationGatewayModelFilterSet


class SyncFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
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


class SyncRecordFilterSet(NameSearchFilterSet, NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for SyncRecord."""

    q = SearchFilter(
        filter_predicates={
            "source": "icontains",
            "target": "icontains",
            "obj_type": "icontains",
            "obj_name": "icontains",
            "action": "icontains",
            "status": "icontains",
        }
    )

    class Meta:
        """Meta attributes for filter."""

        model = models.SyncRecord

        # add any fields from the model that you would like to filter your searches by using those
        fields = [
            "sync",
            "source",
            "target",
            "obj_type",
            "obj_name",
            "action",
            "status",
        ]


__all__ = (
    "AutomationGatewayModelFilterSet",
    "SSOTInfobloxConfigFilterSet",
    "SyncFilterSet",
    "SyncLogEntryFilterSet",
    "SyncRecordFilterSet",
)
