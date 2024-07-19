"""Tables implementation for SSOT Infoblox."""

import django_tables2 as tables

from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn

from .models import SSOTInfobloxConfig


class SSOTInfobloxConfigTable(BaseTable):
    """Table for SSOTInfobloxConfig."""

    name = tables.LinkColumn()
    infoblox_url = tables.Column(accessor="infoblox_instance__remote_url")
    enable_sync_to_infoblox = BooleanColumn(orderable=False)
    enable_sync_to_nautobot = BooleanColumn(orderable=False)
    import_subnets = BooleanColumn(orderable=False)
    import_ip_addresses = BooleanColumn(orderable=False)
    import_vlan_views = BooleanColumn(orderable=False)
    import_vlans = BooleanColumn(orderable=False)
    import_ipv4 = BooleanColumn(orderable=False)
    import_ipv6 = BooleanColumn(orderable=False)
    job_enabled = BooleanColumn(orderable=False)
    actions = ButtonsColumn(SSOTInfobloxConfig, buttons=("changelog", "edit", "delete"))

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = SSOTInfobloxConfig
        fields = (  # pylint: disable=nb-use-fields-all
            "name",
            "infoblox_url",
            "enable_sync_to_infoblox",
            "import_subnets",
            "import_ip_addresses",
            "import_vlan_views",
            "import_vlans",
            "import_ipv4",
            "import_ipv6",
            "job_enabled",
        )
