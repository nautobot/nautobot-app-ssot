"""Filtering logic for Sync and SyncLogEntry records."""

from nautobot.apps.filters import BaseFilterSet, SearchFilter

from nautobot_ssot import models


class SyncFilterSet(NameSearchFilterSet, NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for Sync."""

    class Meta:
        """Meta attributes for filter."""

        model = models.Sync

        # add any fields from the model that you would like to filter your searches by using those
        fields = "__all__"
