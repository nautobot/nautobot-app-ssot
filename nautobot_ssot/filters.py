"""Filtering for nautobot_ssot."""

from nautobot.apps.filters import NameSearchFilterSet, NautobotFilterSet

from nautobot_ssot import models


class SyncFilterSet(NautobotFilterSet, NameSearchFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for Sync."""

    class Meta:
        """Meta attributes for filter."""

        model = models.Sync

        # add any fields from the model that you would like to filter your searches by using those
        fields = ["id", "name", "description"]
