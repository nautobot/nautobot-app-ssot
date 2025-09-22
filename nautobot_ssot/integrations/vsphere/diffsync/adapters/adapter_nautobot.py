"""Nautobot Adapter for vSphere Integration."""

from typing import Any, Dict, List

import pydantic
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectAlreadyExists
from django.core.exceptions import ValidationError
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
            try:
                vm.validated_save()
            except ValidationError as err:
                self.job.logger.error(f"Unable to set primary IP {info} on {vm}: {err}")

    def _load_single_object(self, database_object, diffsync_model, parameter_names):
        """Load a single diffsync object from a single database object."""
        parameters = {}
        for parameter_name in parameter_names:
            self._handle_single_parameter(parameters, parameter_name, database_object, diffsync_model)
        parameters["pk"] = database_object.pk
        try:
            diffsync_model = diffsync_model(**parameters)
        except pydantic.ValidationError as error:
            raise ValueError(f"Parameters: {parameters}") from error
        # If an IP is assigned to multiple interfaces, each VM will attempt to add it to DiffSync. We just catch the error if it already exists as we only need it in the diffsync store once.
        if diffsync_model._modelname == "ip_address":
            try:
                self.add(diffsync_model)
            except ObjectAlreadyExists:
                self.job.logger.warning(
                    f"IP Address {diffsync_model} already exists in DiffSync. This is an expected warning if you have multiple interaces with the same IP."
                )
        self.add(diffsync_model)
        self._handle_children(database_object, diffsync_model)
        return diffsync_model

    def _load_objects(self, diffsync_model):
        """Overriding _load_objects so we can pass in the config object to the models."""
        parameter_names = self._get_parameter_names(diffsync_model)
        for database_object in diffsync_model._get_queryset(self.config, self.cluster_filters):
            self._load_single_object(database_object, diffsync_model, parameter_names)
