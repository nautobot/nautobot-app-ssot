# pylint: disable=R0801
"""DiffSync adapter for Slurpit."""

import asyncio
import ipaddress
from datetime import datetime
from decimal import Decimal, InvalidOperation

from diffsync import Adapter
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.core.exceptions import ObjectDoesNotExist
from nautobot.dcim.models import LocationType
from nautobot.extras.models import Status
from netutils.mac import mac_to_format
from slurpit.models.site import Site as slurpit_site

from nautobot_ssot.integrations.slurpit import constants
from nautobot_ssot.integrations.slurpit.diffsync.models import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    InventoryItemModel,
    IPAddressModel,
    IPAddressToInterfaceModel,
    LocationModel,
    ManufacturerModel,
    PlatformModel,
    PrefixModel,
    RoleModel,
    VLANModel,
    VRFModel,
)

unknown_location = slurpit_site(
    id=100000,
    sitename="Unknown",
    description="Unknown",
    street="Unknown",
    county="Unknown",
    state="Unknown",
    number="000",
    zipcode="Unknown",
    city="Unknown",
    country="Unknown",
    phonenumber="Unknown",
    status=0,
    longitude="0",
    latitude="0",
)


# Helper function for latitude formatting
def format_latitude(latitude_str):
    """Format latitude string to Decimal with 6 decimal places."""
    try:
        latitude_decimal = Decimal(latitude_str).quantize(Decimal("0.000001"))
        while len(latitude_decimal.as_tuple().digits) > 8:
            latitude_decimal = latitude_decimal.quantize(Decimal("0.00001"))
        return latitude_decimal
    except (InvalidOperation, ValueError):
        return None


