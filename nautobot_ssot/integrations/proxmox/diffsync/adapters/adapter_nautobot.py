"""Nautobot Adapter for the Proxmox VE Integration."""

from typing import Any, Dict, List

from diffsync.enum import DiffSyncFlags
from django.core.exceptions import ValidationError
from nautobot.dcim.models import Device, Interface
from nautobot.ipam.models import IPAddress
from nautobot.virtualization.models import VirtualMachine

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.proxmox.diffsync.models.proxmox import (
    ClusterGroupModel,
    ClusterModel,
    DeviceInterfaceModel,
    DeviceModel,
    IPAddressModel,
    PrefixModel,
    TagModel,
    VirtualMachineModel,
    VMInterfaceModel,
)


class NBAdapter(NautobotAdapter):
    """Nautobot Adapter for Proxmox VE SSoT."""

    _primary_ips: List[Dict[str, Any]]
    _device_primary_ips: List[Dict[str, Any]]
    _interface_links: List[Dict[str, Any]]

    top_level = ("tag", "prefix", "clustergroup", "device", "virtual_machine", "ip_address")
    tag = TagModel
    prefix = PrefixModel
    clustergroup = ClusterGroupModel
    cluster = ClusterModel
    device = DeviceModel
    device_interface = DeviceInterfaceModel
    virtual_machine = VirtualMachineModel
    interface = VMInterfaceModel
    ip_address = IPAddressModel

    def __init__(self, *args, job=None, sync=None, config, cluster_filters, **kwargs):
        """Initialize the adapter."""
        super().__init__(*args, job=job, sync=sync, **kwargs)
        self.config = config
        self.cluster_filters = cluster_filters
        self._primary_ips = []
        self._device_primary_ips = []
        self._interface_links = []

    def load_param_mac_address(self, parameter_name, database_object):
        """Force mac address to string when loading it into the diffsync store."""
        return str(getattr(database_object, parameter_name))

    def sync_complete(self, source, diff, flags: DiffSyncFlags = DiffSyncFlags.NONE, logger=None):
        """Update VMs with their primary IPs once the sync is complete."""
        for info in self._primary_ips:
            try:
                vm = VirtualMachine.objects.get(**info["device"])
            except VirtualMachine.DoesNotExist:
                self.job.logger.warning(
                    f"VirtualMachine not found for {info['device']}, skipping primary IP assignment."
                )
                continue
            for ip in ["primary_ip4", "primary_ip6"]:
                if info[ip]:
                    try:
                        setattr(vm, ip, IPAddress.objects.get(host=info[ip]))
                    except IPAddress.DoesNotExist:
                        self.job.logger.warning(f"IPAddress {info[ip]} not found for {vm}, skipping {ip} assignment.")
                    except IPAddress.MultipleObjectsReturned:
                        self.job.logger.warning(
                            f"Multiple IPAddresses found for host {info[ip]} on {vm}, skipping {ip} assignment."
                        )
            try:
                vm.validated_save()
            except ValidationError as err:
                self.job.logger.error(f"Unable to set primary IP {info} on {vm}: {err}")

        self._link_node_interfaces()
        self._assign_device_primary_ips()

    def _link_node_interfaces(self):
        """Resolve deferred bridge/bond/VLAN relationships between a node's interfaces."""
        relation_fields = {
            "bridge__name": "bridge",
            "lag__name": "lag",
            "parent_interface__name": "parent_interface",
        }
        for link in self._interface_links:
            try:
                interface = Interface.objects.get(device__name=link["device__name"], name=link["name"])
            except Interface.DoesNotExist:
                self.job.logger.warning(f"Interface {link['name']} on {link['device__name']} not found for linking.")
                continue
            changed = False
            for source_key, field_name in relation_fields.items():
                target_name = link.get(source_key)
                current = getattr(interface, field_name)
                if target_name:
                    try:
                        related = Interface.objects.get(device__name=link["device__name"], name=target_name)
                    except Interface.DoesNotExist:
                        self.job.logger.warning(
                            f"Related interface {target_name} on {link['device__name']} not found, skipping {field_name}."
                        )
                        continue
                    if current != related:
                        setattr(interface, field_name, related)
                        changed = True
                elif current is not None:
                    setattr(interface, field_name, None)
                    changed = True
            if changed:
                try:
                    interface.validated_save()
                except ValidationError as err:
                    self.job.logger.error(f"Unable to link interface {interface} relationships: {err}")

    def _assign_device_primary_ips(self):
        """Assign deferred primary IPv4 addresses to node Devices."""
        for info in self._device_primary_ips:
            try:
                device = Device.objects.get(name=info["name"])
            except Device.DoesNotExist:
                self.job.logger.warning(f"Device {info['name']} not found for primary IP assignment.")
                continue
            try:
                device.primary_ip4 = IPAddress.objects.get(host=info["primary_ip4"])
            except IPAddress.DoesNotExist:
                self.job.logger.warning(f"IPAddress {info['primary_ip4']} not found for {device}, skipping.")
                continue
            except IPAddress.MultipleObjectsReturned:
                self.job.logger.warning(f"Multiple IPAddresses for {info['primary_ip4']} on {device}, skipping.")
                continue
            try:
                device.validated_save()
            except ValidationError as err:
                self.job.logger.error(f"Unable to set primary IP {info} on {device}: {err}")

    def _load_objects(self, diffsync_model):
        """Override _load_objects so we can pass in the config object to the models."""
        parameter_names = self._get_parameter_names(diffsync_model)
        for database_object in diffsync_model._get_queryset(self.config, self.cluster_filters):
            self._load_single_object(database_object, diffsync_model, parameter_names)
