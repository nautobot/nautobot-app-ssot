"""Adapter for VM Ware vSphere objects."""

#  pylint: disable=too-many-arguments
# Load method is packed with conditionals  #  pylint: disable=too-many-branches
import ipaddress
from typing import List

from diffsync import Adapter

from nautobot_ssot.integrations.vsphere.diffsync.models.vsphere import (
    ClusterGroupModel,
    ClusterModel,
    IPAddressModel,
    PrefixModel,
    VirtualMachineModel,
    VMInterfaceModel,
)


def deduce_network_from_ip(ip: str, subnet_mask: str) -> str:
    """Deduce the network address from an IP and subnet mask. Supports both IPv4 and IPv6.

    Args:
        ip (str): IP address (e.g., "192.168.2.88" or "2001:db8::1234")
        subnet_mask (str): Subnet mask (e.g., "255.255.254.0" or "ffff:ffff:ffff:ffff::")

    Returns:
        str: Network address in CIDR notation (e.g., "192.168.2.0/23" or "2001:db8::/64")
    """
    mask_obj = ipaddress.ip_address(subnet_mask)

    # Convert subnet mask to prefix length
    prefix_len = bin(int(mask_obj)).count("1")

    # Create full CIDR string
    network = ipaddress.ip_network(f"{ip}/{prefix_len}", strict=False)
    return str(network.network_address)


def create_ipaddr(address: str):
    """Create an IPV4 or IPV6 object."""
    try:
        ip_address = ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError:
        ip_address = ipaddress.IPv6Address(address)
    return ip_address


def get_disk_total(disks: List):
    """Calculcate total disk capacity."""
    total = 0
    for disk in disks:
        total += disk["value"]["capacity"]
    return int(total / 1024.0**3)


