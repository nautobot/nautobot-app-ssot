"""Firewall API."""

from ipaddress import IPv4Interface

from panos.device import SystemSettings, Vsys
from panos.errors import PanDeviceXapiError
from panos.firewall import Firewall
from panos.network import (
    AggregateInterface,
    EthernetInterface,
    LoopbackInterface,
    TunnelInterface,
    VlanInterface,
    Zone,
)

from .base import BaseAPI


class PanoramaFirewallAPI(BaseAPI):
    """Firewall Zone Vsys Objects API SDK."""

    firewalls = []
    vsys = {}
    zones = {}

    #####################
    # Firewall
    #####################

    def get_hostname(self, firewall: "Firewall") -> str:
        """Returns a firewall's hostname if reachable else serial.

        Args:
            firewall (Firewall): panos.firewall.Firewall instance

        Returns:
            str: Hostname or serial
        """
        for child in firewall.children:
            if isinstance(child, SystemSettings):
                return child.hostname
        return firewall.serial

    def retrieve_firewalls(self):
        """Returns all ApplicationGroups."""
        self.firewalls = self._get_firewalls_via_device_groups(Firewall, "object")
        return self.firewalls

    #####################
    # Vsys              #
    #####################

    def retrieve_vsys(self):
        """Returns all Vsys."""

        def map_if_types(vsys_if_list: list) -> set:
            """Guess vsys interface classes based on name."""
            if_types = set()
            for if_name in vsys_if_list:
                if "." in if_name:
                    continue  # TODO:
                    # if_types.add(Layer3Subinterface)
                    # if_types.add(Layer2Subinterface)
                if if_name.startswith("ethernet"):
                    if_types.add(EthernetInterface)
                elif if_name.startswith("loopback"):
                    if_types.add(LoopbackInterface)
                elif if_name.startswith("ae"):
                    if_types.add(AggregateInterface)
                elif if_name.startswith("vlan"):
                    if_types.add(VlanInterface)
                elif if_name.startswith("tunnel"):
                    if_types.add(TunnelInterface)
            return if_types

        for firewall in self.firewalls:
            firewall_name = firewall.get("name")
            firewall_obj = firewall.get("value")
            firewall_device_group_name = firewall.get("location")
            if not isinstance(firewall_obj, Firewall):
                continue
            children_vsys = [vsys for vsys in firewall_obj.children if isinstance(vsys, Vsys)]
            if not children_vsys:
                continue
            for vsys_obj in children_vsys:
                vsys_name = vsys_obj.name
                try:
                    if not self.vsys.get(firewall_obj.serial):
                        self.vsys[firewall_obj.serial] = {}
                    if self.job.debug:
                        self.job.logger.debug(f"Caching data for {vsys_name} for device: {firewall_name}")
                    self.vsys[firewall_obj.serial][vsys_name] = {}
                    self.vsys[firewall_obj.serial][vsys_name]["cached_successfully"] = False
                    self.vsys[firewall_obj.serial][vsys_name].update(
                        {
                            "name": vsys_name,
                            "vsys_obj": vsys_obj,
                            "firewall_name": firewall_name,
                            "firewall_obj": firewall_obj,
                            "devicegroup": firewall_device_group_name,
                            "interfaces": [],
                        }
                    )
                    # Find relevant iftypes to avoid expensive refresh operations.
                    vsys_if_list = vsys_obj.interface or []
                    interface_types = map_if_types(vsys_if_list)
                    # retrieve relevant interfaces for each type of interface for each vsys
                    for interface_type in interface_types:
                        self.vsys[firewall_obj.serial][vsys_name]["interfaces"] += interface_type.refreshall(vsys_obj)
                    self.vsys[firewall_obj.serial][vsys_name]["cached_successfully"] = True
                except Exception as err:
                    self.vsys[firewall_obj.serial][vsys_name] = {}
                    self.vsys[firewall_obj.serial][vsys_name]["name"] = vsys_name
                    self.vsys[firewall_obj.serial][vsys_name]["cached_successfully"] = False
                    self.job.logger.warning(f"Error caching {vsys_name} for device: {firewall_name}, {err}")
                    continue
        return self.vsys

    #####################
    # Zone              #
    #####################

    # Optimized (cached) zone retrieval
    def retrieve_zones(self):
        """Returns all Zones."""
        for fw_sn, fw_vsys in self.vsys.items():
            for _, vsys_values in fw_vsys.items():
                try:
                    vsys_obj = vsys_values.get("vsys_obj", None)
                    if not isinstance(vsys_obj, Vsys):
                        # If there was an error during load, skip.
                        continue
                    for child in vsys_obj.children:
                        if not isinstance(child, Zone):
                            continue
                        if not child.interface:
                            continue
                        if not self.zones.get(fw_sn):
                            self.zones[fw_sn] = {child.name: child}
                        else:
                            self.zones[fw_sn][child.name] = child
                except PanDeviceXapiError:
                    pass
        return self.zones

    #####################
    # General Utility   #
    #####################

    def get_management_interface_name_and_ip(self, firewall: "Firewall"):
        """Retrieve the management interface name and IP address for a PAN-OS firewall.

        This method attempts to identify the management interface and its IP address
        by examining the firewall's system information and interface configuration.
        It uses several heuristics to identify the management interface including:
        - Interfaces with "management" in their name
        - Interfaces in "ha" mode
        - Interfaces configured with the management IP
        Args:
            firewall (Firewall): A PAN-OS firewall object to query
        Returns:
            tuple: A tuple containing:
                - str: The name of the management interface (defaults to "mgmt")
                - str or None: The management IP address if found, None otherwise
        Notes:
            The method handles exceptions internally and logs warnings rather than
            raising exceptions when operations fail.
        """
        mgmt_ip = None
        mgmt_interface_name = "mgmt"

        try:
            system_info = firewall.show_system_info()
            if "ip-address" in system_info.get("system", {}):
                mgmt_ip_host = system_info["system"]["ip-address"]
            elif "mgmt-ip" in system_info.get("system", {}):
                mgmt_ip_host = system_info["system"]["mgmt-ip"]
            else:
                raise ValueError("Management IP not found in system info")
            if "netmask" in system_info.get("system", {}):
                mgmt_netmask = system_info["system"]["netmask"]
            else:
                mgmt_netmask = "32"
            interface = IPv4Interface(f"{mgmt_ip_host}/{mgmt_netmask}")
            mgmt_ip = interface.with_prefixlen
        except Exception as err:
            self.job.logger.warning(f"Failed to determine management IP for {firewall}, {err}")
            mgmt_ip = None

        return mgmt_interface_name, mgmt_ip
