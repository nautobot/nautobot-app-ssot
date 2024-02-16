"""Nautobot Adapter for vSphere Integration."""

from typing import Any, Dict, List

from diffsync.enum import DiffSyncFlags
from nautobot.ipam.models import IPAddress
from nautobot.virtualization.models import VirtualMachine

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.vsphere.diffsync.models.vsphere import (
    ClusterGroupModel,
    ClusterModel,
    IPAddressModel,
    PrefixModel,
    VirtualMachineModel,
    VMInterfaceModel,
)


class Adapter(NautobotAdapter):
    """Nautobot Adapter for vSphere SSoT."""

    _primary_ips: List[Dict[str, Any]]

    top_level = ("prefix", "clustergroup")
    prefix = PrefixModel
    clustergroup = ClusterGroupModel
    cluster = ClusterModel
    virtual_machine = VirtualMachineModel
    interface = VMInterfaceModel
    ip_address = IPAddressModel

    def __init__(self, *args, job=None, sync=None, config, **kwargs):
        """Initialize the adapter."""
        super().__init__(*args, job=job, sync=sync, **kwargs)
        self._primary_ips = []

    def load_param_mac_address(self, parameter_name, database_object):
        """Force mac address to string when loading it into the diffsync store."""
        return str(getattr(database_object, parameter_name))

    # def load_param_primary_ip4__host(self, parameter_name, database_object):
    #     """Load primary_ip4 host into Diffsync store."""
    #     print("PRIMARY IP")
    #     return str(getattr(database_object, parameter_name))

    # def load_param_primary_ip6__host(self, parameter_name, database_object):
    #     """Load primary_ip4 host into Diffsync store."""
    #     return str(getattr(database_object, parameter_name))

    def sync_complete(self, source, diff, flags: DiffSyncFlags = DiffSyncFlags.NONE, logger=None):
        """Update devices with their primary IPs once the sync is complete."""
        for info in self._primary_ips:
            vm = VirtualMachine.objects.get(**info["device"])
            for ip in ["primary_ip4", "primary_ip6"]:
                if info[ip]:
                    setattr(vm, ip, IPAddress.objects.get(host=info[ip]))
            vm.validated_save()
