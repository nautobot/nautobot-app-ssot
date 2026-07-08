#  pylint: disable=duplicate-code

"""Models implementation for SSOT Proxmox VE."""

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255

from nautobot.core.models.generics import PrimaryModel
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import SecretsGroupAssociation
from nautobot.extras.models.statuses import Status

from nautobot_ssot.integrations.proxmox.choices import PrimaryIpSortByChoices
from nautobot_ssot.integrations.proxmox.constants import NODE_INTERFACE_TYPE_MAP


def _get_default_vm_status_map():
    """Provide default value for SSOTProxmoxConfig default_vm_status_map field.

    Keys are Proxmox VE resource statuses (``/cluster/resources``), values are Nautobot Status names.
    """
    return {"running": "Active", "stopped": "Offline", "paused": "Suspended"}


def _get_default_ip_status_map():
    """Provide default value for SSOTProxmoxConfig default_ip_status_map field."""
    return {"PREFERRED": "Active", "UNKNOWN": "Reserved"}


def _get_default_node_interface_type_map():
    """Provide default value for SSOTProxmoxConfig default_node_interface_type_map field.

    Keys are Proxmox VE node interface types (``/nodes/{node}/network``), values are Nautobot DCIM
    interface type slugs.
    """
    return dict(NODE_INTERFACE_TYPE_MAP)


