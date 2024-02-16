"""Adapter for VM Ware vSphere objects."""

#  pylint: disable=too-many-arguments
# Load method is packed with conditionals  #  pylint: disable=too-many-branches
import ipaddress
from typing import List

from diffsync import Adapter
from netutils.ip import cidr_to_netmask

from nautobot_ssot.integrations.vsphere import defaults
from nautobot_ssot.integrations.vsphere.diffsync.models.vsphere import (
    ClusterGroupModel,
    ClusterModel,
    IPAddressModel,
    PrefixModel,
    VirtualMachineModel,
    VMInterfaceModel,
)


def deduce_network_from_ip(ip: ipaddress.IPv4Address, subnet_mask: str):
    """Figure out the network of a given IP and its subnet mask."""
    ip_int = int(ip)
    subnet_int = int(ipaddress.IPv4Address(subnet_mask))

    # Perform a bitwise AND operation between the IP address and the subnet mask
    network_int = ip_int & subnet_int

    # Convert the result back to an IPv4 address
    network_address = str(ipaddress.IPv4Address(network_int))

    return network_address


def create_ipaddr(address: str):
    """Create an IPV4 or IPV4 object."""
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
    # ip_address_to_interface = IPAddressToInterfaceModel
    prefix = PrefixModel

    top_level = ["prefix", "clustergroup"]

    def __init__(self, *args, job=None, sync=None, client, config, cluster_filter, **kwargs):
        """Initialize the vSphereDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        self.config = config
        self.cluster_filter = cluster_filter if cluster_filter else None

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
            diffsync_virtualmachine, _ = self.get_or_instantiate(
                self.virtual_machine,
                {"name": virtual_machine["name"]},
                {
                    "vcpus": virtual_machine["cpu_count"],
                    "memory": virtual_machine["memory_size_MiB"],
                    "disk": (
                        get_disk_total(virtual_machine_details["disks"])
                        if virtual_machine_details.get("disks")
                        else None
                    ),
                    "status__name": defaults.DEFAULT_VM_STATUS_MAP[virtual_machine_details["power_state"]],
                    "cluster__name": cluster["name"],
                },
            )
            diffsync_cluster.add_child(diffsync_virtualmachine)
            self.load_vm_interfaces(
                vsphere_virtual_machine=virtual_machine_details,
                vm_id=virtual_machine["vm"],
                diffsync_virtualmachine=diffsync_virtualmachine,
            )

    def load_ip_addresses(self, vsphere_vm_interfaces, mac_address, diffsync_vminterface):
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

                if defaults.DEFAULT_IGNORE_LINK_LOCAL:
                    if addr.version == 6 and addr.is_link_local:
                        self.job.log_debug(message=f"Skipping Link Local Address: {ip_address}")
                        continue
                if defaults.DEFAULT_IGNORE_APIPA:
                    if addr.version == 4 and addr.is_link_local:
                        self.job.log_debug(message=f"Skipping Link Local Address: {ip_address}")
                _ = ipv4_addresses.append(addr) if addr.version == 4 else ipv6_addresses.append(addr)
                netmask = cidr_to_netmask(ip_address["prefix_length"])
                prefix = deduce_network_from_ip(addr, netmask)

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

                diffsync_ipaddress, created = self.get_or_instantiate(
                    self.ip_address,
                    {
                        "host": ip_address["ip_address"],
                        "mask_length": ip_address["prefix_length"],
                        "status__name": defaults.DEFAULT_IP_STATUS_MAP[ip_address["state"]],
                    },
                    {
                        "vm_interfaces": [{"name": diffsync_vminterface.name}],
                    },
                )
                diffsync_vminterface.add_child(diffsync_ipaddress)
                # diffsync_assignment, _ = self.get_or_instantiate(
                #     self.ip_address_to_interface,
                #     {"ip_address__host": ip_address["ip_address"], "vm_interface__name": diffsync_vminterface.name},
                # )

        return ipv4_addresses, ipv6_addresses

    def load_primary_ip(self, ipv4_addresses, ipv6_addresses, diffsync_virtualmachine):
        """Determine Primary IP of Virtual Machine."""
        # Sort and choose a primary_ip by default config setting
        ipv4_addresses.sort()
        ipv6_addresses.sort()

        # Sort and choose either Lowest or Last item in the list
        if defaults.PRIMARY_IP_SORT_BY == "Lowest":
            if ipv4_addresses:
                diffsync_virtualmachine.primary_ip4__host = str(ipv4_addresses[0])
            if ipv6_addresses:
                diffsync_virtualmachine.primary_ip6__host = str(ipv6_addresses[0])
        else:
            if ipv4_addresses:
                diffsync_virtualmachine.primary_ip4__host = str(ipv4_addresses[-1])
            if ipv6_addresses:
                diffsync_virtualmachine.primary_ip6__host = str(ipv6_addresses[-1])

    def load_vm_interfaces(self, vsphere_virtual_machine, vm_id, diffsync_virtualmachine):
        """Load VM Interfaces."""
        nics = vsphere_virtual_machine["nics"]
        self.job.log_debug(message=f"Loading NICs for VM-ID {vm_id}: {nics}")
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
                    "enabled": defaults.VSPHERE_VM_INTERFACE_MAP[nic["value"]["state"]],
                    "status__name": "Active",
                    "mac_address": nic_mac,
                },
            )
            diffsync_virtualmachine.add_child(diffsync_vminterface)
            # Get detail interfaces w/ ip's from VM - Only if VM is Enabled
            if vsphere_virtual_machine["power_state"] == "POWERED_ON":
                vm_interfaces = self.client.get_vm_interfaces(vm_id=vm_id).json()["value"]

                # Load any IP addresses associated to this NIC/MAC
                ipv4_addresses, ipv6_addresses = self.load_ip_addresses(
                    vm_interfaces,
                    nic_mac,
                    diffsync_vminterface,
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
                        "cluster_type__name": defaults.DEFAULT_VSPHERE_TYPE,
                        "cluster_group__name": clustergroup["name"],
                    },
                )
                cluster_group_parent = self.get(self.clustergroup, clustergroup["name"])
                if self.cluster_filter and cluster["name"] == self.cluster_filter.name:
                    self.job.log_debug(message=f"Found Cluster from filter {cluster}")
                    self.add(diffsync_cluster)
                    if defaults.ENFORCE_CLUSTER_GROUP_TOP_LEVEL:
                        cluster_group_parent.add_child(diffsync_cluster)
                    # Load virtual machines that belong to a cluster
                    self.load_virtualmachines(cluster, diffsync_cluster)
                    break
                if defaults.ENFORCE_CLUSTER_GROUP_TOP_LEVEL:
                    cluster_group_parent.add_child(diffsync_cluster)
                # Load virtual machines that belong to a cluster
                self.load_virtualmachines(cluster, diffsync_cluster)

    def load_standalone_vms(self):
        """Load all VM's from vSphere."""
        virtual_machines = self.client.get_vms().json()["value"]
        for virtual_machine in virtual_machines:
            virtual_machine_details = self.client.get_vm_details(virtual_machine["vm"]).json()["value"]
            self.job.log_debug(message=f"Virtual Machine Details: {virtual_machine_details}")
            diffsync_virtualmachine, _ = self.get_or_instantiate(
                self.virtual_machine,
                {"name": virtual_machine["name"]},
                {
                    "vcpus": virtual_machine["cpu_count"],
                    "memory": virtual_machine["memory_size_MiB"],
                    "disk": (
                        get_disk_total(virtual_machine_details["disks"])
                        if virtual_machine_details.get("disks")
                        else None
                    ),
                    "status": defaults.DEFAULT_VM_STATUS_MAP[virtual_machine_details["power_state"]],
                    "cluster": defaults.DEFAULT_CLUSTER_NAME,
                },
            )
            self.load_vm_interfaces(
                vsphere_virtual_machine=virtual_machine_details,
                vm_id=virtual_machine["vm"],
                diffsync_virtualmachine=diffsync_virtualmachine,
            )

    def load(self):
        """Load data from vSphere."""
        if defaults.DEFAULT_USE_CLUSTERS:
            self.load_data()
        else:
            self.job.log_warning(message="Not syncing Clusters or Cluster Groups per user settings")
            self.job.log_warning(message="`DEFAULT_USE_CLUSTERS` set to `False`")
            self.load_standalone_vms()
