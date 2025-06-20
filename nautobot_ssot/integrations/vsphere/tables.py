"""Tables implementation for SSOT vSphere."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn

from .models import SSOTvSphereConfig


class SSOTvSphereConfigTable(BaseTable):
    """Table for SSOTvSphereConfig."""

    name = tables.LinkColumn()
    vsphere_url = tables.Column(accessor="vsphere_instance__remote_url")
    enable_sync_to_nautobot = BooleanColumn(orderable=False)
    default_ignore_link_local = BooleanColumn(orderable=False)
    job_enabled = BooleanColumn(orderable=False)
    actions = ButtonsColumn(SSOTvSphereConfig, buttons=("changelog", "edit", "delete"))

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = SSOTvSphereConfig
        fields = (  # pylint: disable=nb-use-fields-all
            "name",
            "vsphere_url",
            "enable_sync_to_nautobot",
            "default_ignore_link_local",
            "job_enabled",
            "default_clustergroup_name",
            "default_cluster_name",
            "default_cluster_type",
            "default_vm_status_map",
        )
        default_columns = (
            "name",
            "vsphere_url",
            "enable_sync_to_nautobot",
            "default_ignore_link_local",
            "job_enabled",
            "default_clustergroup_name",
            "default_cluster_name",
            "default_cluster_type",
        )
