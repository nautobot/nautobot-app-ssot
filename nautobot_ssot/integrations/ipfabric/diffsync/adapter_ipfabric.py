# pylint: disable=duplicate-code
"""DiffSync adapter class for Ip Fabric."""

import logging

from diffsync import ObjectAlreadyExists
from nautobot.dcim.models import Device
from nautobot.ipam.models import VLAN
from netutils.mac import mac_to_format
from netutils.interface import canonical_interface_name
from ipfabric import IPFClient
from collections import defaultdict
from ipaddress import IPv4Network, IPv6Network, AddressValueError

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


class IPFabricDiffSync(DiffSyncModelAdapters):
    """Nautobot adapter for DiffSync."""

    def __init__(self, job, sync, client: IPFClient, *args, **kwargs):
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

    def load_device_interfaces(self, device_model, interfaces, device_primary_ip, managed_ipv4, managed_ipv6):
        """Create and load DiffSync Interface model objects for a specific device."""
        pseudo_interface = pseudo_management_interface(device_model.name, interfaces, device_primary_ip)

        if pseudo_interface:
            interfaces.append(pseudo_interface)
            logger.info("Pseudo MGMT Interface: %s", pseudo_interface)

        for iface in interfaces:
            ip_address = iface.get("primaryIp")
            iface_name = iface["intName"]
            try:
                subnet = str(IPv4Network(managed_ipv4[ip_address]['net'], strict=False).netmask)
            except (KeyError, AddressValueError):
                subnet = "255.255.255.255"
            try:
                ipv6_address = IPv6Network(managed_ipv6[iface_name]['net'], strict=False)
                subnetv6 = str(ipv6_address.netmask)
                ipv6_address = ipv6_address.compressed.split('/')[0]
            except (KeyError, AddressValueError):
                ipv6_address, subnetv6 = None, None
            if IP_FABRIC_USE_CANONICAL_INTERFACE_NAME:
                iface_name = canonical_interface_name(iface_name)
            try:
                interface = self.interface(
                    diffsync=self,
                    name=iface_name,
                    device_name=iface.get("hostname"),
                    description=iface.get("dscr", ""),
                    enabled=True,
                    mac_address=mac_to_format(iface.get("mac"), "MAC_COLON_TWO").upper()
                    if iface.get("mac")
                    else DEFAULT_INTERFACE_MAC,
                    mtu=iface.get("mtu") if iface.get("mtu") else DEFAULT_INTERFACE_MTU,
                    type=ipfabric_utils.convert_media_type(iface.get("media") or ""),
                    mgmt_only=iface.get("mgmt_only", False),
                    ip_address=ip_address,
                    subnet_mask=subnet,
                    ipv6_address=ipv6_address,
                    subnetv6_mask=subnetv6,
                    ip_is_primary=ip_address is not None and ip_address == device_primary_ip,
                    status="Active",
                )
                self.add(interface)
                device_model.add_child(interface)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Interface discovered, {iface}")

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
                    logger.warning(f"Clipping VLAN, {vlan_name} due to character limit exceeding {name_max_length}.")
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
                    logger.warning(f"Duplicate VLAN discovered, {vlan}")

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
                        diffsync=self,
                        name=device.hostname,
                        location_name=device.site_name,
                        model=device.model if device.model else f"Default-{device.get('vendor')}",
                        vendor=device.vendor.capitalize(),
                        serial_number=serial_number,
                        role=device.dev_type if device.dev_type else DEFAULT_DEVICE_ROLE,
                        status=DEFAULT_DEVICE_STATUS,
                        platform=device.family,
                    )
                    self.add(device_model)
                    location.add_child(device_model)
                    self.load_device_interfaces(
                        device_model, interfaces.get(device.sn, []), device_primary_ip, managed_ipv4.get(device.sn, {}),
                        managed_ipv6.get(device.sn, {})
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
