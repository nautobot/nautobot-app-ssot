"""Initialize models for Nautobot and Infoblox."""
from .infoblox import InfobloxIPAddress, InfobloxNetwork, InfobloxVLAN, InfobloxVLANView
from .nautobot import NautobotIPAddress, NautobotNetwork, NautobotVlan, NautobotVlanGroup

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
