"""Models implemntation for SSoT Cradlepoint Integration."""

from django.db import models
from django.core.exceptions import ValidationError
from nautobot.core.models.generics import PrimaryModel
from django.core.serializers.json import DjangoJSONEncoder

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255


def _default_unique_ordering():
    """Provides default value for cradlepoint uniqque ID selection."""
    return ["name", "serial_number", "mac", "id"]


class SSOTCradlepointConfig(PrimaryModel):  # pylint: disable=too-many-ancestors
    """SSOT Cradlepoint Config model."""

    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    cradlepoint_instance = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.PROTECT,
        verbose_name="Cradlepoint Instance Config",
        help_text="Cradlepoint Instance",
    )
    job_enabled = models.BooleanField(
        default=False,
        verbose_name="Enabled for Sync Job",
        help_text="Enable use of this configuration in the sync jobs.",
    )
    unique_cradlepoint_field_order = models.JSONField(
        default=_default_unique_ordering, encoder=DjangoJSONEncoder
    )
    is_saved_view_model = False

    class Meta:
        """Meta class for SSOTCradlepointConfig."""

        verbose_name = "SSoT Cradlepoint Config"
        verbose_name_plural = "SSoT Cradlepoint Configs"

    def __str__(self):
        """String representation of singleton instance."""
        return self.name

    def _clean_unique_cradlepoint_field_order(self):
        """Clean unique_cradlepoint_field_order."""
        allowed_items = ["name", "serial_number", "mac", "id"]

        if not isinstance(self.unique_cradlepoint_field_order, list):
            raise ValidationError(
                f"Ensure you are providing a list: {self.unique_cradlepoint_field_order}"
            )

        if set(self.unique_cradlepoint_field_order) != set(allowed_items):
            raise ValidationError(
                f" The field must contain name, id, mac, and serial_number. {self.unique_cradlepoint_field_order}"
            )
