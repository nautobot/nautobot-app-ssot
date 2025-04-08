"""Nautobot Adapter for Cradlepoint Integration."""

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.cradlepoint.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotDeviceType,
    NautobotRole,
    NautobotStatus,
)


class Adapter(NautobotAdapter):
    """Nautobot Adapter for vSphere SSoT."""

    status = NautobotStatus
    device_role = NautobotRole
    device_type = NautobotDeviceType
    device = NautobotDevice

    top_level = ("status", "device_role", "device_type", "device")

    def __init__(self, *args, job=None, sync=None, config, **kwargs):
        """Initialize the adapter."""
        super().__init__(*args, job=job, sync=sync, **kwargs)
        self.config = config

    def load_param_mac_address(self, parameter_name, database_object):
        """Force mac address to string when loading it into the diffsync store."""
        return str(getattr(database_object, parameter_name))
