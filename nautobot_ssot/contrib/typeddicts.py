"""Common TypedDict definitions used in Many-to-Many relationships."""


from typing_extensions import TypedDict


class SortKey:
    """A simple class for identifying sort keys in TypedDict attribute annotations."""


class ContentTypeDict(TypedDict):
    """TypedDict for Django Content Types."""

    app_label: str
    model: str


class TagDict(TypedDict):
    """TypedDict for Nautobot Tags."""

    name: str


class LocationDict(TypedDict):
    """TypedDict for DCIM Locations."""

    name: str
    parent__name: str


class DeviceDict(TypedDict):
    """TypedDict for DCIM Devices."""

    name: str
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

    name: str
    device__name: str


class PrefixDict(TypedDict):
    """TypedDict for IPAM Prefixes."""

    network: str
    prefix_length: int
    namespace__name: str


class VLANDict(TypedDict):
    """TypedDict for IPAM VLANs."""

    vid: int
    vlan_group__name: str


class IPAddressDict(TypedDict):
    """TypedDict for IPAM IP Address."""

    host: str
    mask_length: int


class VirtualMachineDict(TypedDict):
    """TypedDict for IPAM ."""

    name: str
    cluster__name: str
    tenant__name: str


class TenantDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: str


class CustomRelationshipDict(TypedDict):
    """Typed dictionary for custom relationships."""

    name: str