class SSOTProxmoxConfig(PrimaryModel):  # pylint: disable=too-many-ancestors
    """SSOT Proxmox VE Configuration model."""

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    description = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        blank=True,
    )
    proxmox_instance = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.PROTECT,
        verbose_name="Proxmox VE Instance Config",
        help_text="Proxmox VE Instance",
    )
    enable_sync_to_nautobot = models.BooleanField(
        default=True,
        verbose_name="Sync to Nautobot",
        help_text="Enable syncing of data from Proxmox VE to Nautobot.",
    )
    use_clusters = models.BooleanField(
        default=True,
        verbose_name="Use Clusters",
        help_text="Enable use of Clusters. If set to False, all Virtual Machines will be placed in the default cluster.",
    )
    sync_lxc = models.BooleanField(
        default=True,
        verbose_name="Sync LXC Containers",
        help_text="Enable syncing of LXC containers as Virtual Machines (in addition to QEMU VMs).",
    )
    sync_nodes_as_devices = models.BooleanField(
        default=True,
        verbose_name="Sync Nodes as Devices",
        help_text="Model Proxmox VE nodes as Nautobot Devices and link Virtual Machines to their host.",
    )
    sync_proxmox_tags = models.BooleanField(
        default=True,
        verbose_name="Sync Proxmox VE Tags",
        help_text="Enable syncing of Proxmox VE tags on VMs to Nautobot VMs as Tags.",
    )
    default_ssot_tag = models.ForeignKey(
        to="extras.Tag",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="SSoT Tag",
        help_text="Tag applied to every object synced from Proxmox VE, for visibility in the "
        "Nautobot UI. Purely cosmetic — this integration identifies which objects it manages via "
        "the 'last_synced_from_proxmox_on' custom field, not this tag. If another integration "
        "deletes this tag, the next Proxmox VE sync recreates it automatically.",
    )
    default_vm_status_map = models.JSONField(default=_get_default_vm_status_map, encoder=DjangoJSONEncoder)
    default_ip_status_map = models.JSONField(default=_get_default_ip_status_map, encoder=DjangoJSONEncoder, blank=True)
    default_node_interface_type_map = models.JSONField(
        default=_get_default_node_interface_type_map, encoder=DjangoJSONEncoder, blank=True
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
        help_text="Determine whether link-local (and APIPA) addresses on Virtual Machine interfaces should be ignored.",
    )
    job_enabled = models.BooleanField(
        default=False,
        verbose_name="Enabled for Sync Job",
        help_text="Enable use of this configuration in the sync jobs.",
    )
    default_clustergroup_name = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        verbose_name="Default Cluster Group Name",
        default="Proxmox VE Default Cluster Group",
    )
    default_cluster_name = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH, verbose_name="Default Cluster Name", default="Proxmox VE Default Cluster"
    )
    default_cluster_type = models.ForeignKey(
        to="virtualization.ClusterType",
        on_delete=models.PROTECT,
        verbose_name="Default Cluster Type",
    )
    default_location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.PROTECT,
        verbose_name="Default Location",
        help_text="Location assigned to Devices created for Proxmox VE nodes.",
    )
    default_device_type = models.ForeignKey(
        to="dcim.DeviceType",
        on_delete=models.PROTECT,
        verbose_name="Default Node Device Type",
        help_text="DeviceType assigned to Devices created for Proxmox VE nodes.",
    )
    default_device_role = models.ForeignKey(
        to="extras.Role",
        on_delete=models.PROTECT,
        verbose_name="Default Node Device Role",
        help_text="Role assigned to Devices created for Proxmox VE nodes.",
    )
    is_saved_view_model = False
    is_dynamic_group_associable_model = False
    is_metadata_associable_model = False
    is_contact_associable_model = False
    is_data_compliance_model = False

    class Meta:
        """Meta class for SSOTProxmoxConfig."""

        verbose_name = "SSOT Proxmox VE Config"
        verbose_name_plural = "SSOT Proxmox VE Configs"

    def __str__(self):
        """String representation of singleton instance."""
        return self.name

    def _clean_default_vm_status_map(self):
        """Perform validation of the default_vm_status_map field."""
        if not isinstance(self.default_vm_status_map, dict):
            raise ValidationError({"default_vm_status_map": "Virtual Machine status map must be a dict."})

        if not self.default_vm_status_map:
            raise ValidationError({"default_vm_status_map": "Virtual Machine status map must not be empty."})

        for key, value in self.default_vm_status_map.items():
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

    def _clean_default_node_interface_type_map(self):
        """Perform validation of the default_node_interface_type_map field."""
        # An empty value is allowed; the sync falls back to the built-in default map.
        if not self.default_node_interface_type_map:
            return

        if not isinstance(self.default_node_interface_type_map, dict):
            raise ValidationError({"default_node_interface_type_map": "Node interface type map must be a dict."})

        allowed_keys = set(NODE_INTERFACE_TYPE_MAP)
        valid_types = set(InterfaceTypeChoices.values())
        for key, value in self.default_node_interface_type_map.items():
            if key not in allowed_keys:
                raise ValidationError(
                    {
                        "default_node_interface_type_map": f"Unknown Proxmox interface type '{key}'. "
                        f"Allowed keys: {', '.join(sorted(allowed_keys))}."
                    }
                )
            if value not in valid_types:
                raise ValidationError(
                    {"default_node_interface_type_map": f"'{value}' is not a valid Nautobot interface type."}
                )

    def _clean_proxmox_instance(self):
        """Perform validation of the proxmox_instance field.

        The SecretsGroup must provide a REST Token ID (stored as the username secret, in the form
        ``user@realm!tokenid``) and a REST Token Secret (stored as the secret/token secret).
        """
        if not self.proxmox_instance.secrets_group:
            raise ValidationError({"proxmox_instance": "Proxmox VE instance must have Secrets group assigned."})
        try:
            self.proxmox_instance.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            )
        except SecretsGroupAssociation.DoesNotExist:
            raise ValidationError(  # pylint: disable=raise-missing-from
                {
                    "proxmox_instance": "Secrets group for the Proxmox VE instance must have a secret with type "
                    "Username and access type REST holding the API Token ID (user@realm!tokenid)."
                }
            )
        try:
            self.proxmox_instance.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
            )
        except SecretsGroupAssociation.DoesNotExist:
            raise ValidationError(  # pylint: disable=raise-missing-from
                {
                    "proxmox_instance": "Secrets group for the Proxmox VE instance must have a secret with type "
                    "Token and access type REST holding the API Token Secret."
                }
            )

    def clean(self):
        """Clean method for SSOTProxmoxConfig."""
        super().clean()
        self._clean_proxmox_instance()
        self._clean_default_vm_status_map()
        self._clean_default_ip_status_map()
        self._clean_default_node_interface_type_map()
