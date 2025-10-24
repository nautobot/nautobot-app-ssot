"""Nautobot SSoT Citrix ADM Adapter for Citrix ADM SSoT plugin."""

import ipaddress
from decimal import Decimal
from typing import List, Optional

from diffsync import Adapter
from diffsync.exceptions import ObjectNotFound
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, Job
from nautobot.tenancy.models import Tenant
from netutils.ip import is_ip_within

from nautobot_ssot.integrations.citrix_adm.constants import DEVICETYPE_MAP
from nautobot_ssot.integrations.citrix_adm.diffsync.models.citrix_adm import (
    CitrixAdmAddress,
    CitrixAdmDatacenter,
    CitrixAdmDevice,
    CitrixAdmIPAddressOnInterface,
    CitrixAdmOSVersion,
    CitrixAdmPort,
    CitrixAdmSubnet,
)
from nautobot_ssot.integrations.citrix_adm.utils.citrix_adm import (
    CitrixNitroClient,
    parse_nsip6s,
    parse_nsips,
    parse_version,
    parse_vlan_bindings,
)
from nautobot_ssot.utils import parse_hostname_for_role


class CitrixAdmAdapter(Adapter):  # pylint: disable=too-many-instance-attributes
    """DiffSync adapter for Citrix ADM."""

    datacenter = CitrixAdmDatacenter
    osversion = CitrixAdmOSVersion
    device = CitrixAdmDevice
    address = CitrixAdmAddress
    prefix = CitrixAdmSubnet
    port = CitrixAdmPort
    ip_on_intf = CitrixAdmIPAddressOnInterface

    top_level = ["datacenter", "osversion", "device", "prefix", "address", "ip_on_intf"]

    def __init__(
        self,
        job: Job,
        instances: List[ExternalIntegration],
        sync=None,
        tenant: Optional[Tenant] = None,
    ):
        """Initialize Citrix ADM.

        Args:
            job (Job): Citrix ADM job.
            instances (List[ExternalIntegration]): ExternalIntegrations defining Citrix ADM instances.
            sync (object, optional): Citrix ADM DiffSync. Defaults to None.
            tenant (Tenant, optional): Name of Tenant to associate Devices and IP Addresses with.
        """
        super().__init__()
        self.job = job
        self.sync = sync
        self.instances = instances
        self.conn = None
        self.tenant = tenant
        self.adm_site_map = {}
        self.adm_device_map = {}

    def create_site_map(self):
        """Create mapping of ADM Datacenters to information about the Datacenter."""
        sites = self.conn.get_sites()
        for site in sites:
            self.adm_site_map[site["id"]] = site

    def load_site(self, site_info: dict):
        """Load sites from Citrix ADM into DiffSync models.

        Args:
            site_info (dict): Dictionary containing information about Datacenter to be imported.
        """
        if not site_info.get("name"):
            self.job.logger.error(f"Site is missing name so won't be loaded. {site_info}")
        else:
            site_name = site_info["name"]
            if self.job.location_map and site_name in self.job.location_map:
                parent_loc = self.job.location_map[site_name]["parent"]
                if "name" in self.job.location_map[site_name]:
                    site_name = self.job.location_map[site_name]["name"]
            elif self.job.parent_location:
                parent_loc = self.job.parent_location.name
            elif site_info.get("region"):
                parent_loc = site_info["region"]
                if (
                    self.job.location_map
                    and parent_loc in self.job.location_map
                    and "name" in self.job.location_map[parent_loc]
                ):
                    parent_loc = self.job.location_map[parent_loc]["name"]
            else:
                parent_loc = "Global"
            _, loaded = self.get_or_instantiate(
                self.datacenter,
                ids={"name": site_name, "region": parent_loc},
                attrs={
                    "latitude": float(round(Decimal(site_info["latitude"] if site_info["latitude"] else 0.0), 6)),
                    "longitude": float(round(Decimal(site_info["longitude"] if site_info["longitude"] else 0.0), 6)),
                    "uuid": None,
                },
            )
            if loaded and self.job.debug:
                self.job.logger.info(f"Loaded Datacenter from Citrix ADM: {site_name}")

    def load_devices(self):
        """Load devices from Citrix ADM into DiffSync models."""
        devices = self.conn.get_devices()
        for dev in devices:
            if not dev.get("hostname"):
                self.job.logger.warning(f"Device without hostname will not be loaded. {dev}")
                continue
            try:
                found_dev = self.get(self.device, dev["hostname"])
                if found_dev:
                    self.job.logger.warning(f"Duplicate Device attempting to be loaded: {dev['hostname']}")
            except ObjectNotFound:
                site = self.adm_site_map[dev["datacenter_id"]]
                self.load_site(site_info=site)
                site_name = site["name"]
                if (
                    self.job.location_map
                    and site_name in self.job.location_map
                    and "name" in self.job.location_map[site_name]
                ):
                    site_name = self.job.location_map[site_name]["name"]
                role = parse_hostname_for_role(
                    hostname_map=self.job.hostname_mapping,
                    device_hostname=dev["hostname"],
                    default_role="Load-Balancer",
                )
                version = parse_version(dev["version"])
                self.get_or_instantiate(self.osversion, ids={"version": version}, attrs={})
                new_dev = self.device(
                    name=dev["hostname"],
                    model=DEVICETYPE_MAP[dev["type"]] if dev["type"] in DEVICETYPE_MAP else dev["type"],
                    role=role,
                    serial=dev["serialnumber"],
                    site=site_name,
                    status="Active" if dev["instance_state"] == "Up" else "Offline",
                    tenant=self.tenant.name if self.tenant else None,
                    version=version,
                    uuid=None,
                    hanode=dev["ha_ip_address"],
                )
                self.add(new_dev)
                self.adm_device_map[dev["hostname"]] = dev

    def create_port_map(self):
        """Create a port/vlan/ip map for each ADC instance."""
        self.job.logger.info("Retrieving NSIP and port bindings from ADC instances.")
        for _, adc in self.adm_device_map.items():
            vlan_bindings = self.conn.get_vlan_bindings(adc)
            nsips = self.conn.get_nsip(adc)
            nsip6s = self.conn.get_nsip6(adc)

            ports = parse_vlan_bindings(vlan_bindings, adc, self.job)
            ports = parse_nsips(nsips, ports, adc)
            ports = parse_nsip6s(nsip6s, ports)

            self.adm_device_map[adc["hostname"]]["ports"] = ports

    def load_ports(self):
        """Load ports from Citrix ADM into DiffSync models."""
        for _, adc in self.adm_device_map.items():
            for port in adc["ports"]:
                try:
                    self.get(self.port, {"name": port["port"], "device": adc["hostname"]})
                except ObjectNotFound:
                    dev = self.get(self.device, adc["hostname"])
                    new_port = self.add_port(
                        dev_name=adc["hostname"],
                        port_name=port["port"],
                        port_status="ENABLED",
                        description="",
                    )
                    dev.add_child(new_port)

    def load_addresses(self):
        """Load addresses from Citrix ADC instances into Diffsync models."""
        for _, adc in self.adm_device_map.items():
            for port in adc["ports"]:
                if port.get("ipaddress"):
                    addr = f"{port['ipaddress']}/{port['netmask']}"
                    prefix = ipaddress.ip_interface(addr).network.with_prefixlen
                    self.load_prefix(prefix=prefix)
                    _tags = port["tags"] if port.get("tags") else []
                    if len(_tags) > 1:
                        _tags.sort()
                    _primary = bool("MGMT" in _tags or "MIP" in _tags)
                    self.load_address(
                        host_addr=port["ipaddress"],
                        mask_length=port["netmask"],
                        prefix=prefix,
                        tags=_tags,
                    )
                    self.load_address_to_interface(
                        host_addr=port["ipaddress"],
                        device=adc["hostname"],
                        port=port["port"],
                        primary=_primary,
                    )

    def add_port(
        self, dev_name: str, port_name: str = "Management", port_status: str = "ENABLED", description: str = ""
    ):
        """Method to add Port DiffSync model.

        Args:
            dev_name (str): Name of device port is attached to.
            port_name (str, optional): Name of port to create. Defaults to "Management".
            port_status (str, optional): Status of port to create. Defaults to "ENABLED".
            description (str, optional): Description for port. Defaults to "".

        Returns:
            CitrixAdmPort: DiffSync model for Port that was loaded.
        """
        new_port = self.port(
            name=port_name,
            device=dev_name,
            status="Active" if port_status == "ENABLED" else "Offline",
            description=description,
            uuid=None,
        )
        self.add(new_port)
        return new_port

    def load_prefix(self, prefix: str):
        """Load CitrixAdmSubnet DiffSync model with specified data.

        Args:
            prefix (str): Prefix to be loaded.
        """
        if self.tenant:
            namespace = self.tenant.name
        else:
            namespace = "Global"
        try:
            self.get(self.prefix, {"prefix": prefix, "namespace": namespace})
        except ObjectNotFound:
            new_pf = self.prefix(
                prefix=prefix,
                namespace=namespace,
                tenant=self.tenant.name if self.tenant else None,
                uuid=None,
            )
            self.add(new_pf)

    def load_address(self, host_addr: str, mask_length: int, prefix: str, tags: Optional[list] = None):
        """Load CitrixAdmAddress DiffSync model with specified data.

        Args:
            host_addr (str): IP Address to be loaded.
            mask_length (int): Mask length for IP Address.
            prefix (str): Prefix that IP Address resides in.
            tags (list): List of tags assigned to IP. Defaults to None.
        """
        self.get_or_instantiate(
            self.address,
            ids={"host_address": host_addr, "tenant": self.tenant.name if self.tenant else None},
            attrs={
                "mask_length": mask_length,
                "prefix": prefix,
                "tags": tags if tags else [],
            },
        )

    def load_address_to_interface(self, host_addr: str, device: str, port: str, primary: bool = False):
        """Load CitrixAdmIPAddressOnInterface DiffSync model with specified data.

        Args:
            host_addr (str): IP Address in mapping, e.g. "10.0.0.1".
            device (str): Device that IP resides on.
            port (str): Interface that IP is configured on.
            primary (str): Whether the IP is primary IP for assigned device. Defaults to False.
        """
        self.get_or_instantiate(
            self.ip_on_intf, ids={"host_address": host_addr, "device": device, "port": port}, attrs={"primary": primary}
        )

    def find_closer_parent_prefix(self) -> None:
        """Find more accurate parent Prefix for loaded IPAddresses."""
        for ipaddr in self.get_all(obj="address"):
            for prefix in self.get_all(obj="prefix"):
                # check if prefixes are both IPv4 or IPv6
                if (":" in ipaddr.prefix and ":" not in prefix.prefix) or (
                    ":" in prefix.prefix and ":" not in ipaddr.prefix
                ):
                    continue
                if not is_ip_within(ipaddr.prefix, prefix.prefix):
                    if is_ip_within(ipaddr.host_address, prefix.prefix):
                        if self.job.debug:
                            self.job.logger.debug(
                                "More specific Prefix %s found for IPAddress %s", prefix.prefix, ipaddr.host_address
                            )
                        ipaddr.prefix = prefix.prefix
                        self.update(ipaddr)

    def load(self):
        """Load data from Citrix ADM into DiffSync models."""
        for instance in self.instances:
            self.job.logger.info(f"Loading data from {instance.name}.")
            if instance.secrets_group is not None:
                _sg = instance.secrets_group
                instance_username = _sg.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
                )
                instance_password = _sg.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
                )
                self.conn = CitrixNitroClient(
                    base_url=instance.remote_url,
                    user=instance_username,
                    password=instance_password,
                    verify=instance.verify_ssl,
                    job=self.job,
                )
                self.conn.login()
                self.adm_site_map = {}
                self.adm_device_map = {}

                self.create_site_map()
                self.load_devices()
                self.create_port_map()
                self.load_ports()
                self.load_addresses()
                self.find_closer_parent_prefix()

                self.conn.logout()
            else:
                self.job.logger.warning(
                    f"Missing SecretsGroup definition for {instance.name}. This must be defined so we can authenticate instance."
                )
