"""DiffSync adapters for Forward Networks integration."""

from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound
from nautobot.dcim.models import (
    Manufacturer,
)
from nautobot.extras.models import Status, Tag

from nautobot_ssot.integrations.forward_networks.clients import ForwardNetworksClient
from nautobot_ssot.integrations.forward_networks.diffsync.models import (
    VLAN,
    Device,
    Interface,
    IPAddress,
    Location,
    Network,
    Prefix,
)


class ForwardNetworksAdapter(DiffSync):
    """DiffSync adapter for Forward Networks."""

    # DiffSync model mappings
    network = Network
    location = Location
    device = Device
    interface = Interface
    ip_address = IPAddress
    prefix = Prefix
    vlan = VLAN

    def __init__(self, job, sync, client: ForwardNetworksClient, network_id: str):
        """Initialize Forward Networks adapter."""
        super().__init__()
        self.job = job
        self.sync = sync
        self.client = client
        self.network_id = network_id

    def load(self):
        """Load data from Forward Networks API."""
        self.job.logger.info("Loading data from Forward Networks...")

        # Load networks first
        self.load_networks()

        # Load locations
        self.load_locations()

        # Load devices
        self.load_devices()

        # Load device interfaces
        self.load_interfaces()

        # Load IP addresses and prefixes
        self.load_ip_data()

        # Load VLANs if available
        self.load_vlans()

    def load_networks(self):
        """Load network information."""
        try:
            networks = self.client.networks.get_networks()
            for net_data in networks:
                if net_data.get("id") == self.network_id:
                    network = self.network(
                        name=net_data.get("name", f"Network-{net_data.get('id')}"),
                        network_id=net_data.get("id"),
                        description=net_data.get("description", ""),
                        status="Active",
                        tags=[],
                        custom_fields={},
                    )
                    self.add(network)
                    break
        except Exception as err:
            self.job.logger.warning(f"Failed to load networks: {err}")

    def load_locations(self):
        """Load location information."""
        try:
            locations = self.client.locations.get_locations(self.network_id)
            for loc_data in locations:
                location = self.location(
                    name=loc_data.get("name", f"Location-{loc_data.get('id')}"),
                    network=self.network_id,
                    location_id=loc_data.get("id"),
                    description=loc_data.get("description", ""),
                    location_type="Site",
                    latitude=loc_data.get("latitude"),
                    longitude=loc_data.get("longitude"),
                    tags=[],
                    custom_fields={},
                )
                self.add(location)

                # Associate with network
                try:
                    network = self.get(self.network, self.network_id)
                    network.add_child(location)
                except ObjectNotFound:
                    pass

        except Exception as err:
            self.job.logger.warning(f"Failed to load locations: {err}")

    def load_devices(self):
        """Load device information."""
        try:
            devices = self.client.devices.get_devices(self.network_id)
            
            for i, dev_data in enumerate(devices):
                try:
                    device = self.device(
                        name=dev_data.get("name", dev_data.get("hostname", f"Device-{dev_data.get('id')}")),
                        network=self.network_id,
                        device_id=dev_data.get("id"),
                        device_type=dev_data.get("deviceType", "Unknown"),
                        manufacturer=dev_data.get("vendor", "Unknown"),
                        model=dev_data.get("model", "Unknown"),
                        serial_number=dev_data.get("serialNumber"),
                        location=dev_data.get("location"),
                        primary_ip=dev_data.get("managementIp"),
                        platform=dev_data.get("platform"),
                        status="Active",
                        role=dev_data.get("role", "access"),
                        tags=[],
                        custom_fields={},
                    )
                    self.add(device)

                    # Associate with network
                    try:
                        # Try to find the network that was already loaded
                        network_found = False
                        for net in self.get_all(self.network):
                            if net.network_id == self.network_id:
                                net.add_child(device)
                                network_found = True
                                break
                        if not network_found:
                            self.job.logger.warning(f"Network {self.network_id} not found for device {device.name}")
                    except Exception as net_err:
                        self.job.logger.warning(f"Failed to associate network with device {device.name}: {net_err}")

                    if device.location:
                        try:
                            # Try to find the location that was already loaded
                            location_found = False
                            for loc in self.get_all(self.location):
                                if loc.name == device.location and loc.network == self.network_id:
                                    loc.add_child(device)
                                    location_found = True
                                    break
                            if not location_found:
                                self.job.logger.warning(f"Location {device.location} not found for device {device.name}")
                        except Exception as loc_err:
                            self.job.logger.warning(f"Failed to associate location {device.location} with device {device.name}: {loc_err}")
                            
                except Exception as device_err:
                    self.job.logger.error(f"Failed to create device {dev_data.get('name', dev_data.get('id'))}: {device_err}")
                    raise

        except Exception as err:
            self.job.logger.error(f"Failed to load devices: {err}")
            raise

    def load_interfaces(self):
        """Load interface information from devices."""
        # This would typically require additional API calls to get interface details
        # For now, we'll create a basic implementation
        try:
            for device_name in [d.name for d in self.get_all(self.device)]:
                try:
                    # Note: Forward Networks API might not have a direct interface endpoint
                    # This is a placeholder for when that data becomes available
                    device_detail = self.client.devices.get_device(self.network_id, device_name)
                    interfaces = device_detail.get("interfaces", [])

                    for intf_data in interfaces:
                        interface = self.interface(
                            name=intf_data.get("name", "Unknown"),
                            device=device_name,
                            network=self.network_id,
                            description=intf_data.get("description", ""),
                            interface_type=intf_data.get("type", "other"),
                            enabled=intf_data.get("enabled", True),
                            mtu=intf_data.get("mtu"),
                            speed=intf_data.get("speed"),
                            duplex=intf_data.get("duplex"),
                            mac_address=intf_data.get("macAddress"),
                            mode=intf_data.get("mode"),
                            vlan=intf_data.get("vlan"),
                            status="Active",
                            tags=[],
                            custom_fields={},
                        )
                        self.add(interface)

                        # Associate with device
                        try:
                            device = self.get(self.device, device_name, self.network_id)
                            device.add_child(interface)
                        except ObjectNotFound:
                            pass

                except Exception as device_err:
                    self.job.logger.debug(f"Could not load interfaces for device {device_name}: {device_err}")

        except Exception as err:
            self.job.logger.warning(f"Failed to load interfaces: {err}")

    def load_ip_data(self):
        """Load IP addresses and prefixes using NQE queries."""
        try:
            # Use NQE to get IP address information
            ip_query = {
                "query": """
                foreach device in network.devices
                foreach interface in device.interfaces
                foreach ip in interface.ipAddresses
                select {
                    device: device.name,
                    interface: interface.name,
                    address: ip.address,
                    prefix: ip.subnet,
                    version: ip.version
                }
                """,
                "snapshotId": "$last",
            }

            ip_results = self.client.nqe.run_query(ip_query)

            for result in ip_results.get("data", []):
                # Create IP Address
                ip_addr = self.ip_address(
                    address=result.get("address"),
                    network=self.network_id,
                    ip_version=result.get("version", 4),
                    description="",
                    status="Active",
                    device=result.get("device"),
                    interface=result.get("interface"),
                    prefix=result.get("prefix"),
                    tags=[],
                    custom_fields={},
                )
                self.add(ip_addr)

                # Associate with device and interface
                if result.get("device") and result.get("interface"):
                    try:
                        # Find the interface using get_all instead of get
                        interface_found = False
                        for intf in self.get_all(self.interface):
                            if (intf.name == result.get("interface") and 
                                intf.device == result.get("device") and 
                                intf.network == self.network_id):
                                intf.add_child(ip_addr)
                                interface_found = True
                                break
                        if not interface_found:
                            self.job.logger.debug(f"Interface {result.get('interface')} on device {result.get('device')} not found")
                    except Exception as intf_err:
                        self.job.logger.debug(f"Failed to associate interface: {intf_err}")

                # Create Prefix if not exists
                if result.get("prefix"):
                    try:
                        # Try to find existing prefix
                        prefix_found = False
                        for pf in self.get_all(self.prefix):
                            if pf.prefix == result.get("prefix") and pf.network == self.network_id:
                                pf.add_child(ip_addr)
                                prefix_found = True
                                break
                        
                        if not prefix_found:
                            prefix = self.prefix(
                                prefix=result.get("prefix"),
                                network=self.network_id,
                                description="",
                                prefix_type="network",
                                status="Active",
                                tags=[],
                                custom_fields={},
                            )
                            self.add(prefix)
                            prefix.add_child(ip_addr)
                    except Exception as prefix_err:
                        self.job.logger.debug(f"Failed to create/associate prefix: {prefix_err}")

        except Exception as err:
            self.job.logger.warning(f"Failed to load IP data: {err}")

    def load_vlans(self):
        """Load VLAN information using NQE queries."""
        try:
            # Use NQE to get VLAN information
            vlan_query = {
                "query": """
                foreach vlan in network.vlans
                select {
                    vid: vlan.id,
                    name: vlan.name,
                    description: vlan.description
                }
                """,
                "snapshotId": "$last",
            }

            vlan_results = self.client.nqe.run_query(vlan_query)

            for result in vlan_results.get("data", []):
                vlan = self.vlan(
                    vid=result.get("vid"),
                    network=self.network_id,
                    name=result.get("name"),
                    description=result.get("description", ""),
                    status="Active",
                    tags=[],
                    custom_fields={},
                )
                self.add(vlan)

        except Exception as err:
            self.job.logger.warning(f"Failed to load VLANs: {err}")


