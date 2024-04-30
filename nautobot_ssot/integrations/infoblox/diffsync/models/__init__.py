"""Initialize models for Nautobot and Infoblox."""
from .nautobot import NautobotNamespace, NautobotNetwork, NautobotIPAddress, NautobotVlanGroup, NautobotVlan
from .infoblox import InfobloxNamespace, InfobloxNetwork, InfobloxIPAddress, InfobloxVLANView, InfobloxVLAN


__all__ = [
    "NautobotNamespace",
    "NautobotNetwork",
    "NautobotIPAddress",
    "NautobotVlanGroup",
    "NautobotVlan",
    "InfobloxNamespace",
    "InfobloxNetwork",
    "InfobloxIPAddress",
    "InfobloxVLANView",
    "InfobloxVLAN",
]
