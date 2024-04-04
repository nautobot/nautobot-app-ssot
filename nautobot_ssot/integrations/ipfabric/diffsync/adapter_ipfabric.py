# pylint: disable=duplicate-code
"""DiffSync adapter class for Ip Fabric."""
import ipaddress

from diffsync import ObjectAlreadyExists
from nautobot.dcim.models import Device
from nautobot.ipam.models import VLAN
from netutils.mac import mac_to_format
from netutils.interface import canonical_interface_name
from ipfabric import IPFClient
from collections import defaultdict
from ipaddress import IPv4Interface, IPv6Interface, AddressValueError

from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_INTERFACE_MTU,
    DEFAULT_INTERFACE_MAC,
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_STATUS,
    IP_FABRIC_USE_CANONICAL_INTERFACE_NAME,
)
from nautobot_ssot.integrations.ipfabric.diffsync import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.utilities import utils as ipfabric_utils
from celery.utils.log import get_task_logger


logger = get_task_logger("ssot_ipfabric.jobs")

device_serial_max_length = Device._meta.get_field("serial").max_length
name_max_length = VLAN._meta.get_field("name").max_length


class IPFabricDiffSync(DiffSyncModelAdapters):
    """Nautobot adapter for DiffSync."""

    def __init__(self, job, sync, client: IPFClient, *args, **kwargs):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        self.logger = logger

    def load_sites(self):
        """Add IP Fabric Location objects as DiffSync Location models."""
        sites = self.client.inventory.sites.all()
        for site in sites:
            try:
                location = self.location(name=site["siteName"], site_id=site["id"], status="Active")
                self.add(location)
            except ObjectAlreadyExists:
                self.logger.warning(f"Duplicate Location discovered, {site}")

    def load_device_interfaces(self, device_model, interfaces, device_primary_ip, managed_ipv4, managed_ipv6):
        """Create and load DiffSync Interface model objects for a specific device."""
        pseudo_interface = pseudo_management_interface(device_model.name, interfaces, device_primary_ip)

        if pseudo_interface:
            interfaces.append(pseudo_interface)
            self.logger.info("Pseudo MGMT Interface: %s", pseudo_interface)

        total_interfaces = len(interfaces)
        self.logger.info("Total Interfaces: %s on Device %s", total_interfaces, device_model.name)
        for index, iface in enumerate(interfaces, start=1):
            if index % 10 == 0:
                self.logger.info("Processed %s interfaces, %s remaining", index, total_interfaces - index)
            self.logger.debug("Interface: %s", iface)
            self.logger.debug("Device Hostname: %s", iface.get("hostname"))
            ip_address_v4 = iface.get("primaryIp")
            iface_name = iface["intName"]
            subnet_v4 = "255.255.255.255"
            ipv6_address = None
            subnetv6 = None
            #  These ifs can be simplified, but for readability, they are kept separate
            #  If ip_address_v4 is None, then interface is more than likely a management interface
            #  Example:
            # {
            #     "siteName": "35COLO",
            #     "id": "1526185967",
            #     "loginIp": "10.35.253.51",
            #     "primaryIp": None,
            #     "hostname": "L35FW2",
            #     "mac": "5000.0008.0000",
            #     "intName": "Management0/0",
            #     "sn": "9AJR4UMXS30",
            #     "nameOriginal": "Management0/0",
            # }
            if ip_address_v4 is not None:
                managed_ipv4_int = next((iface for iface in managed_ipv4 if iface['ip'] == ip_address_v4), None)
                if managed_ipv4_int is not None:
                    self.logger.debug("Managed IPv4 Interface: %s", managed_ipv4_int)
                    if managed_ipv4_int['net'] is not None:
                        host_net_v4 = IPv4Interface(managed_ipv4_int['net'])
                        subnet_v4 = str(host_net_v4.network.netmask)
                        #  If the net is None, then the interface is a Tunnel interface
                        #  Example:
                        # {
                        #     "hostname": "L77R12-LEAF6",
                        #     "sn": "9HSVSJPXSWU",
                        #     "intName": "Tu2",
                        #     "stateL1": "up",
                        #     "stateL2": "up",
                        #     "siteName": "L77",
                        #     "dnsName": null,
                        #     "dnsHostnameMatch": -1,
                        #     "vlanId": null,
                        #     "dnsReverseMatch": -1,
                        #     "mac": null,
                        #     "ip": "10.77.162.12",
                        #     "net": null,
                        #     "type": "unnumbered",
                        #     "vrf": ""
                        # },
                ipv6_address_int = next((iface for iface in managed_ipv6 if iface['intName'] == iface_name),
                                        None)
                if ipv6_address_int is not None:
                    self.logger.debug("Managed IPv6 Interface: %s", ipv6_address_int)
                    host_net_v6 = IPv6Interface(ipv6_address_int['net'])
                    subnetv6 = str(host_net_v6.network.netmask)
                    ipv6_address = host_net_v6.network.compressed.split('/')[0]
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
                    type=ipfabric_utils.convert_media_type(iface.get("media") or ""),
                    mgmt_only=iface.get("mgmt_only", False),
                    ip_address=ip_address_v4,
                    subnet_mask=subnet_v4,
                    ipv6_address=ipv6_address,
                    subnetv6_mask=subnetv6,
                    ip_is_primary=ip_address_v4 is not None and ip_address_v4 == device_primary_ip,
                    status="Active",
                )
                self.add(interface)
                device_model.add_child(interface)
            except ObjectAlreadyExists:
                self.logger.warning(f"Duplicate Interface discovered, {iface}")

    def managed_ip(self):
        ip_columns = ['sn', 'intName', 'net', 'ip', 'type']
        ip_filter = {'type': ['eq', 'primary']}
        managed_ipv4, managed_ipv6 = defaultdict(dict), defaultdict(dict)
        for ip in self.client.technology.addressing.managed_ip_ipv4.all(columns=ip_columns, filters=ip_filter):
            managed_ipv4[ip['sn']].update({ip['ip']: ip})
        for ip in self.client.technology.addressing.managed_ip_ipv6.all(columns=ip_columns, filters=ip_filter):
            managed_ipv4[ip['sn']].update({ip['intName']: ip})
        return managed_ipv4, managed_ipv6

    def load(self):
        """Load data from IP Fabric."""
        self.load_sites()
        devices = self.client.devices.all
        interfaces = self.client.inventory.interfaces.all()
        managed_ipv4, managed_ipv6 = self.managed_ip()
        vlans = self.client.fetch_all("tables/vlan/site-summary")
        networks = defaultdict(list)
        for network in self.client.technology.managed_networks.networks.all(
            filters={"net": ["empty", False], "siteName": ["empty", False]},
            columns=["net", "siteName"],
        ):
            networks[network["siteName"]].append(ipaddress.ip_network(ipaddress.IPv4Interface(network["net"]).netmask))
        for location in self.get_all(self.location):
            if location.name is None:
                continue
            location_vlans = [vlan for vlan in vlans if vlan["siteName"] == location.name]
            for vlan in location_vlans:
                if not vlan["vlanId"] or (vlan["vlanId"] < 1 or vlan["vlanId"] > 4094):
                    self.logger.warning(
                        f"Not syncing VLAN, NAME: {vlan.get('vlanName')} due to invalid VLAN ID: {vlan.get('vlanId')}."
                    )
                    continue
                description = vlan.get("dscr") if vlan.get("dscr") else f"VLAN ID: {vlan['vlanId']}"
                vlan_name = vlan.get("vlanName") if vlan.get("vlanName") else f"{vlan['siteName']}:{vlan['vlanId']}"
                if len(vlan_name) > name_max_length:
                    self.logger.warning(f"Clipping VLAN, {vlan_name} due to character limit exceeding {name_max_length}.")
                    vlan_name = vlan_name[:name_max_length - 3] + '...'
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
                    self.logger.warning(f"Duplicate VLAN discovered, {vlan}")

            location_devices = [device for device in devices if device.site_name == location.name]
            for device in location_devices:
                device_primary_ip = str(device.login_ip.ip) if device.login_ip else None
                serial_number = device.sn
                if len(serial_number) > device_serial_max_length:
                    logger.warning(
                        f"Clipping Serial Number for {device['hostname']} due to character limit exceeding "
                        f"{device_serial_max_length}."
                    )
                    serial_number = serial_number[:device_serial_max_length]
                try:
                    device_model = self.device(
                        name=device.hostname,
                        location_name=device.site_name,
                        model=device.model if device.model else f"Default-{device.vendor}",
                        vendor=device.vendor.capitalize(),
                        serial_number=serial_number,
                        role=device.dev_type if device.dev_type else DEFAULT_DEVICE_ROLE,
                        status=DEFAULT_DEVICE_STATUS,
                        platform=device.family,
                    )
                    self.add(device_model)
                    location.add_child(device_model)
                    self.load_device_interfaces(
                        device_model,
                        self.client.devices.by_sn[serial_number].interfaces(),
                        device_primary_ip,
                        self.client.devices.by_sn[serial_number].managed_ip_ipv4(),
                        self.client.devices.by_sn[serial_number].managed_ip_ipv6()
                    )
                except ObjectAlreadyExists:
                    logger.warning(f"Duplicate Device discovered, {device}")
                device_name = device.hostname
                stack_members = None
                if self.client.devices.by_sn[serial_number].fetch_all("tables/platforms/stack/members"):
                    stack_members = self.client.technology.platforms.stacks_members.all(
                        filters={"master": ["eq", device_name], "siteName": ["eq", location.name]},
                        columns=["master", "member", "memberSn", "pn"],
                    )
                base_args = {
                    "diffsync": self,
                    "location_name": device.site_name,
                    "model": device.model if device.model else f"Default-{device.vendor}",
                    "vendor": device.vendor.capitalize(),
                    "role": device.dev_type if device.dev_type else DEFAULT_DEVICE_ROLE,
                    "status": DEFAULT_DEVICE_STATUS,
                    "platform": device.family,
                }
                if not stack_members:
                    serial_number = device.sn
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

                device_primary_ip = device.login_ip
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
                            self.load_device_interfaces(
                                device_model,
                                self.client.devices.by_sn[serial_number].interfaces(),
                                device_primary_ip,
                                self.client.devices.by_sn[serial_number].managed_ip_ipv4(),
                                self.client.devices.by_sn[serial_number].managed_ip_ipv6()
                            )
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
