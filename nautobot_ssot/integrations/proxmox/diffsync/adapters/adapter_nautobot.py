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

    def _safe_get(self, model, lookup_kwargs, not_found_message, multiple_message=None):
        """Look up a single related object, logging the exact existing warning on failure.

        Args:
            model (Type[Model]): The Django model class to query.
            lookup_kwargs (dict): Keyword arguments for the ``.objects.get()`` lookup.
            not_found_message (str): Warning message to log if the object does not exist.
            multiple_message (Optional[str]): Warning message to log if multiple objects are
                returned. If ``None``, ``MultipleObjectsReturned`` is not handled here and
                propagates to the caller, matching call sites that never caught it before.

        Returns:
            Optional[Model]: The model instance, or ``None`` if the lookup failed.
        """
        try:
            return model.objects.get(**lookup_kwargs)
        except model.DoesNotExist:
            self.job.logger.warning(not_found_message)
            return None
        except model.MultipleObjectsReturned:
            if multiple_message is None:
                raise
            self.job.logger.warning(multiple_message)
            return None

    def _safe_validated_save(self, obj, error_context):
        """Call ``validated_save()``, logging the exact existing error message on failure.

        Args:
            obj (Any): The Nautobot ORM object to save.
            error_context (str): Text describing the operation, inserted into
                ``f"Unable to {error_context}: {err}"`` to match the current message format exactly.

        Returns:
            bool: ``True`` if the save succeeded, ``False`` if a ``ValidationError`` was raised.
        """
        try:
            obj.validated_save()
            return True
        except ValidationError as err:
            self.job.logger.error(f"Unable to {error_context}: {err}")
            return False

    def sync_complete(self, source, diff, flags: DiffSyncFlags = DiffSyncFlags.NONE, logger=None):
        """Update VMs with their primary IPs once the sync is complete."""
        for info in self._primary_ips:
            vm = self._safe_get(
                VirtualMachine,
                info["device"],
                f"VirtualMachine not found for {info['device']}, skipping primary IP assignment.",
            )
            if vm is None:
                continue
            for ip in ["primary_ip4", "primary_ip6"]:
                if info[ip]:
                    ip_obj = self._safe_get(
                        IPAddress,
                        {"host": info[ip]},
                        f"IPAddress {info[ip]} not found for {vm}, skipping {ip} assignment.",
                        f"Multiple IPAddresses found for host {info[ip]} on {vm}, skipping {ip} assignment.",
                    )
                    if ip_obj is not None:
                        setattr(vm, ip, ip_obj)
            self._safe_validated_save(vm, f"set primary IP {info} on {vm}")

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
            interface = self._safe_get(
                Interface,
                {"device__name": link["device__name"], "name": link["name"]},
                f"Interface {link['name']} on {link['device__name']} not found for linking.",
            )
            if interface is None:
                continue
            changed = False
            for source_key, field_name in relation_fields.items():
                target_name = link.get(source_key)
                current = getattr(interface, field_name)
                if target_name:
                    related = self._safe_get(
                        Interface,
                        {"device__name": link["device__name"], "name": target_name},
                        f"Related interface {target_name} on {link['device__name']} not found, "
                        f"skipping {field_name}.",
                    )
                    if related is None:
                        continue
                    if current != related:
                        setattr(interface, field_name, related)
                        changed = True
                elif current is not None:
                    setattr(interface, field_name, None)
                    changed = True
            if changed:
                self._safe_validated_save(interface, f"link interface {interface} relationships")

    def _assign_device_primary_ips(self):
        """Assign deferred primary IPv4 addresses to node Devices."""
        for info in self._device_primary_ips:
            device = self._safe_get(
                Device,
                {"name": info["name"]},
                f"Device {info['name']} not found for primary IP assignment.",
            )
            if device is None:
                continue
            ip_obj = self._safe_get(
                IPAddress,
                {"host": info["primary_ip4"]},
                f"IPAddress {info['primary_ip4']} not found for {device}, skipping.",
                f"Multiple IPAddresses for {info['primary_ip4']} on {device}, skipping.",
            )
            if ip_obj is None:
                continue
            device.primary_ip4 = ip_obj
            self._safe_validated_save(device, f"set primary IP {info} on {device}")

    def _load_objects(self, diffsync_model):
        """Override _load_objects so we can pass in the config object to the models."""
        parameter_names = self._get_parameter_names(diffsync_model)
        for database_object in diffsync_model._get_queryset(self.config, self.cluster_filters):
            self._load_single_object(database_object, diffsync_model, parameter_names)
