"""Tables implementation for SSOT Proxmox VE."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn

from .models import SSOTProxmoxConfig


class SSOTProxmoxConfigTable(BaseTable):
    """Table for SSOTProxmoxConfig."""

    name = tables.LinkColumn()
    proxmox_url = tables.Column(accessor="proxmox_instance__remote_url")
    enable_sync_to_nautobot = BooleanColumn(orderable=False)
    sync_lxc = BooleanColumn(orderable=False)
    sync_nodes_as_devices = BooleanColumn(orderable=False)
    job_enabled = BooleanColumn(orderable=False)
    actions = ButtonsColumn(SSOTProxmoxConfig, buttons=("changelog", "edit", "delete"))

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = SSOTProxmoxConfig
        fields = (  # pylint: disable=nb-use-fields-all
            "name",
            "proxmox_url",
            "enable_sync_to_nautobot",
            "sync_lxc",
            "sync_nodes_as_devices",
            "job_enabled",
            "default_clustergroup_name",
            "default_cluster_name",
            "default_cluster_type",
        )
        default_columns = (
            "name",
            "proxmox_url",
            "enable_sync_to_nautobot",
            "sync_lxc",
            "sync_nodes_as_devices",
            "job_enabled",
            "default_cluster_name",
        )
