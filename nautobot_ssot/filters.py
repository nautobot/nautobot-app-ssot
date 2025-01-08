"""Filtering for nautobot_ssot."""

from nautobot.apps.filters import NautobotFilterSet, SearchFilter

from nautobot_ssot import models


class SyncFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for Sync."""

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

    class Meta:
        """Metaclass attributes of SyncLogEntryFilter."""

        model = models.SyncLogEntry
        fields = ["sync", "action", "status", "synced_object_type"]  # pylint: disable=nb-use-fields-all
