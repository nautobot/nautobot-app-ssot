# pylint: disable=duplicate-code
"""DiffSync adapter class for Ip Fabric."""

import ipaddress
import logging
from collections import defaultdict

from diffsync import ObjectAlreadyExists
from diffsync.exceptions import ObjectNotFound
from nautobot.dcim.constants import NONCONNECTABLE_IFACE_TYPES
from nautobot.dcim.models import Device
from nautobot.ipam.models import VLAN
from netutils.interface import canonical_interface_name
from netutils.ip import cidr_to_netmask
from netutils.mac import mac_to_format

from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_CABLE_STATUS,
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_STATUS,
    DEFAULT_INTERFACE_MAC,
    DEFAULT_INTERFACE_MTU,
    IP_FABRIC_USE_CANONICAL_INTERFACE_NAME,
    PSEUDO_MANAGEMENT_INTERFACE_NAME,
    SYNC_IPF_DEV_TYPE_TO_ROLE,
)
from nautobot_ssot.integrations.ipfabric.diffsync import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.utilities import utils as ipfabric_utils
from nautobot_ssot.integrations.ipfabric.utilities.cables import canonical_endpoints

try:
    from ipfabric import IPFClient
except ImportError:
    IPFClient = None


logger = logging.getLogger("nautobot.jobs")

device_serial_max_length = Device._meta.get_field("serial").max_length
name_max_length = VLAN._meta.get_field("name").max_length


