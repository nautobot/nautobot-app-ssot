"""Nautobot adapter for the Cisco SD-WAN SSoT integration."""

from diffsync.exceptions import ObjectAlreadyExists

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.cisco_sdwan.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotDeviceType,
    NautobotInterface,
    NautobotIPAddressToInterface,
    NautobotSoftwareVersion,
)


class CiscoSdwanNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    device = NautobotDevice
    device_type = NautobotDeviceType
    software_version = NautobotSoftwareVersion
    interface = NautobotInterface
    ip_address_to_interface = NautobotIPAddressToInterface

    top_level = ["device_type", "software_version", "device", "interface", "ip_address_to_interface"]

    def _load_objects(self, diffsync_model):
        """Load a list of Nautobot objects for the given diffsync model, scoped by the Job parameters."""
        parameter_names = self._get_parameter_names(diffsync_model)
        data = {
            "devices": self.job.devices,
            "managed_device_group": self.job.managed_device_group,
        }
        for database_object in diffsync_model.get_queryset(data=data):
            try:
                self._load_single_object(database_object, diffsync_model, parameter_names)
            except ObjectAlreadyExists:
                continue
