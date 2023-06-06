"""Diffsync Adapter for Cisco ACI."""  # pylint: disable=too-many-lines, too-many-instance-attributes, too-many-arguments

import logging
import os
import re
from ipaddress import ip_network
from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound
from nautobot_ssot_aci.constant import PLUGIN_CFG
from nautobot_ssot_aci.diffsync.models import NautobotTenant
from nautobot_ssot_aci.diffsync.models import NautobotVrf
from nautobot_ssot_aci.diffsync.models import NautobotDeviceType
from nautobot_ssot_aci.diffsync.models import NautobotDeviceRole
from nautobot_ssot_aci.diffsync.models import NautobotDevice
from nautobot_ssot_aci.diffsync.models import NautobotInterfaceTemplate
from nautobot_ssot_aci.diffsync.models import NautobotInterface
from nautobot_ssot_aci.diffsync.models import NautobotIPAddress
from nautobot_ssot_aci.diffsync.models import NautobotPrefix
from nautobot_ssot_aci.diffsync.client import AciApi
from nautobot_ssot_aci.diffsync.utils import load_yamlfile


logger = logging.getLogger("rq.worker")


class AciAdapter(DiffSync):
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

    def __init__(self, *args, job=None, sync=None, client, **kwargs):
        """Initialize ACI.

        Args:
            job (object, optional): Aci job. Defaults to None.
            sync (object, optional): Aci DiffSync. Defaults to None.
            client (object): Aci credentials.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = AciApi(
            username=client["username"],
            password=client["password"],
            base_uri=client["base_uri"],
            verify=client["verify"],
            site=client["site"],
        )
        self.site = client.get("site")
        self.tenant_prefix = client.get("tenant_prefix")
        self.nodes = self.conn.get_nodes()
        self.controllers = self.conn.get_controllers()
        self.nodes.update(self.controllers)
        self.devices = self.nodes

    def load_tenants(self):
        """Load tenants from ACI."""
        tenant_list = self.conn.get_tenants()
        for _tenant in tenant_list:
            if not _tenant["name"] in PLUGIN_CFG.get("ignore_tenants"):
                tenant_name = f"{self.tenant_prefix}:{_tenant['name']}"
                new_tenant = self.tenant(
                    name=tenant_name,
                    description=_tenant["description"],
                    comments=PLUGIN_CFG.get("comments", ""),
                    site_tag=self.site,
                )
                self.add(new_tenant)

    def load_vrfs(self):
        """Load VRFs from ACI."""
        vrf_list = self.conn.get_vrfs(tenant="all")
        for _vrf in vrf_list:
            vrf_name = _vrf["name"]
            vrf_tenant = f"{self.tenant_prefix}:{_vrf['tenant']}"
            vrf_description = _vrf.get("description", "")
            new_vrf = self.vrf(name=vrf_name, tenant=vrf_tenant, description=vrf_description, site_tag=self.site)
            if _vrf["tenant"] not in PLUGIN_CFG.get("ignore_tenants"):
                self.add(new_vrf)

    def load_ipaddresses(self):
        """Load IPAddresses from ACI. Retrieves controller IPs, OOB Mgmt IP of leaf/spine, and Bridge Domain subnet IPs."""
        node_dict = self.conn.get_nodes()
        # Leaf/Spine management IP addresses
        for node in node_dict.values():
            if node["oob_ip"] and not node["oob_ip"] == "0.0.0.0":  # nosec
                new_ipaddress = self.ip_address(
                    address=f"{node['oob_ip']}/32",
                    device=node["name"],
                    status="Active",
                    description=f"ACI {node['role']}: {node['name']}",
                    interface="mgmt0",
                    tenant=None,
                    vrf=None,
                    vrf_tenant=None,
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
                    self.job.log_warning(
                        obj=new_ipaddress, message="Duplicate DiffSync IPAddress Object found and has not been loaded."
                    )

        controller_dict = self.conn.get_controllers()
        # Controller IP addresses
        for controller in controller_dict.values():
            if controller["oob_ip"] and not controller["oob_ip"] == "0.0.0.0":  # nosec
                new_ipaddress = self.ip_address(
                    address=f"{controller['oob_ip']}/32",
                    device=controller["name"],
                    status="Active",
                    description=f"ACI {controller['role']}: {controller['name']}",
                    interface="mgmt0",
                    tenant=None,
                    vrf=None,
                    vrf_tenant=None,
                    site=self.site,
                    site_tag=self.site,
                )
                self.add(new_ipaddress)
        # Bridge domain subnets
        bd_dict = self.conn.get_bds(tenant="all")
        for bd in bd_dict:
            if bd_dict[bd].get("subnets"):
                tenant_name = f"{self.tenant_prefix}:{bd_dict[bd].get('tenant')}"
                if bd_dict[bd]["vrf_tenant"]:
                    vrf_tenant = f"{self.tenant_prefix}:{bd_dict[bd]['vrf_tenant']}"
                else:
                    vrf_tenant = None
                for subnet in bd_dict[bd]["subnets"]:
                    new_ipaddress = self.ip_address(
                        address=subnet[0],
                        status="Active",
                        description=f"ACI Bridge Domain: {bd}",
                        tenant=tenant_name,
                        vrf=bd_dict[bd]["vrf"],
                        vrf_tenant=vrf_tenant,
                        site=self.site,
                        site_tag=self.site,
                    )
                    if not bd_dict[bd]["vrf"] or (not bd_dict[bd]["vrf"] and not vrf_tenant):
                        self.job.log_warning(
                            obj=new_ipaddress,
                            message=f"VRF configured on Bridge Domain {bd} in tenant {tenant_name} is invalid, skipping.",
                        )
                    else:
                        # Using Try/Except to check for an existing loaded object
                        # If the object doesn't exist we can create it
                        # Otherwise we log a message warning the user of the duplicate.
                        try:
                            self.get(obj=new_ipaddress, identifier=new_ipaddress.get_unique_id())
                        except ObjectNotFound:
                            self.add(new_ipaddress)
                        else:
                            self.job.log_warning(
                                obj=new_ipaddress,
                                message="Duplicate DiffSync IPAddress Object found and has not been loaded.",
                            )

    def load_prefixes(self):
        """Load Bridge domain subnets from ACI."""
        bd_dict = self.conn.get_bds(tenant="all")
        for bd in bd_dict:
            if bd_dict[bd].get("subnets"):
                tenant_name = f"{self.tenant_prefix}:{bd_dict[bd].get('tenant')}"
                if bd_dict[bd]["vrf_tenant"]:
                    vrf_tenant = f"{self.tenant_prefix}:{bd_dict[bd]['vrf_tenant']}"
                else:
                    vrf_tenant = None
                if tenant_name not in PLUGIN_CFG.get("ignore_tenants"):
                    for subnet in bd_dict[bd]["subnets"]:

                        new_prefix = self.prefix(
                            prefix=str(ip_network(subnet[0], strict=False)),
                            status="Active",
                            site=self.site,
                            description=f"ACI Bridge Domain: {bd}",
                            tenant=tenant_name,
                            vrf=bd_dict[bd]["vrf"],
                            vrf_tenant=vrf_tenant,
                            site_tag=self.site,
                        )
                        if not bd_dict[bd]["vrf"] or (bd_dict[bd]["vrf"] and not vrf_tenant):
                            self.job.log_warning(
                                obj=new_prefix,
                                message=f"VRF configured on Bridge Domain {bd} in tenant {tenant_name} is invalid, skipping.",
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
                                self.job.log_warning(
                                    obj=new_prefix,
                                    message="Duplicate DiffSync Prefix Object found and has not been loaded.",
                                )

    def load_devicetypes(self):
        """Load device types from YAML files."""
        devicetype_file_path = os.path.join(os.path.dirname(__file__), "..", "device-types")
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
        device_types = {self.devices[key]["model"] for key in self.devices}
        for _devicetype in device_types:
            if f"{_devicetype}.yaml" in os.listdir("nautobot_ssot_aci/diffsync/device-types"):
                device_specs = load_yamlfile(
                    os.path.join(os.getcwd(), "nautobot_ssot_aci", "diffsync", "device-types", f"{_devicetype}.yaml")
                )
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
                self.job.log_info(
                    message=f"No YAML descriptor file for device type {_devicetype}, skipping interface template creation."
                )

    def load_interfaces(self):
        """Load interfaces from ACI."""
        interfaces = self.conn.get_interfaces(
            nodes=self.devices,
        )

        for node in self.devices:
            # Load management and controller interfaces from YAML files

            fn = os.path.join(
                os.getcwd(), "nautobot_ssot_aci", "diffsync", "device-types", f"{self.devices[node]['model']}.yaml"
            )
            if os.path.exists(fn):
                device_specs = load_yamlfile(
                    os.path.join(
                        os.getcwd(),
                        "nautobot_ssot_aci",
                        "diffsync",
                        "device-types",
                        f"{self.devices[node]['model']}.yaml",
                    )
                )
                for _interface in interfaces[node]:
                    if_list = [
                        intf
                        for intf in device_specs["interfaces"]
                        if intf["name"] == _interface.replace("eth", "Ethernet")
                    ]
                    if if_list:
                        intf_type = if_list[0]["type"]
                    else:
                        intf_type = "other"
                    new_interface = self.interface(
                        name=_interface.replace("eth", "Ethernet"),
                        device=self.devices[node]["name"],
                        site=self.site,
                        description=interfaces[node][_interface]["descr"],
                        gbic_vendor=interfaces[node][_interface]["gbic_vendor"],
                        gbic_type=interfaces[node][_interface]["gbic_type"],
                        gbic_sn=interfaces[node][_interface]["gbic_sn"],
                        gbic_model=interfaces[node][_interface]["gbic_model"],
                        state=interfaces[node][_interface]["state"],
                        type=intf_type,
                        site_tag=self.site,
                    )
                    self.add(new_interface)
            else:
                logger.warning(
                    f"No YAML file exists in device-types for model {self.devices[node]['model']}, skipping interface creation"
                )

            for _interface in device_specs["interfaces"]:
                if_list = [intf for intf in device_specs["interfaces"] if intf["name"] == _interface]
                if if_list:
                    intf_type = if_list[0]["type"]
                else:
                    intf_type = "other"
                if re.match("^Eth[0-9]|^mgmt[0-9]", _interface["name"]):
                    new_interface = self.interface(
                        name=_interface["name"],
                        device=self.devices[node]["name"],
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

    def load_deviceroles(self):
        """Load device roles from ACI device data."""
        device_roles = {self.devices[key]["role"] for key in self.devices}
        for _devicerole in device_roles:
            new_devicerole = self.device_role(name=_devicerole, description=PLUGIN_CFG.get("comments", ""))
            self.add(new_devicerole)

    def load_devices(self):
        """Load devices from ACI device data."""
        for key in self.devices:
            if f"{self.devices[key]['model']}.yaml" in os.listdir("nautobot_ssot_aci/diffsync/device-types"):
                device_specs = load_yamlfile(
                    os.path.join(
                        os.getcwd(),
                        "nautobot_ssot_aci",
                        "diffsync",
                        "device-types",
                        f"{self.devices[key]['model']}.yaml",
                    )
                )
                model = device_specs["model"]
            else:
                model = self.devices[key]["model"]
            new_device = self.device(
                name=self.devices[key]["name"],
                device_type=model,
                device_role=self.devices[key]["role"],
                serial=self.devices[key]["serial"],
                comments=PLUGIN_CFG.get("comments", ""),
                node_id=int(key),
                pod_id=self.devices[key]["pod_id"],
                site=self.site,
                site_tag=self.site,
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
