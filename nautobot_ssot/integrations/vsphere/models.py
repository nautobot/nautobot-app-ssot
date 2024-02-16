"""MOdels implementation for SSOT vSphere."""

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255

from nautobot.core.models.generics import PrimaryModel
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import SecretsGroupAssociation
from nautobot.extras.models.statuses import Status

from nautobot_ssot.integrations.vsphere.choices import PrimaryIpSortByChoices


def _get_default_vm_status_map():
    """Provides default value for SSOTvSphereConfig default_vm_status_map field."""
    return {"POWERED_OFF": "Offline", "POWERED_ON": "Active", "SUSPENDED": "Suspended"}


def _get_default_ip_status_map():
    """Provides default value for SSOTvSphereConfig default_ip_status_map field."""
    return {"PREFERRED": "Active", "UNKNOWN": "Reserved"}


def _get_default_vm_interface_map():
    """Provides default value for SSOTvSphereConfig default_vm_interface_map field."""
    return {"NOT_CONNECTED": False, "CONNECTED": True}


class SSOTvSphereConfig(PrimaryModel):  # pylint: disable=too-many-ancestors
    """SSOT vSphere Configuration model."""

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    description = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        blank=True,
    )
    vsphere_instance = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.PROTECT,
        verbose_name="vSphere Instance Config",
        help_text="vSphere Instance",
    )
    enable_sync_to_nautobot = models.BooleanField(
        default=True,
        verbose_name="Sync to Nautobot",
        help_text="Enable syncing of data from vSphere to Nautobot.",
    )
    default_vm_status_map = models.JSONField(default=_get_default_vm_status_map, encoder=DjangoJSONEncoder)
    default_ip_status_map = models.JSONField(default=_get_default_ip_status_map, encoder=DjangoJSONEncoder, blank=True)
    default_vm_interface_map = models.JSONField(
        default=_get_default_vm_interface_map, encoder=DjangoJSONEncoder, blank=True
    )
    primary_ip_sort_by = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        default=PrimaryIpSortByChoices.LOWEST,
        choices=PrimaryIpSortByChoices,
        verbose_name="Primary IP Sort Logic",
        help_text="Choose what logic to use to determine Virtual Machine primary IP.",
    )
    default_ignore_link_local = models.BooleanField(
        default=True,
        verbose_name="Ignore Link Local",
        help_text="Determine whether link-local addresses on Virtual Machine interfaces should be ignored.",
    )
    job_enabled = models.BooleanField(
        default=False,
        verbose_name="Enabled for Sync Job",
        help_text="Enable use of this configuration in the sync jobs.",
    )

    class Meta:
        """Meta class for SSOTvSphereConfig."""

        verbose_name = "SSOT vSphere Config"
        verbose_name_plural = "SSOT vSphere Configs"

    def __str__(self):
        """String representation of singleton instance."""
        return self.name

    def _clean_default_vm_status_map(self):
        """Perform validation of the default_vm_status_map field."""
        allowed_keys = {"POWERED_OFF", "POWERED_ON", "SUSPENDED"}

        if not isinstance(self.default_vm_status_map, dict):
            raise ValidationError({"default_vm_status_map": "Virtual Machine status map must be a dict."})

        invalid_keys = set(self.default_vm_status_map.keys()) - allowed_keys
        if invalid_keys:
            raise ValidationError(
                {"default_vm_status_map": f"Invalid keys found in the VM status map: {', '.join(invalid_keys)}."}
            )

        for key in allowed_keys:
            if key not in self.default_vm_status_map:
                raise ValidationError(
                    {"default_vm_status_map": f"Virtual Machine Status map must have '{key}' key defined."}
                )

            value = self.default_vm_status_map[key]
            if not isinstance(value, str):
                raise ValidationError({"default_vm_status_map": f"Value of '{key}' must be a string."})

            try:
                Status.objects.get(name=value)
            except Status.DoesNotExist:
                raise ValidationError(  # pylint: disable=raise-missing-from
                    {"default_vm_status_map": f"No existing status found for '{value}'."}
                )

    def _clean_default_ip_status_map(self):
        """Perform validation of the default_ip_status_map field."""
        allowed_keys = {"PREFERRED", "UNKNOWN"}

        if not isinstance(self.default_ip_status_map, dict):
            raise ValidationError({"default_ip_status_map": "IP status map must be a dict."})

        invalid_keys = set(self.default_ip_status_map.keys()) - allowed_keys
        if invalid_keys:
            raise ValidationError(
                {"default_ip_status_map": f"Invalid keys found in the IP status map: {', '.join(invalid_keys)}."}
            )

        for key in allowed_keys:
            if key not in self.default_ip_status_map:
                raise ValidationError({"default_ip_status_map": f"IP status map must have '{key}' key defined."})

            value = self.default_ip_status_map[key]
            if not isinstance(value, str):
                raise ValidationError({"default_ip_status_map": f"Value of '{key}' must be a string."})

            try:
                Status.objects.get(name=value)
            except Status.DoesNotExist:
                raise ValidationError(  # pylint: disable=raise-missing-from
                    {"default_ip_status_map": f"No existing status found for {value}."}
                )

    def _clean_default_vm_interface_map(self):
        """Perform validation of the default_vm_interface_map field."""
        allowed_keys = {"CONNECTED", "NOT_CONNECTED"}

        if not isinstance(self.default_vm_interface_map, dict):
            raise ValidationError({"default_vm_interface_map": "Interface map must be a dict."})

        invalid_keys = set(self.default_vm_interface_map.keys()) - allowed_keys
        if invalid_keys:
            raise ValidationError(
                {"default_vm_interface_map": f"Invalid keys found in the Interface map: {', '.join(invalid_keys)}."}
            )

        for key in allowed_keys:
            if key not in self.default_vm_interface_map:
                raise ValidationError({"default_vm_interface_map": f"Interface map must have '{key}' key defined."})

            value = self.default_vm_interface_map[key]
            if not isinstance(value, bool):
                raise ValidationError({"default_vm_interface_map": f"Value of '{key}' must be a boolean."})

    def _clean_vsphere_instance(self):
        """Performs validation of the vsphere_instance field."""
        if not self.vsphere_instance.secrets_group:
            raise ValidationError({"vsphere_instance": "vSphere instance must have Secrets groups assigned."})
        try:
            self.vsphere_instance.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            )
        except SecretsGroupAssociation.DoesNotExist:
            raise ValidationError(  # pylint: disable=raise-missing-from
                {
                    "vsphere_instance": "Secrets group for the vSphere instance must have secret with type Username and access type REST."
                }
            )
        try:
            self.vsphere_instance.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            )
        except SecretsGroupAssociation.DoesNotExist:
            raise ValidationError(  # pylint: disable=raise-missing-from
                {
                    "vsphere_instance": "Secrets group for the vSphere instance must have secret with type Password and access type REST."
                }
            )

    def clean(self):
        """Clean method for SSOTvSphereConfig."""
        super().clean()
        self._clean_vsphere_instance()
        self._clean_default_vm_status_map()
        self._clean_default_ip_status_map()
        self._clean_default_vm_interface_map()
