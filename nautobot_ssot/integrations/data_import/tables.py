"""Tables for the Data Import integration."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ToggleColumn

from nautobot_ssot.integrations.data_import.models import ImportPlan


class ImportPlanTable(BaseTable):
    """List table for Import Plans."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    integration = tables.Column()
    enabled = tables.BooleanColumn()

    class Meta(BaseTable.Meta):
        """Meta class."""

        model = ImportPlan
        fields = ("pk", "name", "description", "integration", "enabled", "last_updated")
        default_columns = ("pk", "name", "description", "integration", "enabled")
