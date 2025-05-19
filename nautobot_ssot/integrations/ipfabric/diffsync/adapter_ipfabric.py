# pylint: disable=duplicate-code
"""DiffSync adapter class for Ip Fabric."""

import ipaddress
import logging
from collections import defaultdict

from diffsync import ObjectAlreadyExists
from nautobot.dcim.models import Device
from nautobot.ipam.models import VLAN
from netutils.interface import canonical_interface_name
from netutils.mac import mac_to_format

from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_STATUS,
    DEFAULT_INTERFACE_MAC,
    DEFAULT_INTERFACE_MTU,
    IP_FABRIC_USE_CANONICAL_INTERFACE_NAME,
    SYNC_IPF_DEV_TYPE_TO_ROLE,
)
from nautobot_ssot.integrations.ipfabric.diffsync import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.utilities import utils as ipfabric_utils

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
        if location_filter:
            self.client.attribute_filters = {"siteName": ["ieq", location_filter]}
            logging.info("Applied IP Fabric Attribute Filter: %s", self.client.attribute_filters)

    def load_sites(self):
        """Add IP Fabric Location objects as DiffSync Location models."""
        sites = self.client.inventory.sites.all()
        for site in sites:
            try:
                location = self.location(adapter=self, name=site["siteName"], site_id=site["id"], status="Active")
                self.add(location)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Location discovered, {site}")

    def load_device_interfaces(self, device_model, device_interfaces, device_primary_ip, managed_ipv4):
        """Create and load DiffSync Interface model objects for a specific device."""
        pseudo_interface = pseudo_management_interface(device_model.name, device_interfaces, device_primary_ip)

        if pseudo_interface:
            device_interfaces.append(pseudo_interface)
            logger.info("Pseudo MGMT Interface: %s", pseudo_interface)

        for iface in device_interfaces:
            # TODO: New Login IP columns in 7.3
            if ip_address := iface.get("primaryIp"):
                subnet_mask = (
                    str(ipaddress.ip_interface(managed_ipv4[ip_address]["net"]).netmask)
                    if ip_address in managed_ipv4
                    else "255.255.255.255"
                )
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
                    ip_is_primary=ip_address is not None and ip_address == device_primary_ip,
                    status="Active",
                )
                self.add(interface)
                device_model.add_child(interface)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Interface discovered, {iface}")

    def load_data(self):
        """Load shared data from IP Fabric."""
        managed_ipv4 = defaultdict(dict)
        stacks, interfaces = defaultdict(list), defaultdict(list)

        vlans = self.client.fetch_all("tables/vlan/site-summary")

        ip_columns = ["sn", "intName", "net", "ip", "type"]
        ip_filter = {"type": ["eq", "primary"]}

        for ip_address in self.client.technology.addressing.managed_ip_ipv4.all(columns=ip_columns, filters=ip_filter):
            managed_ipv4[ip_address["sn"]].update({ip_address["ip"]: ip_address})

        # Get all interfaces for devices
        for interface in self.client.inventory.interfaces.all():
            interfaces[interface["sn"]].append(interface)

        # Get all stacks for devices
        for stack in self.client.technology.platforms.stacks_members.all(
            columns=["master", "member", "memberSn", "pn", "sn"]
        ):
            stacks[stack["sn"]].append(stack)
        return managed_ipv4, vlans, stacks, interfaces

    def load(self):  # pylint: disable=too-many-locals,too-many-statements
        """Load data from IP Fabric."""
        self.load_sites()
        managed_ipv4, vlans, stacks, interfaces = self.load_data()

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
                        if _ := member.get("pn"):
                            args["model"] = _
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
                            self.load_device_interfaces(
                                device_model,
                                interfaces.get(device.sn, []),
                                device_primary_ip,
                                managed_ipv4.get(device.sn, {}),
                            )
                    except ObjectAlreadyExists:
                        logger.warning(f"Duplicate Device discovered, {device.model_dump()}")


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
