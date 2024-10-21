"""Nautobot SSoT for Meraki Adapter for Meraki SSoT plugin."""

from diffsync import Adapter, DiffSyncModel
from diffsync.exceptions import ObjectNotFound
from netutils.ip import ipaddress_interface, netmask_to_cidr

from nautobot_ssot.exceptions import JobException
from nautobot_ssot.integrations.meraki.diffsync.models.meraki import (
    MerakiDevice,
    MerakiHardware,
    MerakiIPAddress,
    MerakiIPAssignment,
    MerakiNetwork,
    MerakiOSVersion,
    MerakiPort,
    MerakiPrefix,
)
from nautobot_ssot.integrations.meraki.utils.meraki import get_role_from_devicetype, parse_hostname_for_role


class MerakiAdapter(Adapter):
    """DiffSync adapter for Meraki."""

    network = MerakiNetwork
    hardware = MerakiHardware
    osversion = MerakiOSVersion
    device = MerakiDevice
    port = MerakiPort
    prefix = MerakiPrefix
    ipaddress = MerakiIPAddress
    ipassignment = MerakiIPAssignment

    top_level = ["network", "hardware", "osversion", "device", "prefix", "ipaddress", "ipassignment"]

    def __init__(self, job, sync, client, tenant=None):
        """Initialize Meraki.

        Args:
            job (object): Meraki SSoT job.
            sync (object): Meraki DiffSync.
            client (object): Meraki API client connection object.
            tenant (object): Tenant specified in Job form to attach to imported Devices.
        """
        super().__init__()
        self.job = job
        self.sync = sync
        self.conn = client
        self.tenant = tenant
        self.device_map = {}
        self.org_uplink_statuses = self.conn.get_org_uplink_statuses()

    def load_networks(self):
        """Load networks from Meraki dashboard into DiffSync models."""
        for net in self.conn.get_org_networks():
            parent_name = None
            if self.job.network_loctype.parent:
                if self.job.parent_location:
                    parent_name = self.job.parent_location.name
                elif self.job.location_map and net in self.job.location_map:
                    parent_name = self.job.location_map[net]["parent"]
                else:
                    self.job.logger.error(
                        f"Parent Location is required for {self.job.network_loctype.name} but can't determine parent to be assigned to {net}."
                    )
                    continue
            self.get_or_instantiate(
                self.network,
                ids={"name": net["name"], "parent": parent_name},
                attrs={
                    "timezone": net["timeZone"],
                    "notes": net["notes"].rstrip() if net.get("notes") else "",
                    "tags": net["tags"],
                    "tenant": self.tenant.name if self.tenant else None,
                    "uuid": None,
                },
            )

    def load_devices(self):  # pylint: disable=too-many-branches
        """Load devices from Meraki dashboard into DiffSync models."""
        self.device_map = {dev["name"]: dev for dev in self.conn.get_org_devices()}
        statuses = self.conn.get_org_device_statuses()
        status = "Offline"
        for dev in self.device_map.values():
            if dev.get("name"):
                if dev["name"] in statuses:
                    if statuses[dev["name"]] == "online":
                        status = "Active"
                try:
                    self.get(self.device, dev["name"])
                    self.job.logger.warning(f"Duplicate device {dev['name']} found and being skipped.")
                except ObjectNotFound:
                    if self.job.hostname_mapping and len(self.job.hostname_mapping) > 0:
                        if self.job.debug:
                            self.job.logger.debug(f"Parsing hostname for device {dev['name']} to determine role.")
                        role = parse_hostname_for_role(dev_hostname=dev["name"], hostname_map=self.job.hostname_mapping)
                    elif self.job.devicetype_mapping and len(self.job.devicetype_mapping) > 0:
                        if self.job.debug:
                            self.job.logger.debug(f"Parsing device model for device {dev['name']} to determine role.")
                        role = get_role_from_devicetype(
                            dev_model=dev["model"], devicetype_map=self.job.devicetype_mapping
                        )
                    else:
                        role = "Unknown"
                    self.load_hardware_model(device_info=dev)
                    self.get_or_instantiate(self.osversion, ids={"version": dev["firmware"]})
                    new_dev, loaded = self.get_or_instantiate(
                        self.device,
                        ids={"name": dev["name"]},
                        attrs={
                            "controller_group": self.job.instance.controller_managed_device_groups.first().name
                            if self.job.instance.controller_managed_device_groups.count() != 0
                            else "",
                            "notes": dev["notes"].rstrip(),
                            "serial": dev["serial"],
                            "status": status,
                            "role": role,
                            "model": dev["model"],
                            "network": self.conn.network_map[dev["networkId"]]["name"],
                            "tenant": self.tenant.name if self.tenant else None,
                            "uuid": None,
                            "version": dev["firmware"],
                        },
                    )
                    if loaded:
                        if dev["model"].startswith(("MX", "MG", "Z")):
                            self.load_firewall_ports(device=new_dev, serial=dev["serial"], network_id=dev["networkId"])
                        if dev["model"].startswith("MS"):
                            self.load_switch_ports(device=new_dev, serial=dev["serial"])
                        if dev["model"].startswith("MR"):
                            self.load_ap_ports(device=new_dev, serial=dev["serial"])
            else:
                self.job.logger.warning(f"Device serial {dev['serial']} is missing hostname so will be skipped.")

    def load_hardware_model(self, device_info: dict):
        """Load hardware model from device information."""
        try:
            self.get(self.hardware, device_info["model"])
        except ObjectNotFound:
            new_hardware = self.hardware(
                model=device_info["model"],
                uuid=None,
            )
            self.add(new_hardware)

    def load_firewall_ports(self, device: DiffSyncModel, serial: str, network_id: str):  # pylint: disable=too-many-locals
        """Load ports of a firewall, cellular, or teleworker device from Meraki dashboard into DiffSync models."""
        mgmt_ports = self.conn.get_management_ports(serial=serial)
        uplink_settings = self.conn.get_uplink_settings(serial=serial)
        lan_ports = self.conn.get_appliance_switchports(network_id=network_id)

        # keep track of whether a primary IP has already been found since we can only assign one
        primary_found = False
        for port in mgmt_ports.keys():
            uplink_status = "Planned"
            if serial in self.org_uplink_statuses:
                uplinks = self.org_uplink_statuses[serial]["uplinks"]
                for link in uplinks:
                    if link["interface"] == port and link["status"] == "active":
                        uplink_status = "Active"
            port_uplink_settings = uplink_settings[port]
            new_port, loaded = self.get_or_instantiate(
                self.port,
                ids={"name": port, "device": device.name},
                attrs={
                    "management": True,
                    "enabled": port_uplink_settings["enabled"],
                    "port_type": "1000base-t",
                    "port_status": uplink_status,
                    "tagging": port_uplink_settings["vlanTagging"]["enabled"],
                    "uuid": None,
                },
            )
            if loaded:
                self.add(new_port)
                device.add_child(new_port)
                if port_uplink_settings["svis"]["ipv4"]["assignmentMode"] == "static":
                    port_svis = port_uplink_settings["svis"]["ipv4"]
                    prefix = ipaddress_interface(ip=port_svis["address"], attr="network.with_prefixlen")
                    self.load_prefix(
                        location=self.conn.network_map[network_id]["name"],
                        prefix=prefix,
                    )
                    self.load_ipaddress(
                        address=port_svis["address"],
                        prefix=prefix,
                    )
                    self.load_ipassignment(
                        address=port_svis["address"],
                        dev_name=device.name,
                        port=port,
                        primary=bool(uplink_status == "Active" and not primary_found),
                    )
                if uplink_status == "Active":
                    primary_found = True
        if lan_ports:
            self.process_lan_ports(device, lan_ports)

    def process_lan_ports(self, device: DiffSyncModel, lan_ports: dict):
        """Load the switchports for a Device into DiffSync models.

        Args:
            device (DiffSyncModel): Loaded Device DiffSyncModel to associate with Port to be loaded.
            lan_ports (dict): Dictionary of switchport data.
        """
        for port in lan_ports:
            new_port, loaded = self.get_or_instantiate(
                self.port,
                ids={"name": str(port["number"]), "device": device.name},
                attrs={
                    "management": False,
                    "enabled": port["enabled"],
                    "port_type": "1000base-t",
                    "port_status": "Active",
                    "tagging": bool(port["type"] == "trunk"),
                    "uuid": None,
                },
            )
            if loaded:
                self.add(new_port)
                device.add_child(new_port)

    def load_switch_ports(self, device: DiffSyncModel, serial: str):
        """Load ports of a switch device from Meraki dashboard into DiffSync models."""
        mgmt_ports = self.conn.get_management_ports(serial=serial)
        org_switchports = self.conn.get_org_switchports()

        for port in mgmt_ports.keys():
            try:
                self.get(self.port, {"name": port, "device": device.name})
            except ObjectNotFound:
                mgmt_port = self.port(
                    name=port,
                    device=device.name,
                    management=True,
                    enabled=True,
                    port_type="1000base-t",
                    port_status="Active",
                    tagging=False,
                    uuid=None,
                )
                self.add(mgmt_port)
                device.add_child(mgmt_port)
                if mgmt_ports[port].get("usingStaticIp"):
                    prefix = ipaddress_interface(
                        ip=f"{mgmt_ports[port]['staticIp']}/{netmask_to_cidr(netmask=mgmt_ports[port]['staticSubnetMask'])}",
                        attr="network.with_prefixlen",
                    )
                    self.load_prefix(
                        location=self.conn.network_map[self.device_map[device.name]["networkId"]]["name"],
                        prefix=prefix,
                    )
                    self.load_ipaddress(
                        address=f"{mgmt_ports[port]['staticIp']}/{netmask_to_cidr(mgmt_ports[port]['staticSubnetMask'])}",
                        prefix=prefix,
                    )
                    self.load_ipassignment(
                        address=f"{mgmt_ports[port]['staticIp']}/{netmask_to_cidr(mgmt_ports[port]['staticSubnetMask'])}",
                        dev_name=device.name,
                        port=port,
                        primary=True,
                    )
        if serial in org_switchports:
            for port in org_switchports[serial]["ports"]:
                new_port = self.port(
                    name=port["portId"],
                    device=device.name,
                    management=False,
                    enabled=port["enabled"],
                    port_type="1000base-t",
                    port_status="Active",
                    tagging=bool(port["type"] == "trunk"),
                    uuid=None,
                )
                self.add(new_port)
                device.add_child(new_port)

    def load_ap_ports(self, device: DiffSyncModel, serial: str):
        """Load ports of a MR device from Meraki dashboard into DiffSync models."""
        mgmt_ports = self.conn.get_management_ports(serial=serial)

        for port in mgmt_ports.keys():
            try:
                self.get(self.port, {"name": port, "device": device.name})
            except ObjectNotFound:
                new_port = self.port(
                    name=port,
                    device=device.name,
                    management=True,
                    enabled=True,
                    port_type="1000base-t",
                    port_status="Active",
                    tagging=False,
                    uuid=None,
                )
                self.add(new_port)
                device.add_child(new_port)
                if mgmt_ports[port].get("usingStaticIp"):
                    prefix = ipaddress_interface(
                        ip=f"{mgmt_ports[port]['staticIp']}/{netmask_to_cidr(netmask=mgmt_ports[port]['staticSubnetMask'])}",
                        attr="network.with_prefixlen",
                    )
                    self.load_prefix(
                        location=self.conn.network_map[self.device_map[device.name]["networkId"]]["name"],
                        prefix=prefix,
                    )
                    self.load_ipaddress(
                        address=f"{mgmt_ports[port]['staticIp']}/{netmask_to_cidr(mgmt_ports[port]['staticSubnetMask'])}",
                        prefix=prefix,
                    )
                    self.load_ipassignment(
                        address=f"{mgmt_ports[port]['staticIp']}/{netmask_to_cidr(mgmt_ports[port]['staticSubnetMask'])}",
                        dev_name=device.name,
                        port=port,
                        primary=True,
                    )

    def load_prefix(self, location: str, prefix: str):
        """Load Prefixes of devices into DiffSync models."""
        if self.tenant:
            namespace = self.tenant.name
        else:
            namespace = "Global"
        try:
            self.get(self.prefix, {"prefix": prefix, "namespace": namespace})
        except ObjectNotFound:
            new_pf = self.prefix(
                prefix=prefix,
                location=location,
                namespace=namespace,
                tenant=self.tenant.name if self.tenant else None,
                uuid=None,
            )
            self.add(new_pf)

    def load_ipaddress(self, address: str, prefix: str):
        """Load IPAddresses of devices into DiffSync models."""
        try:
            self.get(self.ipaddress, {"address": address, "prefix": prefix})
        except ObjectNotFound:
            new_ip = self.ipaddress(
                address=address,
                prefix=prefix,
                tenant=self.tenant.name if self.tenant else None,
                uuid=None,
            )
            self.add(new_ip)

    def load_ipassignment(self, address: str, dev_name: str, port: str, primary: bool):
        """Load IPAddressesToInterface of devices into DiffSync models."""
        namespace = self.tenant.name if self.tenant else "Global"
        try:
            self.get(self.ipassignment, {"address": address, "device": dev_name, "namespace": namespace, "port": port})
        except ObjectNotFound:
            new_map = self.ipassignment(
                address=address,
                namespace=namespace,
                device=dev_name,
                port=port,
                primary=primary,
                uuid=None,
            )
            self.add(new_map)

    def load(self):
        """Load data from Meraki into DiffSync models."""
        if self.conn.validate_organization_exists():
            self.load_networks()
            self.load_devices()
        else:
            self.job.logger.error("Specified organization ID not found in Meraki dashboard.")
            raise JobException("Incorrect Organization ID specified.")