# pylint: disable=too-many-locals,too-many-nested-blocks,too-many-branches
class IPFabricDiffSync(DiffSyncModelAdapters):
    """IPFabric adapter for DiffSync."""

    def __init__(self, job, sync, client: IPFClient, location_filter, *args, **kwargs):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        # Resolved once addressing is read, and empty when addresses are out of scope.
        self.subnet_mask_by_address = {}
        if location_filter:
            self.client.attribute_filters = {"siteName": ["ieq", location_filter]}
            logging.info("Applied IP Fabric Attribute Filter: %s", self.client.attribute_filters)

    def load_sites(self):
        """Add IP Fabric Location objects as DiffSync Location models.

        Loaded even when Locations are out of scope, since Devices and VLANs are their children, but
        then as tree nodes carrying placeholder attributes rather than as data to write.
        """
        sites = self.client.inventory.sites.all()
        for site in sites:
            try:
                self.add(self.location_model(site["siteName"], site_id=site["id"], status="Active"))
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Location discovered, {site}")

    def load_device_interfaces(self, device_model, device_interfaces, device_primary_ip):
        """Create and load DiffSync Interface model objects for a specific device."""
        # The pseudo interface exists only to carry a NAT management address, so with addresses out
        # of scope there is nothing for it to hold. Skipped rather than passed a null address, which
        # `pseudo_management_interface` reads as "no Interface claims it" and so fabricates one for.
        pseudo_interface = (
            pseudo_management_interface(device_model.name, device_interfaces, device_primary_ip)
            if self.scope.ip_addresses
            else None
        )

        if pseudo_interface:
            device_interfaces.append(pseudo_interface)
            logger.info("Pseudo MGMT Interface: %s", pseudo_interface)

        for iface in device_interfaces:
            # loginIpv4 is available in 7.3+, fallback to primaryIp for older versions
            if not self.scope.ip_addresses:
                # Reported as absent rather than skipped, so that the Nautobot adapter's matching
                # `None` leaves the existing address alone instead of diffing against it.
                ip_address = None
                subnet_mask = None
            elif ip_address := iface.get("primaryIp") or iface.get("loginIpv4"):
                # One mask per address rather than per device: see `subnet_masks_by_address`.
                subnet_mask = self.subnet_mask_by_address.get(ip_address, "255.255.255.255")
            else:
                subnet_mask = None

            iface_name = iface["intName"]
            if IP_FABRIC_USE_CANONICAL_INTERFACE_NAME:
                iface_name = canonical_interface_name(iface_name)
            try:
                interface = self.interface(
                    name=iface_name,
                    device_name=iface.get("hostname"),
                    description=iface.get("dscr", ""),
                    enabled=True,
                    mac_address=(
                        mac_to_format(iface.get("mac"), "MAC_COLON_TWO").upper()
                        if iface.get("mac")
                        else DEFAULT_INTERFACE_MAC
                    ),
                    mtu=iface.get("mtu") if iface.get("mtu") else DEFAULT_INTERFACE_MTU,
                    type=ipfabric_utils.convert_media_type(iface.get("media"), iface_name),
                    mgmt_only=iface.get("mgmt_only", False),
                    ip_address=ip_address,
                    subnet_mask=subnet_mask,
                    ip_is_primary=(
                        self.scope.primary_ip and ip_address is not None and ip_address == device_primary_ip
                    ),
                    status="Active",
                )
                self.add(interface)
                device_model.add_child(interface)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Interface discovered, {iface}")

    @staticmethod
    def link_endpoint(link, side):
        """Return the "local" or "remote" side of a connectivity matrix entry as an endpoint."""
        hostname = link.get(f"{side}Host")
        interface_name = link.get(f"{side}Int")
        if not hostname or not interface_name:
            return None
        if IP_FABRIC_USE_CANONICAL_INTERFACE_NAME:
            interface_name = canonical_interface_name(interface_name)
        return hostname, interface_name

    def endpoints_are_cableable(self, *endpoints):
        """Determine whether a Cable can be synced between the given endpoints.

        Both Interfaces must have been loaded, since a Location filter or a stack member's interfaces
        being reported against its master can leave one end out of scope. Both must also be of a type
        Nautobot will cable, as `Cable.clean()` rejects the virtual and wireless types that IP Fabric
        reports tunnel links over.
        """
        for device_name, interface_name in endpoints:
            try:
                interface = self.get(self.interface, {"name": interface_name, "device_name": device_name})
            except ObjectNotFound:
                if self.job.debug:
                    logger.debug(
                        "Not syncing a Cable for %s:%s as no such Interface was loaded", device_name, interface_name
                    )
                return False
            if interface.type in NONCONNECTABLE_IFACE_TYPES:
                if self.job.debug:
                    logger.debug(
                        "Not syncing a Cable for %s:%s as Nautobot will not cable a %s Interface",
                        device_name,
                        interface_name,
                        interface.type,
                    )
                return False
        return True

    def reported_links(self):
        """Return the links the connectivity matrix describes, as canonically ordered endpoint pairs.

        A set, because the matrix reports each link once from each of its two devices and both
        reports reduce to the same pair.
        """
        links = set()
        for link in self.client.technology.interfaces.connectivity_matrix.all():
            local = self.link_endpoint(link, "local")
            remote = self.link_endpoint(link, "remote")
            if not local or not remote:
                if self.job.debug:
                    logger.debug("Skipping connectivity matrix entry with an incomplete endpoint, %s", link)
                continue
            if local == remote:
                logger.warning(f"Skipping connectivity matrix entry that links an Interface to itself, {link}")
                continue
            links.add(canonical_endpoints(local, remote))
        return links

    def recordable_links(self):
        """Return the reported links Nautobot can record, which is at most one per Interface.

        An Interface terminates at most one Cable in every version this app supports. The versions
        that model breakout cables give one Cable several terminations per side; they do not give an
        Interface several Cables. IP Fabric describes a cloud subnet as a link from each Interface in
        it to the subnet, so one Interface can be reported on many links and only one can be kept.

        Taken in sorted order, so that the link kept is the same one on every run. Choosing
        differently between runs would leave each run deleting the Cable the run before it made.
        """
        taken = set()
        recordable = []
        unrecordable = defaultdict(int)
        for endpoints in sorted(self.reported_links()):
            if not self.endpoints_are_cableable(*endpoints):
                continue
            occupied = [endpoint for endpoint in endpoints if endpoint in taken]
            if occupied:
                for endpoint in occupied:
                    unrecordable[endpoint] += 1
                continue
            taken.update(endpoints)
            recordable.append(endpoints)

        for (device_name, interface_name), count in sorted(unrecordable.items()):
            logger.warning(
                "%s:%s is reported on %d further link(s), which Nautobot cannot record because an "
                "Interface terminates at most one Cable",
                device_name,
                interface_name,
                count,
            )
        return recordable

    def load_cables(self):
        """Add IP Fabric connectivity matrix entries as DiffSync Cable models."""
        for endpoint_a, endpoint_b in self.recordable_links():
            self.add(
                self.cable(
                    termination_a_device=endpoint_a[0],
                    termination_a_name=endpoint_a[1],
                    termination_b_device=endpoint_b[0],
                    termination_b_name=endpoint_b[1],
                    status=DEFAULT_CABLE_STATUS,
                )
            )

    def load_data(self):
        """Load shared data from IP Fabric.

        Each table is fetched only when something in scope reads it. These are the largest requests
        the job makes, so a narrowed sync should not pay to download and index a table it will never
        look at.
        """
        managed_ipv4 = defaultdict(dict)
        stacks, interfaces = defaultdict(list), defaultdict(list)
        vlans_by_location = defaultdict(list)

        if self.scope.vlans:
            for vlan in self.client.fetch_all("tables/vlan/site-summary"):
                vlans_by_location[vlan["siteName"]].append(vlan)

        if self.scope.ip_addresses:
            ip_columns = ["sn", "intName", "net", "ip", "type"]
            ip_filter = {"type": ["eq", "primary"]}
            for ip_address in self.client.technology.addressing.managed_ip_ipv4.all(
                columns=ip_columns, filters=ip_filter
            ):
                managed_ipv4[ip_address["sn"]].update({ip_address["ip"]: ip_address})
            self.subnet_mask_by_address = subnet_masks_by_address(managed_ipv4)

        # Get all interfaces for devices
        if self.scope.interfaces:
            for interface in self.client.inventory.interfaces.all():
                interfaces[interface["sn"]].append(interface)

        # Get all stacks for devices. Stack membership is Device data, so it is read whatever else is
        # in scope.
        for stack in self.client.technology.platforms.stacks_members.all(
            columns=["master", "member", "memberSn", "pn", "sn"]
        ):
            stacks[stack["sn"]].append(stack)
        return vlans_by_location, stacks, interfaces

    def load(self):  # pylint: disable=too-many-locals,too-many-statements
        """Load data from IP Fabric."""
        self.load_sites()
        vlans_by_location, stacks, interfaces = self.load_data()

        for location in self.get_all(self.location):
            if location.name is None:
                continue
            location_vlans = vlans_by_location.get(location.name, [])
            for vlan_record in location_vlans:
                vlan_name = vlan_record.get("vlanName")
                vlan_id = vlan_record["vlanId"]
                vlan_desc = vlan_record.get("dscr")
                if not vlan_id or not 1 <= vlan_id <= 4094:
                    logger.warning(f"Not syncing VLAN, NAME: {vlan_name} due to invalid VLAN ID: {vlan_id}.")
                    continue
                description = vlan_desc if vlan_desc else f"VLAN ID: {vlan_id}"
                vlan_label = vlan_name if vlan_name else f"{vlan_record['siteName']}:{vlan_id}"
                if len(vlan_label) > name_max_length:
                    logger.warning(
                        f"Not syncing VLAN, {vlan_label} due to character limit exceeding {name_max_length}."
                    )
                    continue
                try:
                    vlan = self.vlan(
                        name=vlan_label,
                        location=vlan_record["siteName"],
                        vid=vlan_id,
                        status="Active",
                        description=description,
                    )
                    self.add(vlan)
                    location.add_child(vlan)
                except ObjectAlreadyExists:
                    logger.warning(f"Duplicate VLAN discovered, {vlan}")
            for device in self.client.devices.by_site.get(location.name, []):
                base_args = {
                    "diffsync": self,
                    "location_name": device.site,
                    "model": device.model or f"Default-{device.vendor}",
                    "vendor": device.vendor.capitalize(),
                    "role": device.dev_type or DEFAULT_DEVICE_ROLE if SYNC_IPF_DEV_TYPE_TO_ROLE else None,
                    "status": DEFAULT_DEVICE_STATUS,
                    "platform": device.family,
                }
                if device.sn not in stacks:
                    serial_number = device.sn
                    args = base_args.copy()
                    args["name"] = device.hostname
                    args["serial_number"] = serial_number if len(serial_number) < device_serial_max_length else ""
                    member_devices = [args]
                else:
                    # member with the lowest member number will be considered master,
                    # and vc_priority and vc_position will both be derived from the member field,
                    # as the role field will depend on operational state and not config,
                    # and this will cause uneccessary diffs.
                    stack_members = stacks[device.sn]
                    stack_members.sort(key=lambda x: x["member"])
                    member_devices = []
                    for index, member in enumerate(stack_members):
                        # using `or` syntax in case memberSn is defined as None
                        member_sn = member.get("memberSn") or ""
                        args = base_args.copy()
                        if pn := member.get("pn"):
                            args["model"] = pn
                        args.update(
                            {
                                "serial_number": member_sn if len(member_sn) < device_serial_max_length else "",
                                "name": f"{device.hostname}-member{member.get('member')}",
                                "vc_name": device.hostname,
                                "vc_master": False,
                                "vc_priority": member.get("member"),
                                "vc_position": member.get("member"),
                            }
                        )
                        if index == 0:
                            args.update(
                                {
                                    "name": device.hostname,
                                    "vc_master": True,
                                }
                            )
                        member_devices.append(args)

                for index, dev in enumerate(member_devices):
                    if not dev["serial_number"]:
                        logger.warning(
                            f"Serial Number will not be recorded for {dev['name']} due to character limit exceeds {device_serial_max_length}"
                        )
                    try:
                        device_model = self.device(**dev)
                        self.add(device_model)
                        location.add_child(device_model)
                        if index == 0:
                            # TODO: New Login IP columns in 7.3
                            device_primary_ip = str(device.login_ip.ip) if device.login_ip else None
                            if self.scope.interfaces:
                                self.load_device_interfaces(
                                    device_model,
                                    interfaces.get(device.sn, []),
                                    device_primary_ip,
                                )
                    except ObjectAlreadyExists:
                        logger.warning(f"Duplicate Device discovered, {device.model_dump()}")

        if self.scope.cables:
            self.load_cables()


