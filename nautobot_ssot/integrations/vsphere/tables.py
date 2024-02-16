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
            "job_enabled",
        )
