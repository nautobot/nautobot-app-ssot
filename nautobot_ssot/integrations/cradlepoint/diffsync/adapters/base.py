"""Base adapater classes for Cradlepoint SSoT."""

from nautobot_ssot.integrations.cradlepoint.diffsync.models.nautobot import (
    NautobotDeviceType,
    NautobotManufacturer,
)


class BaseNautobotAdapter:
    """Base DiffSync adapter for Cradlepoint to Nautobot syncs."""

    manufacturer = NautobotManufacturer
    device_type = NautobotDeviceType

    top_level = [
        "manufacturer",
        "device_type",
    ]
