"""Models for the Data Import integration."""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255

from nautobot.core.models.generics import PrimaryModel

# Reject CSV uploads larger than this many bytes (per source).
MAX_CSV_BYTES = 5 * 1024 * 1024
# Cap the number of sample rows cached per table for the builder preview.
MAX_CACHED_ROWS = 50


class ImportPlan(PrimaryModel):
    """A saved, re-runnable configuration for importing external data into Nautobot.

    The entire import definition (sources, tables, output mappings, defaults)
    lives in ``document`` — see the engine package for the schema. The model
    row is just the envelope plus cached sample data for the builder UI.
    """

    is_saved_view_model = False

    clone_fields = ["description", "integration", "document", "enabled"]

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    description = models.TextField(blank=True)

    integration = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_import_plans",
        help_text="External Integration providing base URL and auth for API sources. Not needed for CSV-only plans.",
    )

    document = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="The full import definition: sources, tables, outputs, defaults.",
    )

    cached_tables = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Sample data per table id for the builder preview: {table_id: {columns, rows, row_count}}.",
    )

    csv_data = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Raw CSV text keyed by source id for csv-type sources.",
    )

    enabled = models.BooleanField(default=True)

    class Meta:
        """Meta class for ImportPlan."""

        app_label = "nautobot_ssot"
        ordering = ["name"]
        verbose_name = "Import Plan"
        verbose_name_plural = "Import Plans"

    def __str__(self):
        """String representation."""
        return self.name