class VsphereDiffSync(Adapter):
    """vSphere adapter for DiffSync."""

    clustergroup = ClusterGroupModel
    cluster = ClusterModel
    virtual_machine = VirtualMachineModel
    interface = VMInterfaceModel
    ip_address = IPAddressModel
    prefix = PrefixModel

    top_level = ["prefix", "clustergroup", "virtual_machine", "ip_address"]

    def __init__(self, *args, job=None, sync=None, client, config, cluster_filters, **kwargs):
        """Initialize the vSphereDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        self.config = config
        self.cluster_filters = cluster_filters
        self.ip_address_map = {}

    def _add_diffsync_virtualmachine(self, virtual_machine, virtual_machine_details, cluster_name):
        """Add virtualmachine to DiffSync and call load_vm_interfaces().

        Args:
            virtual_machine (dict): Virtual Machine information from vSphere.
            virtual_machine_details (dict): Virtual Machine detail information from vSphere.
            diffsync_cluster (ClusterModel): Current DiffSync Cluster object.
            cluster_name (str): Name of the cluster to which the VM belongs.
        """
        diffsync_virtualmachine, _ = self.get_or_instantiate(
            self.virtual_machine,
            {"name": virtual_machine.get("name"), "cluster__name": cluster_name},
            {
                "vcpus": virtual_machine.get("cpu_count", 0),
                "memory": virtual_machine.get("memory_size_MiB", 0),
                "disk": (
                    get_disk_total(virtual_machine_details["disks"]) if virtual_machine_details.get("disks") else None
                ),
                "status__name": self.config.default_vm_status_map[virtual_machine["power_state"]],
            },
        )
        self.load_vm_interfaces(
            vsphere_virtual_machine_details=virtual_machine_details,
            vm_id=virtual_machine["vm"],
            diffsync_virtualmachine=diffsync_virtualmachine,
        )

    def load_cluster_groups(self):
        """Load Cluster Groups (DataCenters)."""
        clustergroups = self.client.get_datacenters().json()["value"]
        self.job.log_debug(message=f"Loading ClusterGroups {clustergroups}")
        for clustergroup in clustergroups:
            self.get_or_instantiate(self.clustergroup, {"name": clustergroup["name"]})
        return clustergroups

    def load_virtualmachines(self, cluster, diffsync_cluster):
        """Load Virtual Machines."""
        virtual_machines = self.client.get_vms_from_cluster(cluster["cluster"]).json()["value"]
        self.job.log_debug(message=f"Loading VirtualMachines from Cluster {cluster}: {virtual_machines}")

        for virtual_machine in virtual_machines:
            virtual_machine_details = self.client.get_vm_details(virtual_machine["vm"]).json()["value"]
            self.job.log_debug(message=f"Virtual Machine Details: {virtual_machine_details}")
            if virtual_machine.get("cpu_count") is None or virtual_machine.get("memory_size_MiB") is None:
                self.job.logger.info(
                    f"Skipping Virtual Machine {virtual_machine['name']} due to missing CPU or Memory details."
                )
                continue
            self._add_diffsync_virtualmachine(virtual_machine, virtual_machine_details, cluster["name"])

    def load_ip_addresses(
        self,
        vsphere_vm_interfaces,
        mac_address,
        diffsync_vminterface,
        diffsync_virtualmachine,
    ):
        """Load VM IP Addresses into Interfaces.

        Compare the current NIC MAC to grab any IP's associated.
        """
        ipv4_addresses = []
        ipv6_addresses = []
        for interface in vsphere_vm_interfaces:
            if not isinstance(interface, dict):
                continue
            current_mac = interface["mac_address"].lower() if interface.get("mac_address") else None
            if not current_mac == mac_address or not interface.get("ip"):
                continue
            # Capture all IP Addresses
            for ip_address in interface["ip"]["ip_addresses"]:
                self.job.log_debug(message=f"Loading IP Addresses {interface}")
                # Convert to IP Object if IPV4 or IPV6 and add to list by version
                addr = create_ipaddr(ip_address["ip_address"])

                if self.config.default_ignore_link_local and addr.is_link_local:
                    if addr.version == 6:
                        self.job.log_debug(message=f"Skipping Link Local Address: {ip_address}")
                        continue
                    if addr.version == 4:
                        self.job.log_debug(message=f"Skipping APIPA Address: {ip_address}")
                    continue

                _ = ipv4_addresses.append(addr) if addr.version == 4 else ipv6_addresses.append(addr)
                prefix = str(ipaddress.ip_network(f"{addr}/{ip_address['prefix_length']}", strict=False)).split("/")[0]

                diffsync_prefix, _ = self.get_or_instantiate(
                    self.prefix,
                    {
                        "network": prefix,
                        "prefix_length": int(ip_address["prefix_length"]),
                        "namespace__name": "Global",
                        "status__name": "Active",
                    },
                    {"type": "network"},
                )

                # Add info to IP Mapper to load later.
                default = {
                    "mask_length": ip_address["prefix_length"],
                    "status__name": self.config.default_ip_status_map[ip_address["state"]],
                    "vm_interfaces": [
                        {
                            "name": diffsync_vminterface.name,
                            "virtual_machine__name": diffsync_virtualmachine.name,
                        }
                    ],
                }

                ip_info = self.ip_address_map.setdefault(ip_address["ip_address"], default)
                if ip_info != default:
                    # If the IP already exists in the map, ensure the vm_interface is included
                    if {
                        "name": diffsync_vminterface.name,
                        "virtual_machine__name": diffsync_virtualmachine.name,
                    } not in ip_info["vm_interfaces"]:
                        ip_info["vm_interfaces"].append(
                            {
                                "name": diffsync_vminterface.name,
                                "virtual_machine__name": diffsync_virtualmachine.name,
                            }
                        )

        return ipv4_addresses, ipv6_addresses

    def load_primary_ip(self, ipv4_addresses, ipv6_addresses, diffsync_virtualmachine):
        """Determine Primary IP of Virtual Machine."""
        # Sort and choose a primary_ip by default config setting
        ipv4_addresses.sort()
        ipv6_addresses.sort()

        # Sort and choose either Lowest or Last item in the list
        if self.config.primary_ip_sort_by == "Lowest":
            if ipv4_addresses:
                diffsync_virtualmachine.primary_ip4__host = str(ipv4_addresses[0])
            if ipv6_addresses:
                diffsync_virtualmachine.primary_ip6__host = str(ipv6_addresses[0])
        else:
            if ipv4_addresses:
                diffsync_virtualmachine.primary_ip4__host = str(ipv4_addresses[-1])
            if ipv6_addresses:
                diffsync_virtualmachine.primary_ip6__host = str(ipv6_addresses[-1])

    def load_vm_interfaces(self, vsphere_virtual_machine_details, vm_id, diffsync_virtualmachine):
        """Load VM Interfaces."""
        nics = vsphere_virtual_machine_details["nics"]
        self.job.log_debug(message=f"Loading NICs for {vm_id}: {nics}")
        # Get all IP Addresses from ALL NICs on Virtual Machine
        addrs4 = []
        addrs6 = []

        for nic in nics:
            nic_mac = nic["value"]["mac_address"].lower()
            diffsync_vminterface, _ = self.get_or_instantiate(
                self.interface,
                {
                    "name": nic["value"]["label"],
                    "virtual_machine__name": diffsync_virtualmachine.name,
                },
                {
                    "enabled": self.config.default_vm_interface_map[nic["value"]["state"]],
                    "status__name": "Active",
                    "mac_address": nic_mac.upper(),
                },
            )
            diffsync_virtualmachine.add_child(diffsync_vminterface)
            # Get detail interfaces w/ ip's from VM - Only if VM is Enabled
            if vsphere_virtual_machine_details["power_state"] == "POWERED_ON":
                vm_interfaces = self.client.get_vm_interfaces(vm_id=vm_id).json()["value"]

                # Load any IP addresses associated to this NIC/MAC
                ipv4_addresses, ipv6_addresses = self.load_ip_addresses(
                    vm_interfaces,
                    nic_mac,
                    diffsync_vminterface,
                    diffsync_virtualmachine,
                )

                _ = [addrs4.append(str(addr)) for addr in ipv4_addresses]
                _ = [addrs6.append(str(addr)) for addr in ipv6_addresses]

        # Sort through all IP's on
        self.load_primary_ip(addrs4, addrs6, diffsync_virtualmachine)

    def load_data(self):
        """Load all clusters from vSphere."""
        # load all cluster groups (datacenters)
        clustergroups = self.load_cluster_groups()
        for clustergroup in clustergroups:
            clusters = self.client.get_clusters_from_dc(clustergroup["datacenter"]).json()["value"]
            self.job.log_debug(message=f"Found vSphere Clusters {clusters}")
            for cluster in clusters:
                diffsync_cluster, _ = self.get_or_instantiate(
                    self.cluster,
                    {"name": cluster["name"]},
                    {
                        "cluster_type__name": self.config.default_cluster_type,
                        "cluster_group__name": clustergroup["name"],
                    },
                )
                cluster_group_parent = self.get(self.clustergroup, clustergroup["name"])
                if self.cluster_filters:
                    if cluster["name"] in [cluster.name for cluster in self.cluster_filters]:
                        self.job.log_debug(message=f"Found Cluster from filter {cluster}")
                        self.add(diffsync_cluster)
                        cluster_group_parent.add_child(diffsync_cluster)
                        self.load_virtualmachines(cluster, diffsync_cluster)
                else:
                    self.job.log_debug(f"Adding cluster {cluster}")
                    cluster_group_parent.add_child(diffsync_cluster)
                    self.load_virtualmachines(cluster, diffsync_cluster)

    def load_standalone_vms(self):
        """Load all VM's from vSphere."""
        default_diffsync_clustergroup, _ = self.get_or_instantiate(
            self.clustergroup, {"name": self.config.default_clustergroup_name}
        )
        default_diffsync_cluster, _ = self.get_or_instantiate(
            self.cluster,
            {"name": self.config.default_cluster_name},
            {
                "cluster_type__name": self.config.default_cluster_type,
                "cluster_group__name": self.config.default_clustergroup_name,
            },
        )
        default_diffsync_clustergroup.add_child(default_diffsync_cluster)
        virtual_machines = self.client.get_vms().json()["value"]
        for virtual_machine in virtual_machines:
            virtual_machine_details = self.client.get_vm_details(virtual_machine["vm"]).json()["value"]
            self.job.log_debug(message=f"Virtual Machine Details: {virtual_machine_details}")
            if virtual_machine.get("cpu_count") is None or virtual_machine.get("memory_size_MiB") is None:
                self.job.logger.info(
                    f"Skipping Virtual Machine {virtual_machine['name']} due to missing CPU or Memory details."
                )
                continue
            self._add_diffsync_virtualmachine(
                virtual_machine, virtual_machine_details, self.config.default_cluster_name
            )

    def load_ip_map(self):
        """Load all IP Addresses from the IP Map into DiffSync."""
        for ip, info in self.ip_address_map.items():
            diffsync_ipaddress, _ = self.get_or_instantiate(
                self.ip_address,
                {
                    "host": ip,
                    "mask_length": info["mask_length"],
                    "status__name": info["status__name"],
                },
                {"vm_interfaces": info["vm_interfaces"]},
            )

    def load(self):
        """Load data from vSphere."""
        if self.config.use_clusters:
            self.load_data()
        else:
            self.job.logger.info("Not syncing Clusters or Cluster Groups per user settings. Using default Cluster.")
            self.load_standalone_vms()
        self.load_ip_map()
        self.job.logger.info("Finished loading data from vSphere.")
