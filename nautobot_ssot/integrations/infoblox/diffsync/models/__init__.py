"""Initialize models for Nautobot and Infoblox."""

from .infoblox import (
    InfobloxDnsARecord,
    InfobloxDnsHostRecord,
    InfobloxDnsPTRRecord,
    InfobloxIPAddress,
    InfobloxNamespace,
    InfobloxNetwork,
    InfobloxVLAN,
    InfobloxVLANView,
)
from .nautobot import (
    NautobotDnsARecord,
    NautobotDnsHostRecord,
    NautobotDnsPTRRecord,
    NautobotIPAddress,
    NautobotNamespace,
    NautobotNetwork,
    NautobotVlan,
    NautobotVlanGroup,
)

__all__ = [
    "NautobotDnsARecord",
    "NautobotDnsHostRecord",
    "NautobotDnsPTRRecord",
    "NautobotNamespace",
    "NautobotNetwork",
    "NautobotIPAddress",
    "NautobotVlanGroup",
    "NautobotVlan",
    "InfobloxDnsARecord",
    "InfobloxDnsHostRecord",
    "InfobloxDnsPTRRecord",
    "InfobloxNamespace",
    "InfobloxNetwork",
    "InfobloxIPAddress",
    "InfobloxVLANView",
    "InfobloxVLAN",
]
