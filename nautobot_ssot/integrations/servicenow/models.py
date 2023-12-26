"""Configuration data model for nautobot-ssot-servicenow."""

from django.db import models
from django.shortcuts import reverse

from nautobot.core.models import BaseModel


class SSOTServiceNowConfig(BaseModel):  # pylint: disable=nb-string-field-blank-null
    """Singleton data model describing the configuration of this app."""

    def delete(self, *args, **kwargs):
        """Cannot be deleted."""

    @classmethod
    def load(cls):
        """Singleton instance getter."""
        if cls.objects.all().exists():
            return cls.objects.first()
        return cls.objects.create()

    servicenow_instance = models.CharField(
        max_length=100,
        blank=True,
        help_text="ServiceNow instance name, will be used as <code>&lt;instance&gt;.servicenow.com</code>.",
    )

    servicenow_secrets = models.ForeignKey(
        to="extras.SecretsGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Secrets group for authentication to ServiceNow. Should contain a REST username and REST password.",
    )

    def __str__(self):
        """String representation of singleton instance."""
        return "SSoT ServiceNow Configuration"

    def get_absolute_url(self, api=False):  # pylint: disable=unused-argument
        """Get URL for the associated configuration view."""
        return reverse("plugins:nautobot_ssot:servicenow_config")
