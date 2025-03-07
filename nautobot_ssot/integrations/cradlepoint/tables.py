"""Tables implementation for SSOT Cradlepoint."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn

from .models import SSOTCradlepointConfig


class SSOTCradlepointConfigTable(BaseTable):
    """Table for SSOTCradlepointConfig."""

    name = tables.LinkColumn()
    cradlepoint_url = tables.Column(accessor="cradlepoint_instance__remote_url")
    enable_sync_to_nautobot = BooleanColumn(orderable=False)
    job_enabled = BooleanColumn(orderable=False)
    actions = ButtonsColumn(
        SSOTCradlepointConfig, buttons=("changelog", "edit", "delete")
    )

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = SSOTCradlepointConfig
        fields = (  # pylint: disable=nb-use-fields-all
            "name",
            "cradlepoint_url",
            "job_enabled",
        )
