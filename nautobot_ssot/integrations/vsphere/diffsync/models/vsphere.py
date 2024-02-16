"""vSphere SSoT DiffSync models."""

from typing import List, Optional

from nautobot.ipam.models import IPAddress, Prefix
from nautobot.virtualization.models import (
    Cluster,
    ClusterGroup,
    VirtualMachine,
    VMInterface,
)
from typing_extensions import TypedDict

from nautobot_ssot.contrib import NautobotModel


class InterfacesDict(TypedDict):
    """Typed dict to relate interface to IP."""

    name: str


class PrefixModel(NautobotModel):
    """Prefix model."""

    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name", "status__name")
    _attributes = ("type",)

    network: str
    prefix_length: int
    namespace__name: str
    status__name: str
    type: str


class IPAddressModel(NautobotModel):
    """IPAddress Diffsync model."""

    _model = IPAddress
    _modelname = "ip_address"
    _identifiers = ("host", "mask_length", "status__name")
    _attributes = ("vm_interfaces",)

    host: str
    mask_length: int
    status__name: str
    vm_interfaces: List[InterfacesDict] = []


class VMInterfaceModel(NautobotModel):
    """VMInterface Diffsync model."""

    _model = VMInterface
    _modelname = "interface"
    _identifiers = ("name", "virtual_machine__name")
    _attributes = ("enabled", "mac_address", "status__name")
    _children = {"ip_address": "ip_addresses"}

    name: str
    virtual_machine__name: str
    enabled: bool
    status__name: str
    mac_address: Optional[str] = None
    ip_addresses: List[IPAddress] = []


class VirtualMachineModel(NautobotModel):
    """Virtual Machine Diffsync model."""

    _model = VirtualMachine
    _modelname = "virtual_machine"
    _identifiers = ("name",)
    _attributes = (
        "status__name",
        "vcpus",
        "memory",
        "disk",
        "cluster__name",
        "primary_ip4__host",
        "primary_ip6__host",
    )
    _children = {"interface": "interfaces"}

    name: str
    status__name: str
    vcpus: Optional[int] = None
    memory: Optional[int] = None
    disk: Optional[int] = None
    cluster__name: str
    primary_ip4__host: Optional[str] = None
    primary_ip6__host: Optional[str] = None

    interfaces: List[VMInterface] = []

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create the device.

        This overridden method removes the primary IP addresses since those
        cannot be set until after the interfaces are created. The primary IPs
        are set in the `sync_complete` callback of the adapter.

        Args:
            diffsync (VsphereDiffSync): The nautobot sync adapter.
            ids (dict[str, Any]): The natural keys for the device.
            attrs (dict[str, Any]): The attributes to assign to the newly created
                device.

        Returns:
            DeviceModel: The device model.
        """
        if attrs["primary_ip4__host"] or attrs["primary_ip6__host"]:
            adapter._primary_ips.append(
                {
                    "device": {**ids},
                    "primary_ip4": attrs.pop("primary_ip4__host", None),
                    "primary_ip6": attrs.pop("primary_ip4__host", None),
                }
            )
        return super().create(adapter, ids, attrs)


class ClusterModel(NautobotModel):
    """Cluster Model Diffsync model."""

    _model = Cluster
    _modelname = "cluster"
    _identifiers = ("name",)
    _attributes = (
        "cluster_type__name",
        "cluster_group__name",
    )
    _children = {"virtual_machine": "virtual_machines"}

    name: str
    cluster_type__name: str
    cluster_group__name: Optional[str] = None

    virtual_machines: List[VirtualMachineModel] = list()


class ClusterGroupModel(NautobotModel):
    """ClusterGroup Diffsync model."""

    _model = ClusterGroup
    _modelname = "clustergroup"
    _identifiers = ("name",)
    _attributes = ()
    _children = {"cluster": "clusters"}

    name: str
    clusters: Optional[List[ClusterModel]] = list()
