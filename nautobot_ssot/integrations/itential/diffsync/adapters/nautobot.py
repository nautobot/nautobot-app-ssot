"""Itential SSoT Nautobot adapters."""

import re
import traceback

from diffsync import DiffSync

from nautobot.extras.models import Status
from nautobot.dcim.models import Device

from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.integrations.itential.diffsync.models.nautobot import (
    NautobotAnsibleDeviceModel,
    NautobotDefaultAnsibleGroupModel,
)


class NautobotAnsibleDeviceAdapter(DiffSync):
    """Nautobot => Itential Ansible Device Diffsync Adapter."""

    device = NautobotAnsibleDeviceModel
    all_group = NautobotDefaultAnsibleGroupModel
    top_level = ["all_group", "device"]

    def __init__(  # pylint disable=too-many-arguments
        self, job: object, sync: object, gateway: AutomationGatewayModel, status: Status, *args, **kwargs
    ):
        """Initialize Nautobot Itential Ansible Device Diffsync adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.gateway = gateway
        self.status = status

    def _is_rfc1123_compliant(self, device_name: str) -> bool:
        """Check to see if a device name is RFC 1123 compliant."""
        # Check for invalid characters (anything other than alphanumerics, hypens, and periods)
        if not re.search("[a-zA-Z0-9][a-zA-Z0-9-.]{0,62}$", device_name):
            self.job.logger.warning(f"{device_name} has iinvalid characters.")
            return False

        # RFC 1123 allows hostnames to start with a digit
        label_pattern = r"[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$"

        # Split device_name into labels and check each one
        labels = device_name.split(".")

        for label in labels:
            if not re.match(label_pattern, label) or label.endswith("-"):
                self.job.logger.warning(f"{device_name} has an invalid hostname pattern.")
                return False

        return True

    def _ansible_vars(self, device_obj: Device) -> dict:
        """Create device variables to load into Automation Gateway."""
        # Add ansible_network_os if available
        if device_obj.platform and device_obj.platform.network_driver_mappings.get("ansible"):
            ansible_network_os = {"ansible_network_os": device_obj.platform.network_driver_mappings.get("ansible")}
        else:
            ansible_network_os = {}

        # Add device specific credentials if available
        try:
            ansible_username = {
                "ansible_username": device_obj.secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
                )
            }
            ansible_password = {
                "ansible_password": device_obj.secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
                )
            }
        except AttributeError:
            ansible_username = {}
            ansible_password = {}

        # Add ansible_host
        ansible_host = {"ansible_host": device_obj.primary_ip4.host}

        # Add device attributes from config_context
        config_context = device_obj.get_config_context()

        return {**ansible_host, **ansible_network_os, **ansible_username, **ansible_password, **config_context}

    @property
    def _default_group_vars(self) -> dict:
        """Create the ansible default group variables to load into Automation Gateway."""
        try:
            ansible_username = {
                "ansible_username": self.gateway.gateway.secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
                )
            }
            ansible_password = {
                "ansible_password": self.gateway.gateway.secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
                )
            }
        except AttributeError:
            ansible_username = {}
            ansible_password = {}

        return {**ansible_username, **ansible_password}

    def load(self):
        """Load Nautobot Diffsync adapter."""
        self.job.logger.info("Loading default ansible group variables from Nautobot.")
        _group = self.all_group(name="all", variables=self._default_group_vars)
        self.add(_group)

        self.job.logger.info("Loading locations from Nautobot.")
        location = self.gateway.location
        locations = location.descendants(include_self=True) if self.gateway.location_descendants else location

        self.job.logger.info("Loading devices from Nautobot.")
        devices = Device.objects.filter(location__in=locations, status=self.status.pk).exclude(primary_ip4=None)

        for nb_device in devices:
            try:
                if self._is_rfc1123_compliant(nb_device.name):
                    device_vars = self._ansible_vars(nb_device)
                    _device = self.device(name=nb_device.name, variables=device_vars)

                    self.add(_device)
                else:
                    raise Exception(  # pylint: disable=broad-exception-raised
                        f"{nb_device.name} is not RFC 1123 compliant."
                    )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                stacktrace = traceback.format_exc()
                self.job.logger.warning(f"{nb_device.name} was not added to inventory due to an error.")
                self.job.logger.warning(
                    f"An exception ocurred: " f"`{type(exec).__name__}: {exc}`\n```\n{stacktrace}\n```"
                )
