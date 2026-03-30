"""Plugin filters."""

from nautobot.apps.filters import NautobotFilterSet, SearchFilter

from nautobot_ssot.integrations.panorama.models import LogicalGroup, VirtualSystem


class VirtualSystemFilterSet(NautobotFilterSet):
    """API filter for filtering VirtualSystem objects."""

    q = SearchFilter(
        filter_predicates={
            "name": "icontains",
            "system_id": "icontains",
            "device__name": "icontains",
            "device__serial": "icontains",
        },
    )

    class Meta:
        """Meta class."""

        model = VirtualSystem
        fields = [  # pylint: disable=nb-use-fields-all
            "name",
            "system_id",
            "device",
        ]


class LogicalGroupFilterSet(NautobotFilterSet):
    """API filter for filtering LogicalGroup objects."""

    q = SearchFilter(
        filter_predicates={
            "name": "icontains",
        },
    )

    class Meta:
        """Meta class."""

        model = LogicalGroup
        fields = ["name", "parent", "children"]  # pylint: disable=nb-use-fields-all
