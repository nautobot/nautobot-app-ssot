"""Adapter for Proxmox VE objects."""

#  pylint: disable=too-many-arguments
#  pylint: disable=too-many-branches
#  pylint: disable=too-many-locals
import ipaddress
import re
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

from diffsync import Adapter
from nautobot.dcim.choices import InterfaceTypeChoices

from nautobot_ssot.integrations.proxmox.constants import (
    ACTIVE_STATUS_NAME,
    GLOBAL_NAMESPACE_NAME,
    NETWORK_PREFIX_TYPE,
    NODE_INTERFACE_TYPE_MAP,
    get_ssot_tag_name,
)
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

MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


def create_ipaddr(address: str) -> Union[ipaddress.IPv4Address, ipaddress.IPv6Address]:
    """Create an IPv4 or IPv6 address object from a string.

    Args:
        address (str): The IP address string to parse.

    Returns:
        Union[ipaddress.IPv4Address, ipaddress.IPv6Address]: The parsed address object.
    """
    try:
        ip_address = ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError:
        ip_address = ipaddress.IPv6Address(address)
    return ip_address


def parse_net_config(net_string: str) -> Dict[str, str]:
    """Parse a Proxmox ``netN`` config string into a dict of key/value pairs.

    QEMU example: ``virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0,tag=10``
    LXC example:  ``name=eth0,bridge=vmbr0,hwaddr=AA:BB:CC:DD:EE:FF,ip=10.0.0.5/24,gw=10.0.0.1``

    Args:
        net_string (str): The raw Proxmox ``netN`` configuration string.

    Returns:
        dict: The parsed key/value pairs from the config string.
    """
    parts = {}
    for item in net_string.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key.strip()] = value.strip()
    return parts


def mac_from_net_parts(parts: Dict[str, str]) -> Optional[str]:
    """Return the MAC address from parsed ``netN`` parts (QEMU model= value or LXC hwaddr=).

    Args:
        parts (dict): The parsed ``netN`` key/value pairs from :func:`parse_net_config`.

    Returns:
        Optional[str]: The MAC address if found, otherwise ``None``.
    """
    if parts.get("hwaddr"):
        return parts["hwaddr"]
    for value in parts.values():
        if MAC_RE.match(value):
            return value
    return None


def bytes_to_mb(value: Optional[int]) -> Optional[int]:
    """Convert a byte count to whole MB (Nautobot VirtualMachine.memory is in MB).

    Args:
        value (Optional[int]): The byte count to convert.

    Returns:
        Optional[int]: The value in whole MB, or ``None`` if ``value`` is falsy.
    """
    return int(value / 1024**2) if value else None


def bytes_to_gb(value: Optional[int]) -> Optional[int]:
    """Convert a byte count to whole GB (Nautobot VirtualMachine.disk is in GB).

    Args:
        value (Optional[int]): The byte count to convert.

    Returns:
        Optional[int]: The value in whole GB, or ``None`` if ``value`` is falsy.
    """
    return int(value / 1024**3) if value else None


