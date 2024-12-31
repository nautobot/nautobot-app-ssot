"""Common TypedDict definitions used in Many-to-Many relationships."""

from typing import Annotated, TypedDict

from nautobot_ssot.contrib.types import FieldType


class ContentTypeDict(TypedDict):
    """TypedDict for Django Content Types."""

    app_label: str
    model: Annotated[str, FieldType.SORT_BY]


class TagDict(TypedDict):
    """TypedDict for Nautobot Tags."""

    name: Annotated[str, FieldType.SORT_BY]


class LocationDict(TypedDict):
    """TypedDict for DCIM Locations."""

    name: Annotated[str, FieldType.SORT_BY]
    parent__name: str


class DeviceDict(TypedDict):
    """TypedDict for DCIM Devices."""

    name: Annotated[str, FieldType.SORT_BY]
    location__name: str
    tenant__name: str
    rack__name: str
    rack__rack_group__name: str
    position: int
    face: str
    virtual_chassis__name: str
    vc_position: int


class InterfaceDict(TypedDict):
    """TypedDict for DCIM INterfaces."""

    name: Annotated[str, FieldType.SORT_BY]
    device__name: str


class PrefixDict(TypedDict):
    """TypedDict for IPAM Prefixes."""

    network: Annotated[str, FieldType.SORT_BY]
    prefix_length: int
    namespace__name: str


class VLANDict(TypedDict):
    """TypedDict for IPAM VLANs."""

    vid: Annotated[int, FieldType.SORT_BY]
    vlan_group__name: str


class IPAddressDict(TypedDict):
    """TypedDict for IPAM IP Address."""

    host: Annotated[str, FieldType.SORT_BY]
    prefix_length: int


class VirtualMachineDict(TypedDict):
    """TypedDict for IPAM ."""

    name: Annotated[str, FieldType.SORT_BY]
    cluster__name: str
    tenant__name: str
