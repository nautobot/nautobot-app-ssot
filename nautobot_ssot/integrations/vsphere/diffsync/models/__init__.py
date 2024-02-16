"""Collection of adapters."""

from .vsphere import ClusterGroupModel, ClusterModel, IPAddressModel, PrefixModel, VirtualMachineModel, VMInterfaceModel

__all__ = (
    "IPAddressModel",
    "VMInterfaceModel",
    "VirtualMachineModel",
    "ClusterModel",
    "ClusterGroupModel",
    "PrefixModel",
)
