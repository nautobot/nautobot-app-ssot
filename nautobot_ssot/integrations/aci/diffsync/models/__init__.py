"""Initialize models for Nautobot and ACI."""

from .nautobot import (
    NautobotTenant,
    NautobotVrf,
    NautobotDevice,
    NautobotDeviceRole,
    NautobotDeviceType,
    NautobotInterfaceTemplate,
    NautobotInterface,
    NautobotPrefix,
    NautobotIPAddress,
    NautobotACIAppProfile,
    NautobotACIBridgeDomain,
    NautobotACIEPG,
    NautobotACIAppTermination,
)

__all__ = [
    "NautobotTenant",
    "NautobotVrf",
    "NautobotDevice",
    "NautobotDeviceRole",
    "NautobotDeviceType",
    "NautobotInterfaceTemplate",
    "NautobotInterface",
    "NautobotPrefix",
    "NautobotIPAddress",
    "NautobotACIAppProfile",
    "NautobotACIBridgeDomain",
    "NautobotACIEPG",
    "NautobotACIAppTermination",
]
