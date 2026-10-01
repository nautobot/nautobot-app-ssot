"""Forms implementation for SSOT Proxmox VE."""

from django import forms
from nautobot.apps.forms import JSONField, StaticSelect2
from nautobot.dcim.models import DeviceType, Location
from nautobot.extras.forms import NautobotFilterForm, NautobotModelForm
from nautobot.extras.models import Role, SecretsGroup, Tag
from nautobot.virtualization.models import ClusterType

from .choices import PrimaryIpSortByChoices
from .constants import (
    CLUSTER_TYPE_NAME,
    NODE_DEVICE_ROLE_NAME,
    NODE_DEVICE_TYPE_NAME,
    NODE_LOCATION_NAME,
    SSOT_TAG_NAME,
)
from .models import SSOTProxmoxConfig


class SSOTProxmoxConfigForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """SSOTProxmoxConfig creation/edit form."""

    default_vm_status_map = JSONField(
        required=True,
        label="Virtual Machine Status Map",
        help_text="Maps Proxmox VE Virtual Machine statuses to Nautobot statuses.",
    )
    default_ip_status_map = JSONField(
        required=True,
        label="Virtual Machine IP Status Map",
        help_text="Maps Virtual Machine IP statuses to Nautobot statuses.",
    )
    default_node_interface_type_map = JSONField(
        required=False,
        label="Node Interface Type Map",
        help_text="Maps Proxmox VE node interface types (eth, bond, bridge, vlan, ...) to Nautobot interface types.",
    )
    primary_ip_sort_by = forms.ChoiceField(
        choices=PrimaryIpSortByChoices,
        required=True,
        label="Primary IP Sort Logic",
        widget=StaticSelect2(),
    )
    proxmox_secrets_group = forms.ModelChoiceField(
        queryset=SecretsGroup.objects.all(),
        required=True,
        label="Secrets Group",
        help_text="Existing Secrets Group holding the REST Username (Token ID) and REST Token "
        "(Token Secret) associations for the Proxmox VE instance.",
    )
    proxmox_remote_url = forms.CharField(
        required=True,
        label="Remote URL",
        help_text="Base URL of the Proxmox VE instance, e.g. https://pve.example.com:8006",
    )
    proxmox_verify_ssl = forms.BooleanField(
        required=False,
        label="Verify SSL",
        help_text="Verify the Proxmox VE instance's SSL certificate.",
    )
    proxmox_timeout = forms.IntegerField(
        required=False,
        initial=30,
        label="Timeout (seconds)",
        help_text="Request timeout, in seconds, for calls to the Proxmox VE instance.",
    )

    class Meta:
        """Meta attributes for the SSOTProxmoxConfigForm class."""

        model = SSOTProxmoxConfig
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """Populate the Proxmox instance pass-through fields from the related ExternalIntegration."""
        super().__init__(*args, **kwargs)
        instance = getattr(self.instance, "proxmox_instance", None)
        if instance:
            self.fields["proxmox_secrets_group"].initial = instance.secrets_group
            self.fields["proxmox_remote_url"].initial = instance.remote_url
            self.fields["proxmox_verify_ssl"].initial = instance.verify_ssl
            self.fields["proxmox_timeout"].initial = instance.timeout

        if self.instance._state.adding:  # pylint: disable=protected-access
            # The UUID pk is set at instantiation, so `pk` can't detect a new instance.
            # Prefill the defaults created by signals.py; .first() keeps the form rendering if one is missing.
            self.fields["default_ssot_tag"].initial = Tag.objects.filter(name=SSOT_TAG_NAME).first()
            self.fields["default_cluster_type"].initial = ClusterType.objects.filter(name=CLUSTER_TYPE_NAME).first()
            self.fields["default_location"].initial = Location.objects.filter(name=NODE_LOCATION_NAME).first()
            self.fields["default_device_type"].initial = DeviceType.objects.filter(model=NODE_DEVICE_TYPE_NAME).first()
            self.fields["default_device_role"].initial = Role.objects.filter(name=NODE_DEVICE_ROLE_NAME).first()

    def clean(self):
        """Apply the pass-through fields to the selected ExternalIntegration before model validation.

        Done here, not in save(), because full_clean() validates the integration's secrets group next.
        NautobotModelForm's super().clean() returns None, so ``self.cleaned_data`` is used instead.

        Returns:
            dict: The cleaned form data.
        """
        super().clean()
        integration = self.cleaned_data.get("proxmox_instance")
        if integration:
            integration.secrets_group = self.cleaned_data.get("proxmox_secrets_group")
            integration.remote_url = self.cleaned_data.get("proxmox_remote_url")
            integration.verify_ssl = self.cleaned_data.get("proxmox_verify_ssl")
            integration.timeout = self.cleaned_data.get("proxmox_timeout") or 30
        return self.cleaned_data

    def save(self, commit=True):
        """Save the config and the ExternalIntegration updated in clean().

        Args:
            commit (bool): Whether to save to the database.

        Returns:
            SSOTProxmoxConfig: The saved config.
        """
        config = super().save(commit=commit)
        if commit:
            config.proxmox_instance.validated_save()
        return config


class SSOTProxmoxConfigFilterForm(NautobotFilterForm):  # pylint: disable=too-many-ancestors
    """Filter form for SSOTProxmoxConfig filter searches."""

    model = SSOTProxmoxConfig

    class Meta:
        """Meta attributes for the SSOTProxmoxConfigFilterForm class."""

        model = SSOTProxmoxConfig
        fields = "__all__"
