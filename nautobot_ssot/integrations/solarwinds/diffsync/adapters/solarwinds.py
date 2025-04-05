"""Nautobot SSoT SolarWinds Adapter for SolarWinds SSoT app."""

import json
from datetime import datetime
from typing import Dict, List, Optional

from diffsync import Adapter, DiffSyncModel
from diffsync.enum import DiffSyncModelFlags
from netutils.ip import ipaddress_interface, is_ip_within
from netutils.mac import mac_to_format

from nautobot_ssot.integrations.solarwinds.diffsync.models.solarwinds import (
    SolarWindsDevice,
    SolarWindsDeviceType,
    SolarWindsInterface,
    SolarWindsIPAddress,
    SolarWindsIPAddressToInterface,
    SolarWindsLocation,
    SolarWindsManufacturer,
    SolarWindsPlatform,
    SolarWindsPrefix,
    SolarWindsRole,
    SolarWindsSoftwareVersion,
)
from nautobot_ssot.integrations.solarwinds.utils.solarwinds import (
    SolarWindsClient,
    determine_role_from_devicetype,
    determine_role_from_hostname,
)


class SolarWindsAdapter(Adapter):  # pylint: disable=too-many-instance-attributes
    """DiffSync adapter for SolarWinds."""

    location = SolarWindsLocation
    platform = SolarWindsPlatform
    role = SolarWindsRole
    manufacturer = SolarWindsManufacturer
    device_type = SolarWindsDeviceType
    softwareversion = SolarWindsSoftwareVersion
    device = SolarWindsDevice
    interface = SolarWindsInterface
    prefix = SolarWindsPrefix
    ipaddress = SolarWindsIPAddress
    ipassignment = SolarWindsIPAddressToInterface

    top_level = [
        "location",
        "manufacturer",
        "platform",
        "role",
        "softwareversion",
        "device",
        "prefix",
        "ipaddress",
        "ipassignment",
    ]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        client: SolarWindsClient,
        containers,
        location_type,
        job,
        sync=None,
        parent=None,
        tenant=None,
    ):
        """Initialize SolarWinds.

        Args:
            job (object, optional): SolarWinds job. Defaults to None.
            sync (object, optional): SolarWindsDataSource Sync. Defaults to None.
            client (SolarWindsClient): SolarWinds API client connection object.
            containers (str): Concatenated string of Container names to be imported. Will be 'ALL' for all containers.
            location_type (LocationType): The LocationType to create containers as in Nautobot.
            parent (Location, optional): The parent Location to assign created containers to in Nautobot.
            tenant (Tenant, optional): The Tenant to associate with Devices and IPAM data.
        """
        super().__init__()
        self.job = job
        self.sync = sync
        self.conn = client
        self.containers = containers
        self.location_type = location_type
        self.parent = parent
        self.tenant = tenant
        self.failed_devices = []

    def load(self):  # pylint: disable=too-many-locals, too-many-branches, too-many-statements
        """Load data from SolarWinds into DiffSync models."""
        self.job.logger.info("Loading data from SolarWinds.")

        if self.parent:
            self.load_parent()

        container_nodes = self.get_container_nodes(custom_property=self.job.custom_property)

        self.load_sites(container_nodes)

        node_details = {}
        for container_name, nodes in container_nodes.items():  # pylint: disable=too-many-nested-blocks
            self.job.logger.debug(f"Retrieving node details from SolarWinds for {container_name}.")
            node_details = self.conn.build_node_details(nodes=nodes)
            for node in node_details.values():
                device_type = self.conn.standardize_device_type(node=node)
                role = self.determine_device_role(node, device_type)
                self.load_role(role)
                if device_type:
                    platform_name = self.load_platform(device_type, manufacturer=node.get("Vendor"))
                    if platform_name == "UNKNOWN":
                        self.job.logger.error(f"Can't determine platform for {node['NodeHostname']} so skipping load.")
                        self.failed_devices.append({**node, **{"error": "Unable to determine Platform."}})
                        continue
                    if node.get("Vendor") and node["Vendor"] != "net-snmp":
                        self.load_manufacturer_and_device_type(manufacturer=node["Vendor"], device_type=device_type)
                        version = self.conn.extract_version(version=node["Version"]) if node.get("Version") else ""
                        if version:
                            self.get_or_instantiate(
                                self.softwareversion,
                                ids={"version": version, "platform__name": platform_name, "status__name": "Active"},
                                attrs={},
                            )
                        new_dev, loaded = self.get_or_instantiate(
                            self.device,
                            ids={
                                "name": node["NodeHostname"],
                            },
                            attrs={
                                "device_type__manufacturer__name": node["Vendor"],
                                "device_type__model": device_type,
                                "location__name": container_name,
                                "location__location_type__name": self.location_type.name,
                                "platform__name": platform_name,
                                "role__name": role,
                                "snmp_location": node["SNMPLocation"] if node.get("SNMPLocation") else None,
                                "software_version__version": version if version else None,
                                "software_version__platform__name": platform_name if version else None,
                                "last_synced_from_sor": datetime.today().date().isoformat(),
                                "status__name": "Active",
                                "serial": node["ServiceTag"] if node.get("ServiceTag") else "",
                                "tenant__name": self.tenant.name if self.tenant else None,
                                "system_of_record": "SolarWinds",
                            },
                        )
                        if loaded:
                            if node.get("interfaces"):
                                self.load_interfaces(device=new_dev, intfs=node["interfaces"])
                            if not node.get("ipaddrs") or (
                                node.get("ipaddrs") and node["IPAddress"] not in node["ipaddrs"]
                            ):
                                prefix = ipaddress_interface(
                                    ip=f"{node['IPAddress']}/{node['PFLength']}", attr="network"
                                ).with_prefixlen
                                self.load_prefix(network=prefix)
                                self.load_ipaddress(
                                    addr=node["IPAddress"],
                                    prefix_length=node["PFLength"],
                                    prefix=prefix,
                                    addr_type="IPv6" if ":" in node["IPAddress"] else "IPv4",
                                )
                                self.load_interfaces(
                                    device=new_dev,
                                    intfs={1: {"Name": "Management", "Enabled": "Up", "Status": "Up"}},
                                )
                                self.load_ipassignment(
                                    addr=node["IPAddress"],
                                    dev_name=new_dev.name,
                                    intf_name="Management",
                                    addr_type="IPv6" if ":" in node["IPAddress"] else "IPv4",
                                    mgmt_addr=node["IPAddress"],
                                )
                            if node.get("ipaddrs"):
                                for _, ipaddr in node["ipaddrs"].items():
                                    pf_len = ipaddr["SubnetMask"]
                                    prefix = ipaddress_interface(
                                        f"{ipaddr['IPAddress']}/{pf_len}", "network"
                                    ).with_prefixlen
                                    self.load_prefix(network=prefix)
                                    self.load_ipaddress(
                                        addr=ipaddr["IPAddress"],
                                        prefix_length=pf_len,
                                        prefix=prefix,
                                        addr_type=ipaddr["IPAddressType"],
                                    )
                                    if ipaddr["IntfName"] not in node["interfaces"]:
                                        self.load_interfaces(
                                            device=new_dev,
                                            intfs={1: {"Name": ipaddr["IntfName"], "Enabled": "Up", "Status": "Up"}},
                                        )
                                    self.load_ipassignment(
                                        addr=ipaddr["IPAddress"],
                                        dev_name=new_dev.name,
                                        intf_name=ipaddr["IntfName"],
                                        addr_type=ipaddr["IPAddressType"],
                                        mgmt_addr=node["IPAddress"],
                                    )
                else:
                    if node.get("Vendor") and node["Vendor"] == "net-snmp":
                        self.job.logger.error(f"{node['NodeHostname']} is showing as net-snmp so won't be imported.")
                    else:
                        self.job.logger.error(f"{node['NodeHostname']} is missing DeviceType so won't be imported.")
                    self.failed_devices.append({**node, **{"error": "Unable to determine DeviceType."}})

        self.reprocess_ip_parent_prefixes()
        if node_details and self.job.debug:
            self.job.logger.debug(f"Node details: {json.dumps(node_details, indent=2)}")
        if self.failed_devices:
            self.job.logger.warning(
                f"List of {len(self.failed_devices)} devices that were unable to be loaded. {json.dumps(self.failed_devices, indent=2)}"
            )

    def load_manufacturer_and_device_type(self, manufacturer: str, device_type: str):
        """Load Manufacturer and DeviceType into DiffSync models.

        Args:
            manufacturer (str): Name of manufacturer to be loaded.
            device_type (str): DeviceType to be loaded.
        """
        manu, _ = self.get_or_instantiate(self.manufacturer, ids={"name": manufacturer}, attrs={})
        new_dt, loaded = self.get_or_instantiate(
            self.device_type,
            ids={"model": device_type, "manufacturer__name": manufacturer},
            attrs={},
        )
        if loaded:
            manu.add_child(new_dt)

    def get_container_nodes(self, custom_property=None):
        """Gather container nodes for all specified containers from SolarWinds."""
        container_ids, container_nodes = {}, {}
        if self.containers != "ALL":
            container_ids = self.conn.get_filtered_container_ids(containers=self.containers)
        else:
            container_ids = self.conn.get_top_level_containers(top_container=self.job.top_container)
        container_nodes = self.conn.get_container_nodes(
            container_ids=container_ids,
            custom_property=custom_property,
            location_name=self.job.location_override.name if self.job.location_override else None,
        )
        return container_nodes

    def load_location(  # pylint: disable=too-many-arguments
        self,
        loc_name: str,
        location_type: str,
        status: str,
        parent_name: Optional[str] = None,
        parent_type: Optional[str] = None,
        parent_parent_name: Optional[str] = None,
        parent_parent_type: Optional[str] = None,
    ) -> tuple:
        """Load location into DiffSync model.

        Args:
            loc_name (str): Location name to load.
            location_type (str): LocationType for Location to be loaded.
            parent_name (str, optional): Name for parent of Location. Defaults to None.
            parent_type (str, optional): LocationType for parent of Location. Defaults to None.
            parent_parent_name (str, optional): Name for parent of parent of Location. Defaults to None.
            parent_parent_type (str, optional): LocationType for parent of parent of Location. Defaults to None.
            status (str): Status of Location to be loaded.

        Returns:
            tuple: Location DiffSync model and if it was loaded.
        """
        location, loaded = self.get_or_instantiate(
            self.location,
            ids={
                "name": loc_name,
                "location_type__name": location_type,
                "parent__name": parent_name,
                "parent__location_type__name": parent_type,
                "parent__parent__name": parent_parent_name,
                "parent__parent__location_type__name": parent_parent_type,
            },
            attrs={"status__name": status},
        )

        return (location, loaded)

    def load_parent(self):
        """Function to load parent Location into Location DiffSync model."""
        parent, loaded = self.load_location(
            loc_name=self.parent.name,
            location_type=self.parent.location_type.name,
            status=self.parent.status.name,
            parent_name=self.parent.parent.name if self.parent and self.parent.parent else None,
            parent_type=self.parent.parent.location_type.name if self.parent and self.parent.parent else None,
            parent_parent_name=(
                self.parent.parent.parent.name
                if self.parent and self.parent.parent and self.parent.parent.parent
                else None
            ),
            parent_parent_type=(
                self.parent.parent.parent.location_type.name
                if self.parent and self.parent.parent and self.parent.parent.parent
                else None
            ),
        )
        if loaded:
            parent.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    def load_sites(self, container_nodes: Dict[str, List[dict]]):
        """Load containers as LocationType into Location DiffSync models.

        Args:
            container_nodes (Dict[str, List[dict]]): Dictionary of Container to list of dictionaries containing nodes within that container.
        """
        for container_name, node_list in container_nodes.items():
            self.job.logger.debug(f"Found {len(node_list)} nodes for {container_name} container.")
            self.load_location(
                loc_name=container_name,
                location_type=self.location_type.name,
                parent_name=self.parent.name if self.parent else None,
                parent_type=self.parent.location_type.name if self.parent else None,
                parent_parent_name=self.parent.parent.name if self.parent and self.parent.parent else None,
                parent_parent_type=(
                    self.parent.parent.location_type.name if self.parent and self.parent.parent else None
                ),
                status="Active",
            )

    def determine_device_role(self, node: dict, device_type: str) -> str:
        """Determine Device Role based upon role_choice setting.

        Args:
            node (dict): Dictionary of Node details.
            device_type (str): DeviceType model.

        Returns:
            str: Device Role from DeviceType, Hostname, or default Role.
        """
        role = ""
        if self.job.role_map and self.job.role_choice == "DeviceType":
            role = determine_role_from_devicetype(device_type=device_type, role_map=self.job.role_map)
        if self.job.role_map and self.job.role_choice == "Hostname":
            role = determine_role_from_hostname(hostname=node["NodeHostname"], role_map=self.job.role_map)
        if not role:
            role = self.job.default_role.name
        return role

    def load_role(self, role):
        """Load passed Role into DiffSync model."""
        self.get_or_instantiate(
            self.role, ids={"name": role}, attrs={"content_types": [{"app_label": "dcim", "model": "device"}]}
        )

    def load_platform(self, device_type: str, manufacturer: str):
        """Load Platform into DiffSync model based upon DeviceType.

        Args:
            device_type (str): DeviceType name for associated Platform.
            manufacturer (str): Manufacturer name for associated Platform.
        """
        platform = "UNKNOWN"
        if "Aruba" in manufacturer:
            if device_type.startswith(("1", "60", "61", "62", "63", "64", "8", "93", "94")):
                self.get_or_instantiate(
                    self.platform,
                    ids={"name": "arubanetworks.aos.aoscx", "manufacturer__name": manufacturer},
                    attrs={"network_driver": "aruba_aoscx", "napalm_driver": ""},
                )
                platform = "arubanetworks.aos.aoscx"
            elif device_type.startswith(("AP", "MC", "MM", "7", "90", "91", "92")):
                self.get_or_instantiate(
                    self.platform,
                    ids={"name": "arubanetworks.aos.os", "manufacturer__name": manufacturer},
                    attrs={"network_driver": "aruba_os", "napalm_driver": ""},
                )
                platform = "arubanetworks.aos.os"
            elif device_type.startswith(("25", "29", "38", "54")):
                self.get_or_instantiate(
                    self.platform,
                    ids={"name": "arubanetworks.aos.osswitch", "manufacturer__name": manufacturer},
                    attrs={"network_driver": "aruba_osswitch", "napalm_driver": ""},
                )
                platform = "arubanetworks.aos.osswitch"

        if "Cisco" in manufacturer:
            if device_type.startswith("85"):
                if "wireless" in device_type.lower() or "wlc" in device_type.lower():
                    self.get_or_instantiate(
                        self.platform,
                        ids={"name": "cisco.ios.aireos", "manufacturer__name": manufacturer},
                        attrs={"network_driver": "cisco_aireos", "napalm_driver": ""},
                    )
                platform = "cisco.ios.aireos"
            elif not device_type.startswith("N"):
                self.get_or_instantiate(
                    self.platform,
                    ids={"name": "cisco.ios.ios", "manufacturer__name": manufacturer},
                    attrs={"network_driver": "cisco_ios", "napalm_driver": "ios"},
                )
                platform = "cisco.ios.ios"
            elif device_type.startswith("N"):
                self.get_or_instantiate(
                    self.platform,
                    ids={"name": "cisco.nxos.nxos", "manufacturer__name": manufacturer},
                    attrs={"network_driver": "cisco_nxos", "napalm_driver": "nxos"},
                )
                platform = "cisco.nxos.nxos"
        elif "Palo" in manufacturer:
            self.get_or_instantiate(
                self.platform,
                ids={"name": "paloaltonetworks.panos.panos", "manufacturer__name": manufacturer},
                attrs={"network_driver": "paloalto_panos", "napalm_driver": ""},
            )
            platform = "paloaltonetworks.panos.panos"

        return platform

    def load_interfaces(self, device: DiffSyncModel, intfs: dict) -> None:
        """Load interfaces for passed device.

        Args:
            device (DiffSyncModel): DiffSync Device model that's been loaded.
            intfs (dict): Interface data for Device.
        """
        for _, intf in intfs.items():
            new_intf, loaded = self.get_or_instantiate(
                self.interface,
                ids={"name": intf["Name"], "device__name": device.name},
                attrs={
                    "enabled": bool(intf["Enabled"] == "Up"),
                    "mac_address": mac_to_format(intf["MAC"], "MAC_COLON_TWO") if intf.get("MAC") else None,
                    "mtu": intf["MTU"] if intf.get("MTU") else 1500,
                    "type": self.conn.determine_interface_type(interface=intf),
                    "status__name": "Active" if intf["Status"] == "Up" else "Failed",
                },
            )
            if loaded:
                device.add_child(new_intf)

    def reprocess_ip_parent_prefixes(self) -> None:
        """Check for an existing more specific prefix.

        Runs after loading all data to ensure IP's have appropriate parent prefixes.
        """
        for ipaddr in self.get_all(obj="ipaddress"):
            parent_subnet = f"{ipaddr.parent__network}/{ipaddr.parent__prefix_length}"
            for prefix in self.get_all(obj="prefix"):
                if not prefix.namespace__name == ipaddr.parent__namespace__name:
                    continue
                subnet = f"{prefix.network}/{prefix.prefix_length}"
                if not is_ip_within(parent_subnet, subnet):
                    if is_ip_within(ipaddr.host, subnet):
                        if self.job.debug:
                            self.job.logger.debug(
                                "More specific subnet %s found for IP %s/%s", subnet, ipaddr.host, ipaddr.mask_length
                            )
                        ipaddr.parent__network = prefix.network
                        ipaddr.parent__prefix_length = prefix.prefix_length
                        self.update(ipaddr)

    def load_prefix(self, network: str) -> None:
        """Load Prefix for passed network.

        Args:
            network (str): Prefix network to be loaded.
        """
        self.get_or_instantiate(
            self.prefix,
            ids={
                "network": network.split("/")[0],
                "prefix_length": network.split("/")[1],
                "namespace__name": self.tenant.name if self.tenant else "Global",
            },
            attrs={
                "status__name": "Active",
                "tenant__name": self.tenant.name if self.tenant else None,
                "last_synced_from_sor": datetime.today().date().isoformat(),
                "system_of_record": "SolarWinds",
            },
        )

    def load_ipaddress(self, addr: str, prefix_length: int, prefix: str, addr_type: str) -> None:
        """Load IPAddress for passed address.

        Args:
            addr (str): Host for IPAddress.
            prefix_length (int): Prefix length for IPAddress.
            prefix (str): Parent prefix CIDR for IPAddress.
            addr_type (str): Either "IPv4" or "IPv6"
        """
        self.get_or_instantiate(
            self.ipaddress,
            ids={
                "host": addr,
                "parent__network": prefix.split("/")[0],
                "parent__prefix_length": prefix_length,
                "parent__namespace__name": self.tenant.name if self.tenant else "Global",
            },
            attrs={
                "mask_length": prefix_length,
                "status__name": "Active",
                "ip_version": 4 if addr_type == "IPv4" else 6,
                "tenant__name": self.tenant.name if self.tenant else None,
                "last_synced_from_sor": datetime.today().date().isoformat(),
                "system_of_record": "SolarWinds",
            },
        )

    def load_ipassignment(  # pylint: disable=too-many-arguments
        self,
        addr: str,
        dev_name: str,
        intf_name: str,
        addr_type: str,
        mgmt_addr: str,
    ) -> None:
        """Load IPAddress for passed address.

        Args:
            addr (str): Host for IPAddress.
            dev_name (str): Device name for associated Interface.
            intf_name (str): Interface name to associate IPAddress to.
            addr_type (str): Either "IPv4" or "IPv6"
            mgmt_addr (str): Management IP Address for Device.
        """
        self.get_or_instantiate(
            self.ipassignment,
            ids={"interface__device__name": dev_name, "interface__name": intf_name, "ip_address__host": addr},
            attrs={
                "interface__device__primary_ip4__host": mgmt_addr if addr_type == "IPv4" else None,
                "interface__device__primary_ip6__host": mgmt_addr if addr_type == "IPv6" else None,
            },
        )
