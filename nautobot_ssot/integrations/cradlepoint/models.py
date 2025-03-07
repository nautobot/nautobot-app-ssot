"""Models implemntation for SSoT Cradlepoint Integration."""
from nautobot.core.models.generics import PrimaryModel
from django.db import models

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255


class SSOTCradlepointConfig(PrimaryModel):
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
    is_saved_view_model = False

    class Meta:
        """Meta class for SSOTCradlepointConfig."""

        verbose_name = "SSoT Cradlepoint Config"
        verbose_name_plural = "SSoT Cradlepoint Configs"

    def __str__(self):
        """String representation of singleton instance."""
        return self.name
