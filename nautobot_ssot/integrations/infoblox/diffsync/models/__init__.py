"""Initialize models for Nautobot and Infoblox."""

from .nautobot import (
    NautobotDnsARecord,
    NautobotDnsHostRecord,
    NautobotDnsPTRRecord,
    NautobotNamespace,
    NautobotNetwork,
    NautobotIPAddress,
    NautobotVlanGroup,
    NautobotVlan,
)
from .infoblox import (
    InfobloxDnsARecord,
    InfobloxDnsHostRecord,
    InfobloxDnsPTRRecord,
    InfobloxNamespace,
    InfobloxNetwork,
    InfobloxIPAddress,
    InfobloxVLANView,
    InfobloxVLAN,
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
