"""DiffSync adapter for Arista CloudVision."""
import distutils
import re

import arista.tag.v2 as TAG
from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound

from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS
from nautobot_ssot.integrations.aristacv.diffsync.models.cloudvision import (
    CloudvisionCustomField,
    CloudvisionDevice,
    CloudvisionPort,
    CloudvisionIPAddress,
)
from nautobot_ssot.integrations.aristacv.utils import cloudvision


class CloudvisionAdapter(DiffSync):
    """DiffSync adapter implementation for CloudVision user-defined device tags."""

    device = CloudvisionDevice
    port = CloudvisionPort
    ipaddr = CloudvisionIPAddress
    cf = CloudvisionCustomField

    top_level = ["device", "ipaddr", "cf"]

    def __init__(self, *args, job=None, conn: cloudvision.CloudvisionApi, **kwargs):
        """Initialize the CloudVision DiffSync adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.conn = conn

    def load_devices(self):
        """Load devices from CloudVision."""
        if APP_SETTINGS.get("create_controller"):
            cvp_version = cloudvision.get_cvp_version()
            cvp_ver_cf = self.cf(name="arista_eos", value=cvp_version, device_name="CloudVision")
            try:
                self.add(cvp_ver_cf)
            except ObjectAlreadyExists as err:
                self.job.log_warning(
                    message=f"Unable to add CustomField for EOS Version for CloudVision device as already exists. {err}"
                )
            new_cvp = self.device(
                name="CloudVision",
                serial="",
                status="active",
                device_model="CloudVision",
                version=cvp_version,
                uuid=None,
            )
            try:
                self.add(new_cvp)
            except ObjectAlreadyExists as err:
                self.job.log_warning(message=f"Error attempting to add CloudVision device. {err}")
        for dev in cloudvision.get_devices(client=self.conn.comm_channel):
            if dev["hostname"] != "":
                new_device = self.device(
                    name=dev["hostname"],
                    serial=dev["device_id"],
                    status=dev["status"],
                    device_model=dev["model"],
                    version=dev["sw_ver"],
                    uuid=None,
                )
                try:
                    self.add(new_device)
                except ObjectAlreadyExists as err:
                    self.job.log_warning(
                        message=f"Duplicate device {dev['hostname']} {dev['device_id']} found and ignored. {err}"
                    )
                    continue
                self.load_interfaces(device=new_device)
                self.load_ip_addresses(dev=new_device)
                self.load_device_tags(device=new_device)
            else:
                self.job.log_warning(message=f"Device {dev} is missing hostname so won't be imported.")
                continue

    def load_interfaces(self, device):
        """Load device interface from CloudVision."""
        chassis_type = cloudvision.get_device_type(client=self.conn, dId=device.serial)
        if self.job.kwargs.get("debug"):
            self.job.log_debug(message=f"Chassis type for {device.name} is {chassis_type}.")
        port_info = []
        if chassis_type == "modular":
            port_info = cloudvision.get_interfaces_chassis(client=self.conn, dId=device.serial)
        elif chassis_type == "fixedSystem":
            port_info = cloudvision.get_interfaces_fixed(client=self.conn, dId=device.serial)
        elif chassis_type == "Unknown":
            self.job.log_warning(
                message=f"Unable to determine chassis type for {device.name} so will be unable to retrieve interfaces."
            )
            return None
        if self.job.kwargs.get("debug"):
            self.job.log_debug(message=f"Device being loaded: {device.name}. Port: {port_info}.")
        for port in port_info:
            if self.job.kwargs.get("debug"):
                self.job.log_debug(message=f"Port {port['interface']} being loaded for {device.name}.")
            port_mode = cloudvision.get_interface_mode(client=self.conn, dId=device.serial, interface=port)
            transceiver = cloudvision.get_interface_transceiver(client=self.conn, dId=device.serial, interface=port)
            if transceiver == "Unknown":
                # Breakout transceivers, ie 40G -> 4x10G, shows up as 4 interfaces and requires looking at base interface to find transceiver, ie Ethernet1 if Ethernet1/1
                base_port_name = re.sub(r"/\d", "", port["interface"])
                transceiver = cloudvision.get_interface_transceiver(
                    client=self.conn, dId=device.serial, interface=base_port_name
                )
            port_description = cloudvision.get_interface_description(
                client=self.conn, dId=device.serial, interface=port["interface"]
            )
            port_status = cloudvision.get_interface_status(port_info=port)
            port_type = cloudvision.get_port_type(port_info=port, transceiver=transceiver)
            if port["interface"] != "":
                new_port = self.port(
                    name=port["interface"],
                    device=device.name,
                    description=port_description,
                    mac_addr=port["mac_addr"] if port.get("mac_addr") else "",
                    mode="tagged" if port_mode == "trunk" else "access",
                    mtu=port["mtu"] if port.get("mtu") else 1500,
                    enabled=port["enabled"],
                    status=port_status,
                    port_type=port_type,
                    uuid=None,
                )
                try:
                    self.add(new_port)
                    device.add_child(new_port)
                except ObjectAlreadyExists as err:
                    self.job.log_warning(
                        message=f"Duplicate port {port['interface']} found for {device.name} and ignored. {err}"
                    )

    def load_ip_addresses(self, dev: device):
        """Load IP addresses from CloudVision."""
        dev_ip_intfs = cloudvision.get_ip_interfaces(client=self.conn, dId=dev.serial)
        for intf in dev_ip_intfs:
            if self.job.kwargs.get("debug"):
                self.job.log(message=f"Loading interface {intf['interface']} on {dev.name} for {intf['address']}.")
            try:
                _ = self.get(self.port, {"name": intf["interface"], "device": dev.name})
            except ObjectNotFound:
                new_port = self.port(
                    name=intf["interface"],
                    device=dev.name,
                    description=cloudvision.get_interface_description(
                        client=self.conn, dId=dev.serial, interface=intf["interface"]
                    ),
                    mac_addr="",
                    enabled=True,
                    mode="access",
                    mtu=65535,
                    port_type=cloudvision.get_port_type(port_info={"interface": intf["interface"]}, transceiver=""),
                    status="active",
                    uuid=None,
                )
                self.add(new_port)
                try:
                    device = self.get(self.device, dev.name)
                    device.add_child(new_port)
                except ObjectNotFound as err:
                    self.job.log_warning(
                        message=f"Unable to find device {dev.name} to assign port {intf['interface']}. {err}"
                    )

            if self.job.kwargs.get("debug"):
                self.job.log(
                    message=f"Attempting to load IP Address {intf['address']} for {intf['interface']} on {dev.name}."
                )
            if intf["address"] and intf["address"] != "none":
                new_ip = self.ipaddr(
                    address=intf["address"],
                    interface=intf["interface"],
                    device=dev.name,
                    uuid=None,
                )
                try:
                    self.add(new_ip)
                except ObjectAlreadyExists as err:
                    self.job.log_warning(
                        message=f"Unable to load {intf['address']} for {dev.name} on {intf['interface']}. {err}"
                    )
                    continue

    def load_device_tags(self, device):
        """Load device tags from CloudVision."""
        system_tags = cloudvision.get_tags_by_type(
            client=self.conn.comm_channel, creator_type=TAG.models.CREATOR_TYPE_SYSTEM
        )
        dev_tags = [
            tag
            for tag in cloudvision.get_device_tags(client=self.conn.comm_channel, device_id=device.serial)
            if tag in system_tags
        ]

        # Check if topology_type tag exists
        list_of_tag_names = [value["label"] for value in dev_tags]
        if "topology_type" not in list_of_tag_names:
            dev_tags.append({"label": "topology_type", "value": "-"})

        for tag in dev_tags:
            if tag["label"] in ["hostname", "serialnumber", "Container"]:
                continue
            if tag["label"] == "mpls" or tag["label"] == "ztp":
                tag["value"] = bool(distutils.util.strtobool(tag["value"]))

            new_cf = self.cf(name=f"arista_{tag['label']}", value=tag["value"], device_name=device.name)
            try:
                self.add(new_cf)
            except ObjectAlreadyExists:
                self.job.log_warning(message=f"Duplicate tag encountered for {tag['label']} on device {device.name}")

    def load(self):
        """Load devices and associated data from CloudVision."""
        if APP_SETTINGS.get("hostname_patterns") and not (
            APP_SETTINGS.get("site_mappings") and APP_SETTINGS.get("role_mappings")
        ):
            self.job.log_warning(
                message="Configuration found for hostname_patterns but no site_mappings or role_mappings. Please ensure your mappings are defined."
            )
        self.load_devices()