class ProxmoxDiffSync(Adapter):
    """Proxmox VE adapter for DiffSync."""

    tag = TagModel
    clustergroup = ClusterGroupModel
    cluster = ClusterModel
    device = DeviceModel
    device_interface = DeviceInterfaceModel
    virtual_machine = VirtualMachineModel
    interface = VMInterfaceModel
    ip_address = IPAddressModel
    prefix = PrefixModel

    top_level = ["tag", "prefix", "clustergroup", "device", "virtual_machine", "ip_address"]

    def __init__(self, *args, job=None, sync=None, client, config, cluster_filters, **kwargs):
        """Initialize the ProxmoxDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        self.config = config
        self.cluster_filters = cluster_filters
        self.ip_address_map = {}
        # Maps Proxmox node name -> Device name (identical here, but kept explicit for linkage).
        self.node_device_map = {}
        # Maps Proxmox node name -> management IP (from /cluster/status), used to pick the node primary IP.
        self.node_mgmt_ip = {}
        self.cluster_name = None

    def load_clusters(self) -> None:
        """Load the Cluster Group and Cluster from Proxmox VE cluster status.

        Returns:
            None
        """
        status = self.client.get_cluster_status()
        cluster_entry = next((entry for entry in status if entry.get("type") == "cluster"), None)

        # Capture each node's management IP for primary-IP selection later.
        for entry in status:
            if entry.get("type") == "node" and entry.get("name") and entry.get("ip"):
                self.node_mgmt_ip[entry["name"]] = entry["ip"]

        if self.config.use_clusters and cluster_entry:
            self.cluster_name = cluster_entry["name"]
        else:
            self.cluster_name = self.config.default_cluster_name

        clustergroup_name = self.config.default_clustergroup_name
        diffsync_clustergroup, _ = self.get_or_instantiate(self.clustergroup, {"name": clustergroup_name})
        diffsync_cluster, _ = self.get_or_instantiate(
            self.cluster,
            {"name": self.cluster_name},
            {
                "cluster_type__name": self.config.default_cluster_type.name,
                "cluster_group__name": clustergroup_name,
            },
        )
        diffsync_clustergroup.add_child(diffsync_cluster)

    def load_nodes(self) -> None:
        """Load Proxmox VE nodes as Nautobot Devices.

        Returns:
            None
        """
        nodes = self.client.get_nodes()
        self.job.log_debug(message=f"Loading Proxmox VE nodes: {nodes}")
        for node in nodes:
            node_name = node.get("node")
            if not node_name:
                continue
            node_status = self.client.get_node_status(node_name)
            memory_total = (node_status.get("memory") or {}).get("total")
            diffsync_device, _ = self.get_or_instantiate(
                self.device,
                {"name": node_name},
                {
                    "device_type__model": self.config.default_device_type.model,
                    "role__name": self.config.default_device_role.name,
                    "location__name": self.config.default_location.name,
                    "status__name": ACTIVE_STATUS_NAME,
                    "clusters": [{"name": self.cluster_name}],
                    "pve_version": node_status.get("pveversion"),
                    "cpu_count": (node_status.get("cpuinfo") or {}).get("cpus"),
                    "memory_gb": bytes_to_gb(memory_total),
                },
            )
            self.node_device_map[node_name] = node_name
            self.load_node_interfaces(node_name, diffsync_device)

    def load_node_interfaces(self, node_name: str, diffsync_device: DeviceModel) -> None:
        """Load a node's network interfaces (with topology + IPs) as DCIM Interfaces on its Device.

        Args:
            node_name (str): The Proxmox VE node name.
            diffsync_device (DeviceModel): The node's Device DiffSync model.

        Returns:
            None
        """
        interfaces = self.client.get_node_network(node_name)
        self.job.log_debug(message=f"Loading network interfaces for node {node_name}: {interfaces}")

        # First pass: map each member interface to its bridge, bond, or VLAN parent.
        member_bridge, member_lag, member_parent = {}, {}, {}
        for entry in interfaces:
            iface_name = entry.get("iface")
            iface_type = entry.get("type")
            if iface_type in ("bridge", "OVSBridge"):
                for port in (entry.get("bridge_ports") or "").split():
                    member_bridge[port] = iface_name
            elif iface_type in ("bond", "OVSBond"):
                for slave in (entry.get("slaves") or "").split():
                    member_lag[slave] = iface_name
            if iface_type == "vlan":
                raw = entry.get("vlan-raw-device") or (iface_name.split(".")[0] if "." in iface_name else None)
                if raw and raw != iface_name:
                    member_parent[iface_name] = raw

        # Second pass: create the interfaces, their relationships, and their IPs.
        # The Proxmox-type → Nautobot-type mapping is configurable per SSOTProxmoxConfig; fall back to
        # the built-in default if the config field is empty.
        type_map = self.config.default_node_interface_type_map or NODE_INTERFACE_TYPE_MAP
        node_ipv4 = []
        for entry in interfaces:
            iface_name = entry.get("iface")
            if not iface_name:
                continue
            mtu = entry.get("mtu")
            diffsync_interface, _ = self.get_or_instantiate(
                self.device_interface,
                {"name": iface_name, "device__name": node_name},
                {
                    "type": type_map.get(entry.get("type"), InterfaceTypeChoices.TYPE_OTHER),
                    "enabled": bool(entry.get("active")),
                    "status__name": ACTIVE_STATUS_NAME,
                    "mtu": int(mtu) if mtu else None,
                    "bridge__name": member_bridge.get(iface_name),
                    "lag__name": member_lag.get(iface_name),
                    "parent_interface__name": member_parent.get(iface_name),
                },
            )
            diffsync_device.add_child(diffsync_interface)
            node_ipv4 += self._load_node_interface_ips(entry, iface_name, node_name)

        self._set_node_primary_ip(node_name, diffsync_device, node_ipv4)

    def _load_node_interface_ips(self, entry: dict, iface_name: str, node_name: str) -> List[ipaddress.IPv4Address]:
        """Record IPs configured on a node interface.

        Args:
            entry (dict): The Proxmox network entry for this interface.
            iface_name (str): The interface name.
            node_name (str): The Proxmox VE node name.

        Returns:
            List[ipaddress.IPv4Address]: The IPv4 addresses found on this interface.
        """
        ipv4_found = []
        assignment = {"name": iface_name, "device__name": node_name}
        for cidr_key in ("cidr", "cidr6"):
            cidr = entry.get(cidr_key)
            if cidr and "/" in cidr:
                host, _, prefix_length = cidr.partition("/")
                ipv4, _ = self._record_ip(host, int(prefix_length), "interfaces", assignment)
                ipv4_found += ipv4
        # Fallback for IPv4 entries that expose address + netmask but no cidr.
        if not entry.get("cidr") and entry.get("address") and entry.get("netmask"):
            netmask = entry["netmask"]
            try:
                prefix_length = bin(int(ipaddress.IPv4Address(netmask))).count("1")
            except ipaddress.AddressValueError:
                prefix_length = None
            if prefix_length is not None:
                ipv4, _ = self._record_ip(entry["address"], prefix_length, "interfaces", assignment)
                ipv4_found += ipv4
        return ipv4_found

    def _set_node_primary_ip(
        self, node_name: str, diffsync_device: DeviceModel, node_ipv4: List[ipaddress.IPv4Address]
    ) -> None:
        """Set the node Device's primary IPv4, preferring the cluster management IP.

        Args:
            node_name (str): The Proxmox VE node name.
            diffsync_device (DeviceModel): The node's Device DiffSync model.
            node_ipv4 (List[ipaddress.IPv4Address]): IPv4 addresses found on the node's interfaces.

        Returns:
            None
        """
        mgmt_ip = self.node_mgmt_ip.get(node_name)
        if mgmt_ip and any(str(addr) == mgmt_ip for addr in node_ipv4):
            diffsync_device.primary_ip4__host = mgmt_ip
        elif node_ipv4:
            node_ipv4.sort()
            diffsync_device.primary_ip4__host = str(node_ipv4[0])

    def _vm_tag_list(self, resource: dict) -> List[dict]:
        """Build the tag list for a VM, always including the SSoT tag.

        Args:
            resource (dict): The Proxmox VE VM/container resource entry.

        Returns:
            List[dict]: The tag identifiers to assign to the VM, sorted by name.
        """
        tags = [{"name": get_ssot_tag_name(self.config)}]
        if self.config.sync_proxmox_tags and resource.get("tags"):
            for raw_tag in re.split(r"[;,]", resource["tags"]):
                raw_tag = raw_tag.strip()
                if raw_tag:
                    self.get_or_instantiate(self.tag, {"name": raw_tag}, {"description": ""})
                    tags.append({"name": raw_tag})
        return sorted(tags, key=lambda item: item["name"].lower())

    def load_virtual_machines(self) -> None:
        """Load QEMU VMs (and LXC containers if enabled) from /cluster/resources.

        Returns:
            None
        """
        resources = self.client.get_resources(resource_type="vm")
        for resource in resources:
            resource_type = resource.get("type")
            if resource_type == "lxc" and not self.config.sync_lxc:
                continue
            if resource_type not in ("qemu", "lxc"):
                continue
            if resource.get("template"):
                self.job.log_debug(message=f"Skipping template {resource.get('name')}.")
                continue

            name = resource.get("name") or f"{resource_type}-{resource.get('vmid')}"
            node = resource.get("node")
            status_key = resource.get("status", "stopped")
            status_name = self.config.default_vm_status_map.get(status_key)
            if not status_name:
                self.job.logger.warning(f"Unknown Proxmox VM status '{status_key}' for {name}, skipping.")
                continue

            attrs = {
                "status__name": status_name,
                "vcpus": resource.get("maxcpu"),
                "memory": bytes_to_mb(resource.get("maxmem")),
                "disk": bytes_to_gb(resource.get("maxdisk")),
                "tags": self._vm_tag_list(resource),
            }
            # Link the VM to its host node Device via the custom relationship (only if nodes are synced).
            if self.config.sync_nodes_as_devices and node in self.node_device_map:
                attrs["host_device"] = {"name": self.node_device_map[node]}

            diffsync_vm, created = self.get_or_instantiate(
                self.virtual_machine,
                {"name": name, "cluster__name": self.cluster_name},
                attrs,
            )
            if not created:
                self.job.logger.warning(
                    f"Duplicate Virtual Machine name '{name}' in cluster '{self.cluster_name}'. Skipping duplicate."
                )
                continue

            self.load_vm_interfaces(resource, diffsync_vm)

    def load_vm_interfaces(self, resource: dict, diffsync_vm: VirtualMachineModel) -> None:
        """Load interfaces and IPs for a VM using the QEMU or LXC code path.

        Args:
            resource (dict): The Proxmox VE VM/container resource entry.
            diffsync_vm (VirtualMachineModel): The VM DiffSync model to attach interfaces to.

        Returns:
            None
        """
        node = resource.get("node")
        vmid = resource.get("vmid")
        resource_type = resource.get("type")

        if resource_type == "qemu":
            vm_config = self.client.get_qemu_config(node, vmid)
            agent_interfaces = []
            if resource.get("status") == "running":
                agent_interfaces = self.client.get_qemu_agent_interfaces(node, vmid)
            self._load_qemu_interfaces(vm_config, agent_interfaces, diffsync_vm)
        else:
            vm_config = self.client.get_lxc_config(node, vmid)
            self._load_lxc_interfaces(vm_config, diffsync_vm)

    def _instantiate_interface(self, name: str, mac: Optional[str], diffsync_vm: VirtualMachineModel):
        """Create/get a VMInterface DiffSync model and attach it to the VM.

        Args:
            name (str): The interface name.
            mac (Optional[str]): The interface's MAC address, if known.
            diffsync_vm (VirtualMachineModel): The VM DiffSync model to attach the interface to.

        Returns:
            VMInterfaceModel: The created/existing VMInterface DiffSync model.
        """
        diffsync_interface, _ = self.get_or_instantiate(
            self.interface,
            {"name": name, "virtual_machine__name": diffsync_vm.name},
            {
                "enabled": True,
                "status__name": ACTIVE_STATUS_NAME,
                "mac_address": mac.upper() if mac else None,
            },
        )
        diffsync_vm.add_child(diffsync_interface)
        return diffsync_interface

    def _load_vm_interfaces_from_config(
        self,
        vm_config: dict,
        diffsync_vm: VirtualMachineModel,
        get_name: Callable[[str, dict], str],
        get_ip_pairs: Callable[[str, dict, Optional[str]], Iterable[tuple]],
    ) -> None:
        """Shared skeleton: iterate a VM's ``netN`` config entries, create interfaces, record IPs.

        Args:
            vm_config (dict): The VM's Proxmox config (QEMU or LXC), as returned by the client.
            diffsync_vm (VirtualMachineModel): The VM DiffSync model to attach interfaces to.
            get_name (Callable[[str, dict], str]): Given the ``netN`` key and its parsed parts,
                returns the interface name to use.
            get_ip_pairs (Callable[[str, dict, Optional[str]], Iterable[tuple]]): Given the ``netN``
                key, its parsed parts, and the resolved MAC address, yields ``(host, prefix_length)``
                tuples to record against the interface.

        Returns:
            None
        """
        addrs4, addrs6 = [], []
        for key, value in vm_config.items():
            if not re.match(r"^net\d+$", key) or not isinstance(value, str):
                continue
            parts = parse_net_config(value)
            mac = mac_from_net_parts(parts)
            diffsync_interface = self._instantiate_interface(get_name(key, parts), mac, diffsync_vm)
            assignment = {"name": diffsync_interface.name, "virtual_machine__name": diffsync_vm.name}

            for host, prefix_length in get_ip_pairs(key, parts, mac):
                ipv4, ipv6 = self._record_ip(host, prefix_length, "vm_interfaces", assignment)
                addrs4 += ipv4
                addrs6 += ipv6

        self.load_primary_ip(addrs4, addrs6, diffsync_vm)

    def _load_qemu_interfaces(
        self, vm_config: dict, agent_interfaces: List[dict], diffsync_vm: VirtualMachineModel
    ) -> None:
        """QEMU path: NICs come from config; IPs come from the guest agent matched by MAC.

        Args:
            vm_config (dict): The VM's Proxmox QEMU config, as returned by the client.
            agent_interfaces (List[dict]): Interfaces reported by the QEMU guest agent.
            diffsync_vm (VirtualMachineModel): The VM DiffSync model to attach interfaces to.

        Returns:
            None
        """
        # Build a MAC -> agent interface lookup.
        agent_by_mac = {}
        for iface in agent_interfaces:
            hw = iface.get("hardware-address")
            if hw:
                agent_by_mac[hw.lower()] = iface

        def qemu_ip_pairs(key, parts, mac):  # pylint: disable=unused-argument
            agent_iface = agent_by_mac.get(mac.lower()) if mac else None
            if not agent_iface:
                return
            for ip_entry in agent_iface.get("ip-addresses", []) or []:
                yield ip_entry.get("ip-address"), ip_entry.get("prefix")

        self._load_vm_interfaces_from_config(
            vm_config, diffsync_vm, get_name=lambda key, parts: key, get_ip_pairs=qemu_ip_pairs
        )

    def _load_lxc_interfaces(self, vm_config: dict, diffsync_vm: VirtualMachineModel) -> None:
        """LXC path: NICs and IPs both come from the container config (no agent).

        Args:
            vm_config (dict): The VM's Proxmox LXC config, as returned by the client.
            diffsync_vm (VirtualMachineModel): The VM DiffSync model to attach interfaces to.

        Returns:
            None
        """

        def lxc_ip_pairs(key, parts, mac):  # pylint: disable=unused-argument
            for ip_key in ("ip", "ip6"):
                cidr = parts.get(ip_key)
                if not cidr or cidr in ("dhcp", "manual", "auto") or "/" not in cidr:
                    continue
                host, _, prefix_length = cidr.partition("/")
                yield host, int(prefix_length)

        self._load_vm_interfaces_from_config(
            vm_config,
            diffsync_vm,
            get_name=lambda key, parts: parts.get("name") or key,
            get_ip_pairs=lxc_ip_pairs,
        )

    def _record_ip(
        self, host: Optional[str], prefix_length: Optional[int], assignment_key: str, assignment_value: dict
    ) -> Tuple[list, list]:
        """Record an IP + its Prefix and its interface assignment.

        Args:
            host (Optional[str]): The IP address string.
            prefix_length (Optional[int]): The mask length.
            assignment_key (str): Either ``"vm_interfaces"`` (VMInterface) or ``"interfaces"`` (DCIM Interface).
            assignment_value (dict): The interface dict to assign the IP to.

        Returns:
            Tuple[list, list]: ``([ipv4], [ipv6])`` lists for primary-IP selection.
        """
        if not host or prefix_length is None:
            return [], []
        addr = create_ipaddr(host)
        if self.config.default_ignore_link_local and addr.is_link_local:
            self.job.log_debug(message=f"Skipping link-local/APIPA address: {host}")
            return [], []

        prefix_network = str(ipaddress.ip_network(f"{addr}/{prefix_length}", strict=False)).split("/")[0]
        self.get_or_instantiate(
            self.prefix,
            {
                "network": prefix_network,
                "prefix_length": int(prefix_length),
                "namespace__name": GLOBAL_NAMESPACE_NAME,
                "status__name": ACTIVE_STATUS_NAME,
            },
            {"type": NETWORK_PREFIX_TYPE},
        )

        ip_info = self.ip_address_map.setdefault(
            host,
            {
                "mask_length": int(prefix_length),
                "status__name": self.config.default_ip_status_map["PREFERRED"],
                "vm_interfaces": [],
                "interfaces": [],
            },
        )
        if assignment_value not in ip_info[assignment_key]:
            ip_info[assignment_key].append(assignment_value)

        if addr.version == 4:
            return [addr], []
        return [], [addr]

    def load_primary_ip(self, ipv4_addresses: list, ipv6_addresses: list, diffsync_vm: VirtualMachineModel) -> None:
        """Determine the primary IP(s) of a Virtual Machine per the configured sort logic.

        Args:
            ipv4_addresses (list): The VM's candidate IPv4 addresses.
            ipv6_addresses (list): The VM's candidate IPv6 addresses.
            diffsync_vm (VirtualMachineModel): The VM DiffSync model to set primary IPs on.

        Returns:
            None
        """
        ipv4_addresses.sort()
        ipv6_addresses.sort()
        index = 0 if self.config.primary_ip_sort_by == "Lowest" else -1
        if ipv4_addresses:
            diffsync_vm.primary_ip4__host = str(ipv4_addresses[index])
        if ipv6_addresses:
            diffsync_vm.primary_ip6__host = str(ipv6_addresses[index])

    def load_ip_map(self) -> None:
        """Load all IP Addresses accumulated in the IP map into DiffSync.

        Returns:
            None
        """
        for ip, info in self.ip_address_map.items():
            self.get_or_instantiate(
                self.ip_address,
                {
                    "host": ip,
                    "mask_length": info["mask_length"],
                    "status__name": info["status__name"],
                },
                {
                    "vm_interfaces": sorted(
                        info["vm_interfaces"], key=lambda item: item["virtual_machine__name"].lower()
                    ),
                    "interfaces": sorted(
                        info["interfaces"], key=lambda item: (item["device__name"].lower(), item["name"].lower())
                    ),
                },
            )

    def load(self) -> None:
        """Load data from Proxmox VE.

        Returns:
            None
        """
        # Regardless of settings, we must include the SSoT tag.
        self.get_or_instantiate(self.tag, {"name": get_ssot_tag_name(self.config)})

        self.load_clusters()
        if self.config.sync_nodes_as_devices:
            self.load_nodes()
        self.load_virtual_machines()
        self.load_ip_map()
        self.job.logger.info("Finished loading data from Proxmox VE.")
