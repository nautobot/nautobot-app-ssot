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


class NBAdapter(NautobotAdapter):
    """Nautobot Adapter for vSphere SSoT."""

    _primary_ips: List[Dict[str, Any]]

    top_level = ("prefix", "clustergroup", "virtual_machine")
    prefix = PrefixModel
    clustergroup = ClusterGroupModel
    cluster = ClusterModel
    virtual_machine = VirtualMachineModel
    interface = VMInterfaceModel
    ip_address = IPAddressModel

    def __init__(self, *args, job=None, sync=None, config, cluster_filters, **kwargs):
        """Initialize the adapter."""
        super().__init__(*args, job=job, sync=sync, **kwargs)
        self.config = config
        self.cluster_filters = cluster_filters
        self._primary_ips = []

    def load_param_mac_address(self, parameter_name, database_object):
        """Force mac address to string when loading it into the diffsync store."""
        return str(getattr(database_object, parameter_name))

    def sync_complete(self, source, diff, flags: DiffSyncFlags = DiffSyncFlags.NONE, logger=None):
        """Update devices with their primary IPs once the sync is complete."""
        for info in self._primary_ips:
            vm = VirtualMachine.objects.get(**info["device"])
            for ip in ["primary_ip4", "primary_ip6"]:
                if info[ip]:
                    setattr(vm, ip, IPAddress.objects.get(host=info[ip]))
            vm.validated_save()

    def _load_objects(self, diffsync_model):
        """Overriding _load_objects so we can pass in the config object to the models."""
        parameter_names = self._get_parameter_names(diffsync_model)
        for database_object in diffsync_model._get_queryset(self.config, self.cluster_filters):
            self._load_single_object(database_object, diffsync_model, parameter_names)
