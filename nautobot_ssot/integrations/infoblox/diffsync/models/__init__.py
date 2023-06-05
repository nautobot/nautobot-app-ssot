"""Initialize models for Nautobot and Infoblox."""
from .nautobot import NautobotAggregate, NautobotNetwork, NautobotIPAddress, NautobotVlanGroup, NautobotVlan
from .infoblox import InfobloxAggregate, InfobloxNetwork, InfobloxIPAddress, InfobloxVLANView, InfobloxVLAN


__all__ = [
    "NautobotAggregate",
    "NautobotNetwork",
    "NautobotIPAddress",
    "NautobotVlanGroup",
    "NautobotVlan",
    "InfobloxAggregate",
    "InfobloxNetwork",
    "InfobloxIPAddress",
    "InfobloxVLANView",
    "InfobloxVLAN",
]