def pseudo_management_interface(hostname, device_interfaces, device_primary_ip):
    """Return a dict for an non-existing interface for NAT management addresses."""
    if any(iface for iface in device_interfaces if iface.get("primaryIp", "") == device_primary_ip):
        return None
    return {
        "hostname": hostname,
        "intName": PSEUDO_MANAGEMENT_INTERFACE_NAME,
        "dscr": "pseudo interface for NAT IP address",
        "primaryIp": device_primary_ip,
        "type": "virtual",
        "mgmt_only": True,
    }


def subnet_masks_by_address(managed_ipv4):
    """Return one subnet mask per address, the narrowest of those reported for it.

    IP Fabric indexes addressing by serial number and so describes a subnet per device. An address
    on two devices can therefore be reported in two subnets, while Nautobot holds one mask per
    address, so two Interfaces sharing an address cannot each carry the mask reported for them. One
    mask is chosen here, for every Interface holding that address, so that the two sides agree.

    The narrowest report is the one chosen, because it agrees with the address's parent: Nautobot
    parents an address to the most specific Prefix containing it. A fixed rule rather than the order
    IP Fabric answers in, which is not guaranteed.
    """
    lengths = {}
    contested = set()
    for by_address in managed_ipv4.values():
        for address, record in by_address.items():
            if not record.get("net"):
                continue
            length = ipaddress.ip_network(record["net"], strict=False).prefixlen
            if address in lengths and lengths[address] != length:
                contested.add(address)
            lengths[address] = max(length, lengths.get(address, 0))
    for address in sorted(contested):
        logger.warning(
            "IP Fabric reports %s in more than one subnet, so its Interfaces cannot each carry "
            "the mask reported for them; using the narrowest, /%d",
            address,
            lengths[address],
        )
    return {address: cidr_to_netmask(length) for address, length in lengths.items()}
