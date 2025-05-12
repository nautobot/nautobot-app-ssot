"""Common TypedDict definitions used in Many-to-Many relationships."""

from typing_extensions import Annotated, TypedDict


class SortKey:
    """A simple class for identifying sort keys in TypedDict attribute annotations."""


class ContentTypeDict(TypedDict):
    """TypedDict for Django Content Types."""

    app_label: str
    model: Annotated[str, SortKey]


class TagDict(TypedDict):
    """TypedDict for Nautobot Tags."""

    name: Annotated[str, SortKey]


class LocationDict(TypedDict):
    """TypedDict for DCIM Locations."""

    name: Annotated[str, SortKey]
    parent__name: str


class DeviceDict(TypedDict):
    """TypedDict for DCIM Devices."""

    name: Annotated[str, SortKey]
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

    name: Annotated[str, SortKey]
    device__name: str


class PrefixDict(TypedDict):
    """TypedDict for IPAM Prefixes."""

    network: Annotated[str, SortKey]
    prefix_length: int
    namespace__name: str


class VLANDict(TypedDict):
    """TypedDict for IPAM VLANs."""

    vid: Annotated[int, SortKey]
    vlan_group__name: str


class IPAddressDict(TypedDict):
    """TypedDict for IPAM IP Address."""

    host: Annotated[str, SortKey]
    prefix_length: int


class VirtualMachineDict(TypedDict):
    """TypedDict for IPAM ."""

    name: Annotated[str, SortKey]
    cluster__name: str
    tenant__name: str
