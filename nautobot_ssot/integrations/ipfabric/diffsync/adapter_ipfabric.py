# pylint: disable=duplicate-code
"""DiffSync adapter class for Ip Fabric."""
import ipaddress
import logging
from collections import defaultdict

from diffsync import ObjectAlreadyExists
from nautobot.dcim.models import Device
from nautobot.ipam.models import VLAN
from netutils.mac import mac_to_format
from netutils.interface import canonical_interface_name

from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_INTERFACE_MTU,
    DEFAULT_INTERFACE_MAC,
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_STATUS,
    IP_FABRIC_USE_CANONICAL_INTERFACE_NAME,
)
from nautobot_ssot.integrations.ipfabric.diffsync import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.utilities import utils as ipfabric_utils


logger = logging.getLogger("nautobot.jobs")

device_serial_max_length = Device._meta.get_field("serial").max_length
name_max_length = VLAN._meta.get_field("name").max_length


# pylint: disable=too-many-locals,too-many-nested-blocks,too-many-branches
class IPFabricDiffSync(DiffSyncModelAdapters):
    """IPFabric adapter for DiffSync."""

    def __init__(self, job, sync, client, *args, **kwargs):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client

    def load_sites(self):
        """Add IP Fabric Location objects as DiffSync Location models."""
        sites = self.client.inventory.sites.all()
        for site in sites:
            try:
                location = self.location(diffsync=self, name=site["siteName"], site_id=site["id"], status="Active")
                self.add(location)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Location discovered, {site}")

    def load_device_interfaces(self, device_model, interfaces, device_primary_ip, networks):
        """Create and load DiffSync Interface model objects for a specific device."""
        device_interfaces = [iface for iface in interfaces if iface.get("hostname") == device_model.name]
        pseudo_interface = pseudo_management_interface(device_model.name, device_interfaces, device_primary_ip)

        if pseudo_interface:
            device_interfaces.append(pseudo_interface)
            logger.info("Pseudo MGMT Interface: %s", pseudo_interface)

        for iface in device_interfaces:
            subnet_mask = None
            ip_address = iface.get("primaryIp")
            if ip_address:
                ip_network = ipaddress.ip_network(ip_address)
                for network in networks[device_model.location_name]:
                    if network.supernet_of(ip_network):
                        subnet_mask = str(network.netmask)
                        break
                else:
                    subnet_mask = None
                    for site_name, site_networks in networks.items():
                        # Already checked networks for the site
                        if site_name == device_model.location_name:
                            continue
                        for network in site_networks:
                            if network.supernet_of(ip_network):
                                subnet_mask = str(network.netmask)
                                break
                        if subnet_mask:
                            break
                    else:
                        # TODO: why is only IPv4?
                        subnet_mask = "255.255.255.255"

            iface_name = iface["intName"]
            if IP_FABRIC_USE_CANONICAL_INTERFACE_NAME:
                iface_name = canonical_interface_name(iface_name)
            try:
                interface = self.interface(
                    diffsync=self,
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
                    ip_is_primary=ip_address is not None and ip_address == device_primary_ip,
                    status="Active",
                )
                self.add(interface)
                device_model.add_child(interface)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Interface discovered, {iface}")

    def load(self):  # pylint: disable=too-many-locals,too-many-statements
        """Load data from IP Fabric."""
        self.load_sites()
        devices = self.client.inventory.devices.all()
        interfaces = self.client.inventory.interfaces.all()
        vlans = self.client.fetch_all("tables/vlan/site-summary")
        networks = defaultdict(list)
        for network in self.client.technology.managed_networks.networks.all(
            filters={"net": ["empty", False], "siteName": ["empty", False]},
            columns=["net", "siteName"],
        ):
            networks[network["siteName"]].append(ipaddress.ip_network(network["net"]))
        for location in self.get_all(self.location):
            if location.name is None:
                continue
            location_vlans = [vlan for vlan in vlans if vlan["siteName"] == location.name]
            for vlan in location_vlans:
                if not vlan["vlanId"] or (vlan["vlanId"] < 1 or vlan["vlanId"] > 4094):
                    logger.warning(
                        f"Not syncing VLAN, NAME: {vlan.get('vlanName')} due to invalid VLAN ID: {vlan.get('vlanId')}."
                    )
                    continue
                description = vlan.get("dscr") if vlan.get("dscr") else f"VLAN ID: {vlan['vlanId']}"
                vlan_name = vlan.get("vlanName") if vlan.get("vlanName") else f"{vlan['siteName']}:{vlan['vlanId']}"
                if len(vlan_name) > name_max_length:
                    logger.warning(f"Not syncing VLAN, {vlan_name} due to character limit exceeding {name_max_length}.")
                    continue
                try:
                    vlan = self.vlan(
                        diffsync=self,
                        name=vlan_name,
                        location=vlan["siteName"],
                        vid=vlan["vlanId"],
                        status="Active",
                        description=description,
                    )
                    self.add(vlan)
                    location.add_child(vlan)
                except ObjectAlreadyExists:
                    logger.warning(f"Duplicate VLAN discovered, {vlan}")
            location_devices = [device for device in devices if device["siteName"] == location.name]
            for device in location_devices:
                device_name = device["hostname"]
                stack_members = self.client.technology.platforms.stacks_members.all(
                    filters={"master": ["eq", device_name], "siteName": ["eq", location.name]},
                    columns=["master", "member", "memberSn", "pn"],
                )
                base_args = {
                    "diffsync": self,
                    "location_name": device["siteName"],
                    "model": device.get("model") if device.get("model") else f"Default-{device.get('vendor')}",
                    "vendor": device.get("vendor").capitalize(),
                    "role": device.get("devType") if device.get("devType") else DEFAULT_DEVICE_ROLE,
                    "status": DEFAULT_DEVICE_STATUS,
                    "platform": device.get("family"),
                }
                if not stack_members:
                    serial_number = device["sn"]
                    sn_length = len(serial_number)
                    args = base_args.copy()
                    args["name"] = device_name
                    args["serial_number"] = serial_number if sn_length < device_serial_max_length else ""
                    member_devices = [args]
                else:
                    # member with the lowest member number will be considered master,
                    # and vc_priority and vc_position will both be derived from the member field,
                    # as the role field will depend on operational state and not config,
                    # and this will cause uneccessary diffs.
                    stack_members.sort(key=lambda x: x["member"])
                    member_devices = []
                    for index, member in enumerate(stack_members):
                        # using `or` syntax in case memberSn is defined as None
                        member_sn = member.get("memberSn") or ""
                        member_sn_length = len(member_sn)
                        args = base_args.copy()
                        model = member.get("pn")
                        if model:
                            args["model"] = model
                        args["serial_number"] = member_sn if member_sn_length < device_serial_max_length else ""
                        args["vc_name"] = device_name
                        member_field = member.get("member")
                        args["vc_priority"] = member_field
                        args["vc_position"] = member_field
                        if index == 0:
                            args["name"] = device_name
                            args["vc_master"] = True
                        else:
                            args["name"] = f"{device_name}-member{member_field}"
                            args["vc_master"] = False
                        member_devices.append(args)

                device_primary_ip = device["loginIp"]
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
                            self.load_device_interfaces(device_model, interfaces, device_primary_ip, networks)
                    except ObjectAlreadyExists:
                        logger.warning(f"Duplicate Device discovered, {device}")


def pseudo_management_interface(hostname, device_interfaces, device_primary_ip):
    """Return a dict for an non-existing interface for NAT management addresses."""
    if any(iface for iface in device_interfaces if iface.get("primaryIp", "") == device_primary_ip):
        return None
    return {
        "hostname": hostname,
        "intName": "pseudo_mgmt",
        "dscr": "pseudo interface for NAT IP address",
        "primaryIp": device_primary_ip,
        "type": "virtual",
        "mgmt_only": True,
    }