class SlurpitAdapter(Adapter):
    """DiffSync adapter for Slurpit."""

    # Model mappings
    location = LocationModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    platform = PlatformModel
    role = RoleModel
    device = DeviceModel
    interface = InterfaceModel
    inventory_item = InventoryItemModel
    vlan = VLANModel
    vrf = VRFModel
    prefix = PrefixModel
    ipaddress = IPAddressModel
    ipassignment = IPAddressToInterfaceModel
    top_level = (
        "location",
        "manufacturer",
        "device_type",
        "platform",
        "role",
        "device",
        "vlan",
        "vrf",
        "prefix",
        "ipaddress",
        "interface",
        "ipassignment",
    )

    def __init__(self, *args, api_client, job=None, **kwargs):
        """Initialize the Slurpit adapter."""
        super().__init__(*args, **kwargs)
        self.client = api_client
        self.job = job
        self.filtered_networks = []
        self.ipaddress_by_device = {}
        self.hostname_to_primary_ip = {}

    # Utility for running async coroutines synchronously
    def run_async(self, coroutine):
        """Run an async coroutine synchronously."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coroutine)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coroutine)

    def unique_vendors(self):
        """Get unique vendors from the devices."""
        devices = self.run_async(self.client.device.get_devices())
        vendors = {device.brand for device in devices}
        return [{"brand": item} for item in vendors]

    def unique_device_type(self):
        """Get unique device types from the devices."""
        devices = self.run_async(self.client.device.get_devices())
        device_types = {(device.brand, device.device_type, device.device_os) for device in devices}
        return [{"brand": item[0], "device_type": item[1], "device_os": item[2]} for item in device_types]

    def unique_platforms(self):
        """Get unique platforms from the devices."""
        devices = self.run_async(self.client.device.get_devices())
        return {device.device_os: device.brand for device in devices}

    def filter_networks(self):
        """Filter out networks based on ignore prefixes and normalize network/mask fields."""
        if self.job.ignore_prefixes:
            ignore_prefixes = [
                "0.0.0.0/0",
                "0.0.0.0/32",
                "::/0",
                "224.0.0.0/4",
                "255.255.255.255",
                "ff00::/8",
                "169.254.0.0/16",
                "fe80::/10",
                "127.0.0.0/8",
                "::1/128",
            ]
        else:
            ignore_prefixes = []

        def normalize_network(entry):
            network = entry.get("Network", "")
            mask = entry.get("Mask", "")
            if "/" in network:
                entry["normalized_prefix"] = network
            elif mask:
                entry["normalized_prefix"] = f"{network}/{mask}"
            else:
                entry["normalized_prefix"] = network
            return entry

        def should_ignore(network):
            try:
                net = ipaddress.ip_network(network, strict=False)
                # if net.prefixlen in {32, 128}:
                #     return True
                return any(net == ipaddress.ip_network(ignore, strict=False) for ignore in ignore_prefixes)
            except ValueError:
                return False

        network_list = self.planning_results("routing-table")
        self.filtered_networks = [
            normalize_network(entry)
            for entry in network_list
            if not should_ignore(normalize_network(entry)["normalized_prefix"])
        ]
        return self.filtered_networks

    async def filter_interfaces(self, interfaces):
        """Filter interfaces based on the filtered networks."""
        precomputed_filtered_networks = [
            {"network": ipaddress.ip_network(prefix["normalized_prefix"], strict=False), "Vrf": prefix.get("Vrf", None)}
            for prefix in self.filtered_networks
        ]

        async def normalize_and_find_prefix(entry):
            address = entry.get("IP", "")
            if address:
                if isinstance(address, list):
                    address = address[0]
                if "/" not in address:
                    address = f"{address}/32"
            else:
                return None

            try:
                network = ipaddress.ip_network(address, strict=False)
                entry["normalized_address"] = address
            except ValueError:
                return None

            for prefix in precomputed_filtered_networks:
                if network.subnet_of(prefix["network"]):
                    entry["prefix"] = str(prefix["network"])
                    entry["vrf"] = prefix["Vrf"]
                    break

            return entry

        # Concurrent execution of tasks
        tasks = [normalize_and_find_prefix(entry) for entry in interfaces if entry.get("IP")]

        # Run tasks concurrently
        filtered_interfaces = await asyncio.gather(*tasks)

        results = [entry for entry in filtered_interfaces if entry]

        # Filter out None values and return results
        return results

    def planning_results(self, planning_name):
        """Get planning results for a specific planning name."""
        plannings = self.run_async(self.client.planning.get_plannings())
        planning = next((plan.to_dict() for plan in plannings if plan.slug == planning_name), None)
        if not planning:
            raise IndexError(f"No planning found for name: {planning_name}")

        search_data = {"planning_id": planning["id"], "unique_results": True, "latest": True}
        results = self.run_async(self.client.planning.search_plannings(search_data, limit=30000))
        return results if results else []

    # Data loading functions
    def load_locations(self):
        """Load locations from Slurpit."""
        _loc_type = LocationType.objects.get(name="Site")
        _status = Status.objects.get(name="Active")
        sites = self.run_async(self.client.site.get_sites())
        sites.append(unknown_location)
        for site in sites:
            try:
                address = [site.number, site.street, site.city, site.state, site.country, site.county, site.zipcode]
                data = {
                    "name": site.sitename,
                    "description": site.description,
                    "latitude": format_latitude(site.latitude) if site.latitude else None,
                    "longitude": format_latitude(site.longitude) if site.longitude else None,
                    "contact_phone": site.phonenumber,
                    "physical_address": "\n".join(address),
                    "location_type__name": self.job.site_loctype.name,
                    "status__name": "Active",
                    "tags": [{"name": "SSoT Synced from Slurpit"}],
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }
                location = self.location(**data)
                self.add(location)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate location {location.name}. {err}")

    def load_vendors(self):
        """Load manufacturers from Slurpit."""
        vendors = self.unique_vendors()
        for vendor in vendors:
            try:
                manufacturer = self.manufacturer(
                    name=vendor["brand"],
                    system_of_record="Slurpit",
                    last_synced_from_sor=datetime.today().date().isoformat(),
                )
                self.add(manufacturer)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate manufacturer {manufacturer.name}. {err}")

    def load_device_types(self):
        """Load device types from Slurpit."""
        device_types = self.unique_device_type()
        for device_type in device_types:
            try:
                data = {
                    "model": device_type["device_type"],
                    "manufacturer__name": device_type["brand"],
                    "tags": [{"name": "SSoT Synced from Slurpit"}],
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }
                model = self.device_type(**data)
                self.add(model)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate device type {model.model}. {err}")

    def load_platforms(self):
        """Load platforms from Slurpit."""
        platforms = self.unique_platforms()
        for platform in platforms:
            try:
                platform_data = {
                    "name": platform,
                    "manufacturer__name": platforms[platform],
                    "network_driver": platform,
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }
                model = self.platform(**platform_data)
                self.add(model)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate platform {model.name}. {err}")

    def load_roles(self):
        """Load device roles."""
        try:
            role = self.role(
                name=constants.DEFAULT_DEVICE_ROLE,
                color=constants.DEFAULT_DEVICE_ROLE_COLOR,
                content_types=[{"app_label": "dcim", "model": "device"}],
                system_of_record="Slurpit",
                last_synced_from_sor=datetime.today().date().isoformat(),
            )
            self.add(role)
        except ObjectAlreadyExists as err:
            self.job.logger.warning(f"Duplicate role {role.name}. {err}")

    def load_devices(self):
        """Load devices from Slurpit."""
        devices = self.run_async(self.client.device.get_devices())
        for device in devices:
            try:
                data = {
                    "name": device.hostname,
                    "location__name": device.site or unknown_location.sitename,
                    "device_type__manufacturer__name": device.brand,
                    "device_type__model": device.device_type,
                    "platform__name": device.device_os,
                    "role__name": constants.DEFAULT_DEVICE_ROLE,
                    "status__name": "Active",
                    "location__location_type__name": self.job.site_loctype.name,
                    "tags": [{"name": "SSoT Synced from Slurpit"}],
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }
                if device.ipv4:
                    self.hostname_to_primary_ip[device.hostname] = device.ipv4
                self.add(self.device(**data))
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate device {device.name}. {err}")

    def load_interfaces(self):
        """Load interfaces from Slurpit."""
        interfaces = self.planning_results("interfaces")
        for interface in interfaces:  # pylint: disable=too-many-nested-blocks
            if interface.get("Interface", ""):
                try:
                    description = interface.get("Description", "")
                    mac = "" if isinstance(interface.get("MAC", ""), list) else interface.get("MAC", "")
                    enabled = "up" in interface.get("Line", "").lower()
                    data = {
                        "name": interface["Interface"],
                        "device__name": interface["hostname"],
                        "description": description,
                        "enabled": enabled,
                        "type": "1000base-t",
                        "status__name": "Active",
                        "mtu": 1500,
                        "mgmt_only": False,
                        "mac_address": mac_to_format(mac, "MAC_COLON_TWO").upper() if mac else "00:00:00:00:00:01",
                        "tags": [{"name": "SSoT Synced from Slurpit"}],
                        "system_of_record": "Slurpit",
                        "last_synced_from_sor": datetime.today().date().isoformat(),
                    }

                    ipaddress_info = self.ipaddress_by_device.get(
                        f"{interface.get('hostname')}__{interface.get('Interface')}"
                    )
                    if ipaddress_info:
                        for ip_address in ipaddress_info:
                            interface_match_data = {
                                "interface__name": data["name"],
                                "interface__device__name": interface.get("hostname"),
                                "ip_address__host": ip_address.get("host"),
                            }
                            if self.hostname_to_primary_ip.get(interface.get("hostname")) == ip_address.get("host"):
                                interface_match_data["interface__device__primary_ip4__host"] = ip_address.get("host")

                            self.add(self.ipassignment(**interface_match_data))

                    new_interface = self.interface(**data)
                    self.add(new_interface)
                    # dev.add_child(new_interface)
                except ObjectNotFound:
                    self.job.logger.warning(f"Device {interface['hostname']} not found")
                except ObjectAlreadyExists as err:
                    self.job.logger.warning(f"Duplicate interface {new_interface.name}. {err}")
                except ObjectDoesNotExist as err:
                    self.job.logger.warning(f"Unable to find IP for interface {ip_address.get('host')}. {err}")

    def load_inventory_items(self):
        """Load inventory items from Slurpit."""
        inventory_items = self.planning_results("hardware-info")
        for item in inventory_items:
            if item.get("Name", "") or item.get("Product", ""):
                try:
                    name = item.get("Name") if item.get("Name") else item.get("Product")
                    dev = self.get(self.device, {"name": item["hostname"]})
                    new_item = self.inventory_item(
                        name=name,
                        part_id=item.get("Product", ""),
                        serial=item.get("Serial", ""),
                        description=item.get("Descr", ""),
                        device__name=item.get("hostname"),
                        tags=[{"name": "SSoT Synced from Slurpit"}],
                        system_of_record="Slurpit",
                        last_synced_from_sor=datetime.today().date().isoformat(),
                    )
                    self.add(new_item)
                    dev.add_child(new_item)
                except ObjectNotFound:
                    self.job.logger.warning(f"Device {item['hostname']} not found")
                except ObjectAlreadyExists as err:
                    self.job.logger.warning(f"Unable to load {new_item.name} as it appears to be a duplicate. {err}")

    def load_vlans(self):
        """Load VLANs from Slurpit."""
        vlans = self.planning_results("vlans")
        for vlan in vlans:
            try:
                data = {
                    "vid": vlan.get("Vlan", ""),
                    "name": vlan.get("Name", ""),
                    "status__name": "Active",
                    "tags": [{"name": "SSoT Synced from Slurpit"}],
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }
                vlan = self.vlan(**data)
                self.add(vlan)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate VLAN {vlan.name}. {err}")

    def load_vrfs(self):
        """Load VRFs from Slurpit."""
        vrfs = {vrf["Vrf"] for vrf in self.planning_results("routing-table") if vrf.get("Vrf", "")}
        for vrf in vrfs:
            try:
                data = {
                    "name": vrf,
                    "namespace__name": self.job.namespace.name,
                    "tags": [{"name": "SSoT Synced from Slurpit"}],
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }
                new_vrf = self.vrf(**data)
                self.add(new_vrf)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate VRF {new_vrf.name}. {err}")

    def load_prefixes(self):
        """Load prefixes from Slurpit."""
        routes = self.filter_networks()
        for route in routes:
            try:
                data = {
                    "network": route.get("normalized_prefix", "").split("/")[0],
                    "prefix_length": route.get("normalized_prefix", "").split("/")[1],
                    "status__name": "Active",
                    "namespace__name": self.job.namespace.name,
                    "tags": [{"name": "SSoT Synced from Slurpit"}],
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }
                if vrf_name := route.get("Vrf"):
                    data["vrfs"] = [{"name": vrf_name}]
                prefix = self.prefix(**data)
                self.add(prefix)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate prefix {prefix.network}. {err}")

    def load_ip_addresses(self):
        """Load IP addresses from Slurpit."""
        interfaces = self.planning_results("interfaces")
        ip_addresses = self.run_async(self.filter_interfaces(interfaces))

        self.ipaddress_by_device = {}

        for ip_address in ip_addresses:
            try:
                mask_length = int(ip_address.get("prefix", "").split("/")[1]) if ip_address.get("prefix") else 32
                data = {
                    "host": ip_address.get("normalized_address", "").split("/")[0],
                    "mask_length": mask_length,
                    "status__name": "Active",
                    "assigned_object__app_label": "interface",
                    "assigned_object__device__name": ip_address.get("hostname", ""),
                    "assigned_object__name": ip_address.get("Interface", ""),
                    "assigned_object__model": "dcim",
                    "tags": [{"name": "SSoT Synced from Slurpit"}],
                    "system_of_record": "Slurpit",
                    "last_synced_from_sor": datetime.today().date().isoformat(),
                }

                if prefix := ip_address.get("prefix"):
                    network_data = prefix.split("/")[0]
                    mask_length_data = prefix.split("/")[1]
                else:
                    network_data = ip_address.get("normalized_address").split("/")[0]
                    mask_length_data = ip_address.get("normalized_address").split("/")[1]

                try:
                    cached_prefix = self.get(self.prefix, {"network": network_data, "prefix_length": mask_length_data})
                except ObjectNotFound:
                    cached_prefix = None

                if not cached_prefix:
                    prefix_data = {
                        "network": network_data,
                        "prefix_length": mask_length_data,
                        "namespace__name": self.job.namespace.name,
                        "status__name": "Active",
                        "tags": [{"name": "SSoT Synced from Slurpit"}],
                        "system_of_record": "Slurpit",
                        "last_synced_from_sor": datetime.today().date().isoformat(),
                    }
                    self.add(self.prefix(**prefix_data))
                new_ip = self.ipaddress(**data)
                self.add(new_ip)

                try:
                    self.ipaddress_by_device[f"{ip_address.get('hostname', '')}__{ip_address.get('Interface')}"].append(
                        data
                    )
                except KeyError:
                    self.ipaddress_by_device[f"{ip_address.get('hostname', '')}__{ip_address.get('Interface')}"] = [
                        data
                    ]
            except ObjectNotFound:
                self.job.logger.warning(f"Interface {ip_address.get('Interface')} not found")
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Duplicate IP address {new_ip.host}. {err}")

    # Unified load function
    def load(self):
        """Load all data models."""
        self.load_locations()
        self.load_vendors()
        self.load_device_types()
        self.load_platforms()
        self.load_roles()
        self.load_devices()
        self.load_inventory_items()
        self.load_vlans()
        self.load_vrfs()
        self.load_prefixes()
        self.load_ip_addresses()
        self.load_interfaces()
