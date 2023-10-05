"""Initialize models for Nautobot and Infoblox."""
from .nautobot import NautobotNetwork, NautobotIPAddress, NautobotVlanGroup, NautobotVlan
from .infoblox import InfobloxNetwork, InfobloxIPAddress, InfobloxVLANView, InfobloxVLAN


__all__ = [
    "NautobotNetwork",
    "NautobotIPAddress",
    "NautobotVlanGroup",
    "NautobotVlan",
    "InfobloxNetwork",
    "InfobloxIPAddress",
    "InfobloxVLANView",
    "InfobloxVLAN",
]
