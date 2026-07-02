"""Adapter for Proxmox VE objects."""

#  pylint: disable=too-many-arguments
#  pylint: disable=too-many-branches
#  pylint: disable=too-many-locals
import ipaddress
import re

from diffsync import Adapter
from nautobot.dcim.choices import InterfaceTypeChoices

from nautobot_ssot.integrations.proxmox.constants import NODE_INTERFACE_TYPE_MAP, SSOT_TAG_NAME
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


def create_ipaddr(address: str):
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


def parse_net_config(net_string: str) -> dict:
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


def mac_from_net_parts(parts: dict):
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


def bytes_to_mb(value):
    """Convert a byte count to whole MB (Nautobot VirtualMachine.memory is in MB).

    Args:
        value (Optional[int]): The byte count to convert.

    Returns:
        Optional[int]: The value in whole MB, or ``None`` if ``value`` is falsy.
    """
    return int(value / 1024**2) if value else None


def bytes_to_gb(value):
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

    @property
    def _ssot_tag_name(self):
        """Configured SSoT sync tag name, falling back to the built-in default."""
        return getattr(getattr(self.config, "default_ssot_tag", None), "name", None) or SSOT_TAG_NAME

    def load_clusters(self):
        """Load the Cluster Group and Cluster from Proxmox VE cluster status."""
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

    def load_nodes(self):
        """Load Proxmox VE nodes as Nautobot Devices."""
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
                    "status__name": "Active",
                    "clusters": [{"name": self.cluster_name}],
                    "pve_version": node_status.get("pveversion"),
                    "cpu_count": (node_status.get("cpuinfo") or {}).get("cpus"),
                    "memory_gb": bytes_to_gb(memory_total),
                },
            )
            self.node_device_map[node_name] = node_name
            self.load_node_interfaces(node_name, diffsync_device)

    def load_node_interfaces(self, node_name, diffsync_device):
        """Load a node's network interfaces (with topology + IPs) as DCIM Interfaces on its Device."""
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
                    "status__name": "Active",
                    "mtu": int(mtu) if mtu else None,
                    "bridge__name": member_bridge.get(iface_name),
                    "lag__name": member_lag.get(iface_name),
                    "parent_interface__name": member_parent.get(iface_name),
                },
            )
            diffsync_device.add_child(diffsync_interface)
            node_ipv4 += self._load_node_interface_ips(entry, iface_name, node_name)

        self._set_node_primary_ip(node_name, diffsync_device, node_ipv4)

    def _load_node_interface_ips(self, entry, iface_name, node_name):
        """Record IPs configured on a node interface; return the IPv4 addresses found."""
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

    def _set_node_primary_ip(self, node_name, diffsync_device, node_ipv4):
        """Set the node Device's primary IPv4, preferring the cluster management IP."""
        mgmt_ip = self.node_mgmt_ip.get(node_name)
        if mgmt_ip and any(str(addr) == mgmt_ip for addr in node_ipv4):
            diffsync_device.primary_ip4__host = mgmt_ip
        elif node_ipv4:
            node_ipv4.sort()
            diffsync_device.primary_ip4__host = str(node_ipv4[0])

    def _vm_tag_list(self, resource):
        """Build the tag list for a VM, always including the SSoT tag."""
        tags = [{"name": self._ssot_tag_name}]
        if self.config.sync_proxmox_tags and resource.get("tags"):
            for raw_tag in re.split(r"[;,]", resource["tags"]):
                raw_tag = raw_tag.strip()
                if raw_tag:
                    self.get_or_instantiate(self.tag, {"name": raw_tag}, {"description": ""})
                    tags.append({"name": raw_tag})
        return sorted(tags, key=lambda item: item["name"].lower())

    def load_virtual_machines(self):
        """Load QEMU VMs (and LXC containers if enabled) from /cluster/resources."""
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

    def load_vm_interfaces(self, resource, diffsync_vm):
        """Load interfaces and IPs for a VM using the QEMU or LXC code path."""
        node = resource.get("node")
        vmid = resource.get("vmid")
        resource_type = resource.get("type")

        if resource_type == "qemu":
            config = self.client.get_qemu_config(node, vmid)
            agent_interfaces = []
            if resource.get("status") == "running":
                agent_interfaces = self.client.get_qemu_agent_interfaces(node, vmid)
            self._load_qemu_interfaces(config, agent_interfaces, diffsync_vm)
        else:
            config = self.client.get_lxc_config(node, vmid)
            self._load_lxc_interfaces(config, diffsync_vm)

    def _instantiate_interface(self, name, mac, diffsync_vm):
        """Create/get a VMInterface DiffSync model and attach it to the VM."""
        diffsync_interface, _ = self.get_or_instantiate(
            self.interface,
            {"name": name, "virtual_machine__name": diffsync_vm.name},
            {
                "enabled": True,
                "status__name": "Active",
                "mac_address": mac.upper() if mac else None,
            },
        )
        diffsync_vm.add_child(diffsync_interface)
        return diffsync_interface

    def _load_qemu_interfaces(self, config, agent_interfaces, diffsync_vm):
        """QEMU path: NICs come from config; IPs come from the guest agent matched by MAC."""
        addrs4, addrs6 = [], []
        # Build a MAC -> agent interface lookup.
        agent_by_mac = {}
        for iface in agent_interfaces:
            hw = iface.get("hardware-address")
            if hw:
                agent_by_mac[hw.lower()] = iface

        for key, value in config.items():
            if not re.match(r"^net\d+$", key) or not isinstance(value, str):
                continue
            parts = parse_net_config(value)
            mac = mac_from_net_parts(parts)
            diffsync_interface = self._instantiate_interface(key, mac, diffsync_vm)

            agent_iface = agent_by_mac.get(mac.lower()) if mac else None
            if not agent_iface:
                continue
            assignment = {"name": diffsync_interface.name, "virtual_machine__name": diffsync_vm.name}
            for ip_entry in agent_iface.get("ip-addresses", []) or []:
                ipv4, ipv6 = self._record_ip(
                    ip_entry.get("ip-address"),
                    ip_entry.get("prefix"),
                    "vm_interfaces",
                    assignment,
                )
                addrs4 += ipv4
                addrs6 += ipv6

        self.load_primary_ip(addrs4, addrs6, diffsync_vm)

    def _load_lxc_interfaces(self, config, diffsync_vm):
        """LXC path: NICs and IPs both come from the container config (no agent)."""
        addrs4, addrs6 = [], []
        for key, value in config.items():
            if not re.match(r"^net\d+$", key) or not isinstance(value, str):
                continue
            parts = parse_net_config(value)
            mac = mac_from_net_parts(parts)
            iface_name = parts.get("name") or key
            diffsync_interface = self._instantiate_interface(iface_name, mac, diffsync_vm)
            assignment = {"name": diffsync_interface.name, "virtual_machine__name": diffsync_vm.name}

            for ip_key in ("ip", "ip6"):
                cidr = parts.get(ip_key)
                if not cidr or cidr in ("dhcp", "manual", "auto"):
                    continue
                if "/" not in cidr:
                    continue
                host, _, prefix_length = cidr.partition("/")
                ipv4, ipv6 = self._record_ip(host, int(prefix_length), "vm_interfaces", assignment)
                addrs4 += ipv4
                addrs6 += ipv6

        self.load_primary_ip(addrs4, addrs6, diffsync_vm)

    def _record_ip(self, host, prefix_length, assignment_key, assignment_value):
        """Record an IP + its Prefix and its interface assignment.

        Args:
            host: The IP address string.
            prefix_length: The mask length.
            assignment_key: Either ``"vm_interfaces"`` (VMInterface) or ``"interfaces"`` (DCIM Interface).
            assignment_value: The interface dict to assign the IP to.

        Returns:
            ([ipv4], [ipv6]) lists for primary-IP selection.
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
                "namespace__name": "Global",
                "status__name": "Active",
            },
            {"type": "network"},
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

    def load_primary_ip(self, ipv4_addresses, ipv6_addresses, diffsync_vm):
        """Determine the primary IP(s) of a Virtual Machine per the configured sort logic."""
        ipv4_addresses.sort()
        ipv6_addresses.sort()
        if self.config.primary_ip_sort_by == "Lowest":
            if ipv4_addresses:
                diffsync_vm.primary_ip4__host = str(ipv4_addresses[0])
            if ipv6_addresses:
                diffsync_vm.primary_ip6__host = str(ipv6_addresses[0])
        else:
            if ipv4_addresses:
                diffsync_vm.primary_ip4__host = str(ipv4_addresses[-1])
            if ipv6_addresses:
                diffsync_vm.primary_ip6__host = str(ipv6_addresses[-1])

    def load_ip_map(self):
        """Load all IP Addresses accumulated in the IP map into DiffSync."""
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

    def load(self):
        """Load data from Proxmox VE."""
        # Regardless of settings, we must include the SSoT tag.
        self.get_or_instantiate(self.tag, {"name": self._ssot_tag_name})

        self.load_clusters()
        if self.config.sync_nodes_as_devices:
            self.load_nodes()
        self.load_virtual_machines()
        self.load_ip_map()
        self.job.logger.info("Finished loading data from Proxmox VE.")
