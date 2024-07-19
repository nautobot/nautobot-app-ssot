"""Itential SSoT adapters."""

from diffsync import DiffSync

from nautobot_ssot.integrations.itential.diffsync.models.itential import (
    ItentialAnsibleDeviceModel,
    ItentialDefaultAnsibleGroupModel,
)
from nautobot_ssot.integrations.itential.clients import AutomationGatewayClient


class ItentialAnsibleDeviceAdapter(DiffSync):
    """Itential Ansible Device Diffsync adapter."""

    device = ItentialAnsibleDeviceModel
    all_group = ItentialDefaultAnsibleGroupModel
    top_level = ["all_group", "device"]

    def __init__(self, api_client: AutomationGatewayClient, job: object, sync: object, *args, **kwargs):
        """Initialize Diffsync Adapter."""
        super().__init__(*args, **kwargs)
        self.api_client = api_client
        self.job = job
        self.sync = sync

    def load(self):
        """Load Adapter."""
        self.job.logger.info(f"Loading default ansible group variables from {self.api_client.host}.")
        groups = self.api_client.get_groups().get("data")

        for iag_group in groups:
            if iag_group.get("name") == "all":
                _group = self.all_group(name=iag_group.get("name"), variables=iag_group.get("variables"))

                self.add(_group)

        self.job.logger.info(f"Loading Itential devices from {self.api_client.host} into Diffsync adapter.")
        devices = self.api_client.get_devices().get("data")

        for iag_device in devices:
            _device = self.device(name=iag_device.get("name"), variables=iag_device.get("variables"))

            self.add(_device)
