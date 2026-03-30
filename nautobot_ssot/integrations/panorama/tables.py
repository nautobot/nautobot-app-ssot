"""Plugin tables."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

from nautobot_ssot.integrations.panorama.models import LogicalGroup, VirtualSystem


class VirtualSystemTable(BaseTable):
    """Table for list view of `VirtualSystem` objects."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    actions = ButtonsColumn(VirtualSystem)
    system_id = tables.Column(verbose_name="System ID")
    device = tables.LinkColumn()
    interfaces = tables.ManyToManyColumn(linkify_item=True)

    class Meta(BaseTable.Meta):  # pylint: disable=too-few-public-methods
        """Meta class."""

        model = VirtualSystem
        fields = ["pk", "name", "system_id", "device", "interfaces"]  # pylint: disable=nb-use-fields-all


class LogicalGroupTable(BaseTable):
    """Table for list view of `LogicalGroup` objects."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    actions = ButtonsColumn(LogicalGroup)
    parent = tables.LinkColumn()
    devices = tables.ManyToManyColumn(linkify_item=True)
    virtual_systems = tables.ManyToManyColumn(linkify_item=True)

    class Meta(BaseTable.Meta):  # pylint: disable=too-few-public-methods
        """Meta class."""

        model = LogicalGroup
        fields = ["pk", "name", "parent", "devices", "virtual_systems"]  # pylint: disable=nb-use-fields-all