class NautobotAdapter(DiffSync):
    """DiffSync adapter for Nautobot."""

    # DiffSync model mappings
    network = Network
    location = Location
    device = Device
    interface = Interface
    ip_address = IPAddress
    prefix = Prefix
    vlan = VLAN

    def __init__(self, job, sync):
        """Initialize Nautobot adapter."""
        super().__init__()
        self.job = job
        self.sync = sync

        # Cache commonly used objects
        self._status_active = None
        self._tags_cache = {}
        self._manufacturer_cache = {}
        self._device_type_cache = {}
        self._platform_cache = {}
        self._location_type_cache = {}

    @property
    def status_active(self):
        """Get or create Active status."""
        if not self._status_active:
            self._status_active, _ = Status.objects.get_or_create(name="Active")
        return self._status_active

    def get_or_create_tag(self, tag_name: str) -> Tag:
        """Get or create a tag."""
        if tag_name not in self._tags_cache:
            self._tags_cache[tag_name], _ = Tag.objects.get_or_create(name=tag_name)
        return self._tags_cache[tag_name]

    def get_or_create_manufacturer(self, name: str) -> Manufacturer:
        """Get or create a manufacturer."""
        if name not in self._manufacturer_cache:
            self._manufacturer_cache[name], _ = Manufacturer.objects.get_or_create(name=name)
        return self._manufacturer_cache[name]

    def load(self):
        """Load data from Nautobot."""
        self.job.logger.info("Loading data from Nautobot...")

        # Note: For this implementation, we'll focus on creating a bi-directional sync
        # The Nautobot adapter would load existing data to compare against Forward Networks
        # For brevity, this is a simplified implementation
        pass
