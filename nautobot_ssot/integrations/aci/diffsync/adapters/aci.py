"""DiffSync Adapter for Cisco ACI."""  # pylint: disable=too-many-lines, too-many-instance-attributes, too-many-arguments

# pylint: disable=duplicate-code

import logging
import os
import re
from ipaddress import ip_network
from typing import Optional

from diffsync import Adapter
from diffsync.exceptions import ObjectNotFound

from nautobot_ssot.integrations.aci.constant import PLUGIN_CFG
from nautobot_ssot.integrations.aci.diffsync.models import (
    NautobotDevice,
    NautobotDeviceRole,
    NautobotDeviceType,
    NautobotInterface,
    NautobotInterfaceTemplate,
    NautobotIPAddress,
    NautobotPrefix,
    NautobotTenant,
    NautobotVrf,
)
from nautobot_ssot.integrations.aci.diffsync.utils import load_yamlfile

logger = logging.getLogger(__name__)


class AciAdapter(Adapter):
    """DiffSync adapter for Cisco ACI."""

    tenant = NautobotTenant
    vrf = NautobotVrf
    device_type = NautobotDeviceType
    device_role = NautobotDeviceRole
    device = NautobotDevice
    interface_template = NautobotInterfaceTemplate
    ip_address = NautobotIPAddress
    prefix = NautobotPrefix
    interface = NautobotInterface

    top_level = [
        "tenant",
        "vrf",
        "device_type",
        "device_role",
        "interface_template",
        "device",
        "interface",
        "prefix",
        "ip_address",
    ]

    def __init__(self, *args, job=None, sync=None, client, tenant_prefix, **kwargs):
        """Initialize ACI.

        Args:
            job (object, optional): Aci job. Defaults to None.
            sync (object, optional): Aci DiffSync. Defaults to None.
            client (object): Aci credentials.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = client
        self.site = client.site
        self.tenant_prefix = tenant_prefix
        self.nodes = self.conn.get_nodes()
        self.controllers = self.conn.get_controllers()
        self.nodes.update(self.controllers)
        self.devices = self.nodes

    def load_tenants(self):
        """Load tenants from ACI."""
        tenant_list = self.conn.get_tenants()
        for _tenant in tenant_list:
            if _tenant["name"] not in PLUGIN_CFG.get("ignore_tenants"):
                tenant_name = f"{self.tenant_prefix}:{_tenant['name']}"
                if ":mso" in _tenant.get("annotation").lower():  # pylint: disable=simplifiable-if-statement
                    _msite_tag = True
                else:
                    _msite_tag = False
                new_tenant = self.tenant(
                    name=tenant_name,
                    description=_tenant["description"],
                    comments=PLUGIN_CFG.get("comments", ""),
                    site_tag=self.site,
                    msite_tag=_msite_tag,
                )
                self.add(new_tenant)

    def load_vrfs(self):
        """Load VRFs from ACI."""
        vrf_list = self.conn.get_vrfs(tenant="all")
        for _vrf in vrf_list:
            vrf_name = _vrf["name"]
            vrf_tenant = f"{self.tenant_prefix}:{_vrf['tenant']}"
            vrf_description = _vrf.get("description", "")
            if vrf_name in ["inb", "oob"]:
                namespace = "Global"
            else:
                namespace = vrf_tenant
            new_vrf = self.vrf(
                name=vrf_name, namespace=namespace, tenant=vrf_tenant, description=vrf_description, site_tag=self.site
            )
            if _vrf["tenant"] not in PLUGIN_CFG.get("ignore_tenants"):
                self.add(new_vrf)

    def load_subnet_as_prefix(
        self, prefix: str, namespace: str, site: str, vrf: str, vrf_tenant: str, tenant: Optional[str] = None
    ):
        """Load Subnet into prefix DiffSync model."""
        try:
            self.get(self.prefix, {"prefix": prefix, "site": site, "vrf": vrf, "tenant": tenant})
        except ObjectNotFound:
            new_pf = self.prefix(
                prefix=prefix,
                namespace=namespace,
                status="Active",
                site=site,
                tenant=tenant,
                description="",
                vrf=vrf if vrf else None,
                vrf_tenant=vrf_tenant if vrf_tenant else None,
                site_tag=self.site,
            )
            self.add(new_pf)

    # pylint: disable-next=too-many-branches
    def load_ipaddresses(self):
        """Load IPAddresses from ACI. Retrieves controller IPs, OOB Mgmt IP of leaf/spine, and Bridge Domain subnet IPs."""
        node_dict = self.conn.get_nodes()
        # Leaf/Spine management IP addresses
        mgmt_tenant = f"{self.tenant_prefix}:mgmt"
        for node in node_dict.values():
            if node.get("oob_ip") and "mgmt" not in PLUGIN_CFG.get("ignore_tenants"):
                if node.get("subnet"):
                    subnet = node["subnet"]
                else:
                    subnet = ""
                if subnet:
                    self.load_subnet_as_prefix(
                        prefix=subnet,
                        namespace="Global",
                        site=self.site,
                        vrf="oob",
                        vrf_tenant=mgmt_tenant,
                        tenant=mgmt_tenant,
                    )
                new_ipaddress = self.ip_address(
                    address=node["oob_ip"],
                    prefix=subnet,
                    device=node["name"],
                    status="Active",
                    description=f"ACI {node['role']}: {node['name']}",
                    interface="mgmt0",
                    tenant=mgmt_tenant,
                    namespace="Global",
                    site=self.site,
                    site_tag=self.site,
                )
                # Using Try/Except to check for an existing loaded object
                # If the object doesn't exist we can create it
                # Otherwise we log a message warning the user of the duplicate.
                try:
                    self.get(obj=new_ipaddress, identifier=new_ipaddress.get_unique_id())
                except ObjectNotFound:
                    self.add(new_ipaddress)
                else:
                    self.job.logger.warning("Duplicate DiffSync IPAddress Object found and has not been loaded.")

        controller_dict = self.conn.get_controllers()
        # Controller IP addresses
        for controller in controller_dict.values():
            if controller.get("oob_ip") and "mgmt" not in PLUGIN_CFG.get("ignore_tenants"):
                if controller.get("subnet"):
                    subnet = controller["subnet"]
                else:
                    subnet = ""
                if subnet:
                    self.load_subnet_as_prefix(
                        prefix=subnet,
                        namespace="Global",
                        site=self.site,
                        vrf="oob",
                        vrf_tenant=mgmt_tenant,
                        tenant=mgmt_tenant,
                    )
                new_ipaddress = self.ip_address(
                    address=f"{controller['oob_ip']}",
                    prefix=subnet,
                    device=controller["name"],
                    status="Active",
                    description=f"ACI {controller['role']}: {controller['name']}",
                    interface="mgmt0",
                    tenant=mgmt_tenant,
                    namespace="Global",
                    site=self.site,
                    site_tag=self.site,
                )
                self.add(new_ipaddress)
        # Bridge domain subnets
        bd_dict = self.conn.get_bds(tenant="all")
        for bd_key, bd_value in bd_dict.items():
            if bd_value.get("subnets"):
                tenant_name = f"{self.tenant_prefix}:{bd_value.get('tenant')}"
                if bd_value.get("vrf_tenant"):
                    vrf_tenant = f"{self.tenant_prefix}:{bd_value['vrf_tenant']}"
                else:
                    vrf_tenant = None
                if bd_value.get("tenant") == "mgmt":
                    _namespace = "Global"
                else:
                    _namespace = vrf_tenant or tenant_name
                for subnet in bd_value["subnets"]:
                    if all(
                        tenant not in PLUGIN_CFG.get("ignore_tenants")
                        for tenant in [bd_value.get("tenant"), bd_value.get("vrf_tenant")]
                    ):
                        prefix = ip_network(subnet[0], strict=False).with_prefixlen
                        self.load_subnet_as_prefix(
                            prefix=prefix,
                            namespace=_namespace,
                            site=self.site,
                            vrf=bd_value["vrf"],
                            vrf_tenant=vrf_tenant,
                            tenant=vrf_tenant or tenant_name,
                        )
                        new_ipaddress = self.ip_address(
                            address=subnet[0],
                            prefix=prefix,
                            status="Active",
                            description=f"ACI Bridge Domain: {bd_key}",
                            device=None,
                            interface=None,
                            tenant=vrf_tenant or tenant_name,
                            namespace=_namespace,
                            site=self.site,
                            site_tag=self.site,
                        )
                        # Using Try/Except to check for an existing loaded object
                        # If the object doesn't exist we can create it
                        # Otherwise we log a message warning the user of the duplicate.
                        try:
                            self.get(obj=new_ipaddress, identifier=new_ipaddress.get_unique_id())
                        except ObjectNotFound:
                            self.add(new_ipaddress)
                        else:
                            self.job.logger.warning(
                                f"Duplicate DiffSync IPAddress Object found: {new_ipaddress.address} in Tenant {new_ipaddress.tenant} and has not been loaded.",
                            )

    def load_prefixes(self):
        """Load Bridge domain subnets from ACI."""
        bd_dict = self.conn.get_bds(tenant="all")
        # pylint: disable-next=too-many-nested-blocks
        for bd_key, bd_value in bd_dict.items():
            if bd_value.get("subnets"):
                tenant_name = f"{self.tenant_prefix}:{bd_value.get('tenant')}"
                if bd_value["vrf_tenant"]:
                    vrf_tenant = f"{self.tenant_prefix}:{bd_value['vrf_tenant']}"
                else:
                    vrf_tenant = None
                if bd_value.get("tenant") == "mgmt":
                    _namespace = "Global"
                else:
                    _namespace = vrf_tenant or tenant_name
                if bd_value.get("tenant") not in PLUGIN_CFG.get("ignore_tenants"):
                    for subnet in bd_value["subnets"]:
                        new_prefix = self.prefix(
                            prefix=str(ip_network(subnet[0], strict=False)),
                            namespace=_namespace,
                            status="Active",
                            site=self.site,
                            description=f"ACI Bridge Domain: {bd_key}",
                            tenant=vrf_tenant or tenant_name,
                            vrf=bd_value["vrf"] if bd_value.get("vrf") != "" else None,
                            vrf_tenant=vrf_tenant,
                            site_tag=self.site,
                        )
                        if not bd_value["vrf"] or (bd_value["vrf"] and not vrf_tenant):
                            self.job.logger.warning(
                                f"VRF configured on Bridge Domain {bd_key} in tenant {tenant_name} is invalid, skipping.",
                            )
                        else:
                            # Using Try/Except to check for an existing loaded object
                            # If the object doesn't exist we can create it
                            # Otherwise we log a message warning the user of the duplicate.
                            try:
                                self.get(obj=new_prefix, identifier=new_prefix.get_unique_id())
                            except ObjectNotFound:
                                self.add(new_prefix)
                            else:
                                self.job.logger.warning(
                                    f"Duplicate DiffSync Prefix Object found {new_prefix.prefix} in Namespace {new_prefix.namespace} and has not been loaded.",
                                )

    def load_devicetypes(self):
        """Load device types from YAML files."""
        devicetype_file_path = os.path.join(os.path.dirname(__file__), "..", "device-types")
        # pylint: disable-next=invalid-name
        for dt in os.listdir(devicetype_file_path):
            device_specs = load_yamlfile(os.path.join(devicetype_file_path, dt))
            _devicetype = self.device_type(
                model=device_specs["model"],
                manufacturer=PLUGIN_CFG.get("manufacturer_name"),
                part_nbr=device_specs["part_number"],
                comments=PLUGIN_CFG.get("comments", ""),
                u_height=device_specs["u_height"],
            )
            self.add(_devicetype)

    def load_interfacetemplates(self):
        """Load interface templates from YAML files."""
        devicetype_file_path = os.path.join(os.path.dirname(__file__), "..", "device-types")
        device_types = {value["model"] for value in self.devices.values()}
        for _devicetype in device_types:
            if f"{_devicetype}.yaml" in os.listdir(devicetype_file_path):
                device_specs = load_yamlfile(os.path.join(devicetype_file_path, f"{_devicetype}.yaml"))
                for intf in device_specs["interfaces"]:
                    new_interfacetemplate = self.interface_template(
                        name=intf["name"],
                        device_type=device_specs["model"],
                        type=intf["type"],
                        mgmt_only=intf.get("mgmt_only", False),
                        site_tag=self.site,
                    )
                    self.add(new_interfacetemplate)
            else:
                self.job.logger.info(
                    f"No YAML descriptor file for device type {_devicetype}, skipping interface template creation."
                )

    def load_interfaces(self):
        """Load interfaces from ACI."""
        devicetype_file_path = os.path.join(os.path.dirname(__file__), "..", "device-types")
        interfaces = self.conn.get_interfaces(
            nodes=self.devices,
        )

        for device_name, device in self.devices.items():
            # Load management and controller interfaces from YAML files

            # pylint: disable-next=invalid-name
            fn = os.path.join(devicetype_file_path, f"{device['model']}.yaml")
            if os.path.exists(fn):
                device_specs = load_yamlfile(fn)
                if device_specs and device_specs.get("interfaces"):
                    for interface_name, interface in interfaces[device_name].items():
                        if_list = [
                            intf
                            for intf in device_specs["interfaces"]
                            if intf["name"] == interface_name.replace("eth", "Ethernet")
                        ]
                        if if_list:
                            intf_type = if_list[0]["type"]
                        else:
                            intf_type = "other"
                        new_interface = self.interface(
                            name=interface_name.replace("eth", "Ethernet"),
                            device=device["name"],
                            site=self.site,
                            description=interface["descr"],
                            gbic_vendor=interface["gbic_vendor"],
                            gbic_type=interface["gbic_type"],
                            gbic_sn=interface["gbic_sn"],
                            gbic_model=interface["gbic_model"],
                            state=interface["state"],
                            type=intf_type,
                            site_tag=self.site,
                        )
                        self.add(new_interface)
                    for _interface in device_specs["interfaces"]:
                        if_list = [intf for intf in device_specs["interfaces"] if intf["name"] == _interface]
                        if if_list:
                            intf_type = if_list[0]["type"]
                        else:
                            intf_type = "other"
                        if re.match("^Eth[0-9]|^mgmt[0-9]", _interface["name"]):
                            new_interface = self.interface(
                                name=_interface["name"],
                                device=device["name"],
                                site=self.site,
                                description="",
                                gbic_vendor="",
                                gbic_type="",
                                gbic_sn="",
                                gbic_model="",
                                state="up",
                                type=intf_type,
                                site_tag=self.site,
                            )
                            self.add(new_interface)
            else:
                logger.warning(
                    "No YAML file exists in device-types for model %s, skipping interface creation",
                    device["model"],
                )

    def load_deviceroles(self):
        """Load device roles from ACI device data."""
        device_roles = {value["role"] for value in self.devices.values()}
        for _devicerole in device_roles:
            new_devicerole = self.device_role(name=_devicerole, description=PLUGIN_CFG.get("comments", ""))
            self.add(new_devicerole)

    def load_devices(self):
        """Load devices from ACI device data."""
        devicetype_file_path = os.path.join(os.path.dirname(__file__), "..", "device-types")
        for key, value in self.devices.items():
            model = ""
            if f"{value['model']}.yaml" in os.listdir(devicetype_file_path):
                device_specs = load_yamlfile(
                    os.path.join(
                        devicetype_file_path,
                        f"{value['model']}.yaml",
                    )
                )
                model = device_specs["model"]

            if not model:
                self.get_or_instantiate(
                    self.device_type,
                    ids={"model": value["model"], "part_nbr": ""},
                    attrs={"manufacturer": "Cisco", "u_height": 1, "comments": ""},
                )
                model = value["model"]

            new_device = self.device(
                name=value["name"],
                device_type=model,
                device_role=value["role"],
                serial=value["serial"],
                comments=PLUGIN_CFG.get("comments", ""),
                node_id=int(key),
                pod_id=value["pod_id"],
                site=self.site,
                site_tag=self.site,
                controller_group=(
                    self.job.apic.controller_managed_device_groups.first().name
                    if self.job.apic.controller_managed_device_groups.count() != 0
                    else ""
                ),
            )
            self.add(new_device)

    def load(self):
        """Method for one stop shop loading of all models."""
        self.load_tenants()
        self.load_vrfs()
        self.load_devicetypes()
        self.load_deviceroles()
        self.load_devices()
        self.load_interfaces()
        self.load_prefixes()
        self.load_ipaddresses()
