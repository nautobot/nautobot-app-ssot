"""Forward Enterprise adapter for nautobot-ssot plugin."""
# pylint: disable=R0801,too-many-instance-attributes,too-many-arguments,too-many-locals,too-many-branches,too-many-statements,too-many-return-statements

import ipaddress
from datetime import datetime
from typing import Optional

from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device, Interface, Location
from nautobot.extras.models import Tag
from nautobot.ipam.models import VLAN, VRF, IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.diffsync.models.models import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    IPAddressModel,
    IPAssignmentModel,
    LocationModel,
    ManufacturerModel,
    PlatformModel,
    PrefixModel,
    RoleModel,
    VLANModel,
    VRFModel,
)
from nautobot_ssot.integrations.forward_enterprise.exceptions import ForwardEnterpriseError
from nautobot_ssot.integrations.forward_enterprise.utils.diffsync import (
    create_placeholder_device,
    log_processing_error,
    log_processing_warning,
)
from nautobot_ssot.integrations.forward_enterprise.utils.forward_enterprise_client import ForwardEnterpriseClient
from nautobot_ssot.integrations.forward_enterprise.utils.location_helpers import normalize_location_name
from nautobot_ssot.integrations.forward_enterprise.utils.nautobot import (
    ensure_device_content_type_on_location_type,
    prefetch_nautobot_objects,
)
from nautobot_ssot.integrations.forward_enterprise.utils.vlan_extraction import (
    create_vlan_group_name,
    extract_vlans_by_location,
)


class ForwardEnterpriseAdapter(DiffSync):
    """DiffSync adapter for Forward Enterprise."""

    top_level = [
        "location",
        "manufacturer",
        "device_type",
        "platform",
        "role",
        "device",
        "interface",
        "vrf",
        "prefix",
        "ipaddress",
        "ipassignment",
        "vlan",
    ]

    location = LocationModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    platform = PlatformModel
    role = RoleModel
    device = DeviceModel
    interface = InterfaceModel
    prefix = PrefixModel
    ipaddress = IPAddressModel
    ipassignment = IPAssignmentModel
    vrf = VRFModel
    vlan = VLANModel

    def __init__(
        self,
        job,
        sync_interfaces=False,
        sync_ipam=False,
        namespace=None,
        **kwargs,
    ):
        """Initialize the Forward Enterprise adapter.

        Args:
            job: The Nautobot job instance
            sync_interfaces: Whether to sync interface data
            sync_ipam: Whether to sync IPAM data (VRFs, Prefixes, IPs)
            namespace: Nautobot Namespace object for IPAM objects (defaults to Global if None)
            **kwargs: Additional keyword arguments for parent class
        """
        self.job = job
        self.sync_interfaces = sync_interfaces
        self.sync_ipam = sync_ipam
        self.devices_data = []
        self.interfaces_data = []
        self.ipam_data = []
        self.loaded_vrfs = set()  # Track loaded VRFs to prevent duplicates

        # Handle namespace with default (adapter responsibility, not job responsibility)
        if namespace is None and sync_ipam:
            namespace = Namespace.objects.get(name="Global")
        self.namespace = namespace

        # Get verify_ssl from job's External Integration
        verify_ssl = job.credentials.verify_ssl if job and hasattr(job, "credentials") else True

        # Initialize the Forward Enterprise client with just the job
        self.client = ForwardEnterpriseClient(job=job, verify_ssl=verify_ssl)

        # Filter out old query parameters that are no longer supported
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ["query", "query_id", "namespace"]}
        super().__init__(**filtered_kwargs)

    def load_tags(self):
        """Load and create tags from Forward Enterprise data."""
        # pylint: disable=too-many-return-statements
        tags_to_create = set()

        # Always ensure the SSoT sync tag exists
        tags_to_create.add(f"SSoT Synced from {constants.SYSTEM_OF_RECORD}")

        # Collect all unique tags from devices
        for device in self.devices_data:
            device_tags = device.get("tags", [])
            if isinstance(device_tags, list):
                for tag in device_tags:
                    if isinstance(tag, str) and tag.strip():
                        tags_to_create.add(tag.strip())
                    elif isinstance(tag, dict) and "name" in tag:
                        tags_to_create.add(tag["name"].strip())

        # Create tags in Nautobot if they don't exist
        if self.job:
            self.job.logger.info("Identified %s unique tags from Forward Enterprise", len(tags_to_create))

        for tag_name in sorted(tags_to_create):
            # Create tag if it doesn't exist
            tag, created = Tag.objects.get_or_create(
                name=tag_name,
                defaults={
                    "description": f"Tag synced from {constants.SYSTEM_OF_RECORD}: {tag_name}",
                    "color": constants.DEFAULT_DEVICE_ROLE_COLOR,
                },
            )

            if created and self.job:
                self.job.logger.info("Created new tag: %s", tag_name)

            # Assign content types to the tag so it can be used with various models
            for model in [Device, Interface, IPAddress, Prefix, VLAN, VRF, Location]:
                tag.content_types.add(ContentType.objects.get_for_model(model))

    def load_locations(self):
        """Load locations from Forward Enterprise data."""
        # Ensure the location type allows devices to be assigned to it
        # This prevents "Devices may not associate to locations of type X" errors
        ensure_device_content_type_on_location_type(constants.DEFAULT_LOCATION_TYPE)

        locations = set()
        for device in self.devices_data:
            raw_name = device.get("location")
            location_name = normalize_location_name(raw_name)
            if location_name not in locations:
                try:
                    data = {
                        "name": location_name,
                        "location_type__name": constants.DEFAULT_LOCATION_TYPE,
                        "description": f"Location imported from {constants.SYSTEM_OF_RECORD}",
                        "status__name": "Active",
                        "tags": [{"name": f"SSoT Synced from {constants.SYSTEM_OF_RECORD}"}],
                        "system_of_record": constants.SYSTEM_OF_RECORD,
                        "last_synced_from_sor": datetime.today().date().isoformat(),
                    }
                    location = self.location(**data)
                    self.add(location)
                    locations.add(location_name)
                except ObjectAlreadyExists as err:
                    if self.job:
                        self.job.logger.warning("Duplicate location %s. %s", location_name, err)

    def load_manufacturers(self):
        """Load manufacturers from Forward Enterprise data."""
        manufacturers = set()
        for device in self.devices_data:
            manufacturer_name = str(device.get("manufacturer", "Unknown"))
            if manufacturer_name and manufacturer_name not in manufacturers:
                try:
                    manufacturer = self.manufacturer(
                        name=manufacturer_name,
                        system_of_record=constants.SYSTEM_OF_RECORD,
                        last_synced_from_sor=datetime.today().date().isoformat(),
                    )
                    self.add(manufacturer)
                    manufacturers.add(manufacturer_name)
                except ObjectAlreadyExists as err:
                    if self.job:
                        self.job.logger.warning("Duplicate manufacturer %s. %s", manufacturer_name, err)

    def load_device_types(self):
        """Load device types from Forward Enterprise data."""
        device_types = set()
        for device in self.devices_data:
            manufacturer_name = str(device.get("manufacturer") or "").strip()
            device_type_name = str(device.get("device_type") or "").strip()
            device_type_key = (manufacturer_name, device_type_name)

            # Skip if manufacturer or model is missing
            if not manufacturer_name or not device_type_name:
                if self.job:
                    self.job.logger.warning(
                        f"Skipping device type: manufacturer='{manufacturer_name}', model='{device_type_name}' for device '{device.get('name', 'Unknown')}'"
                    )
                continue

            if device_type_key not in device_types:
                try:
                    data = {
                        "model": device_type_name,
                        "manufacturer__name": manufacturer_name,
                        "tags": [{"name": f"SSoT Synced from {constants.SYSTEM_OF_RECORD}"}],
                        "system_of_record": constants.SYSTEM_OF_RECORD,
                        "last_synced_from_sor": datetime.today().date().isoformat(),
                    }
                    model = self.device_type(**data)
                    self.add(model)
                    device_types.add(device_type_key)
                except ObjectAlreadyExists as err:
                    if self.job:
                        self.job.logger.warning("Duplicate device type %s. %s", device_type_name, err)

    def load_platforms(self):
        """Load platforms from Forward Enterprise data."""
        platforms = set()
        for device in self.devices_data:
            manufacturer_name = str(device.get("manufacturer") or "").strip()
            device_type_name = str(device.get("device_type") or "").strip()
            platform_key = (manufacturer_name, device_type_name)

            # Skip if manufacturer or device_type is missing
            if not manufacturer_name or not device_type_name:
                if self.job:
                    self.job.logger.warning(
                        f"Skipping platform: manufacturer='{manufacturer_name}', device_type='{device_type_name}' for device '{device.get('name', 'Unknown')}'"
                    )
                continue

            if platform_key not in platforms:
                try:
                    platform_data = {
                        "name": device_type_name,
                        "manufacturer__name": manufacturer_name,
                        "network_driver": device_type_name.lower(),
                        "system_of_record": constants.SYSTEM_OF_RECORD,
                        "last_synced_from_sor": datetime.today().date().isoformat(),
                    }
                    model = self.platform(**platform_data)
                    self.add(model)
                    platforms.add(platform_key)
                except ObjectAlreadyExists as err:
                    if self.job:
                        self.job.logger.warning("Duplicate platform %s. %s", device_type_name, err)

    def load_roles(self):
        """Load device roles."""
        try:
            role = self.role(
                name=constants.DEFAULT_DEVICE_ROLE,
                color=constants.DEFAULT_DEVICE_ROLE_COLOR,
                content_types=[{"app_label": "dcim", "model": "device"}],
                system_of_record=constants.SYSTEM_OF_RECORD,
                last_synced_from_sor=datetime.today().date().isoformat(),
            )
            self.add(role)
        except ObjectAlreadyExists as err:
            if self.job:
                self.job.logger.warning("Duplicate role %s. %s", constants.DEFAULT_DEVICE_ROLE, err)

    def load_devices(self):
        """Load devices from Forward Enterprise data."""
        if self.job:
            self.job.logger.info("Loading devices from Forward Enterprise data.")

        for device in self.devices_data:
            self.process_device(device)

    def process_device(self, device_data):
        """Process a single device and handle any errors."""
        device_name = device_data.get("name", "Unknown")

        try:
            # Create device model with validation
            device_model = self._create_device_model(device_data)
            self.add(device_model)
        except ForwardEnterpriseError as exception:
            log_processing_warning(self.job.logger if self.job else None, "device", device_name, str(exception))
            # Continue processing with placeholder if needed
            placeholder = create_placeholder_device(device_name)
            self.add(placeholder)
        except (ValueError, KeyError, AttributeError, TypeError) as exception:
            log_processing_error(self.job.logger if self.job else None, "device", device_name, exception)
            # Add placeholder device to prevent sync failures
            placeholder = create_placeholder_device(device_name)
            self.add(placeholder)

    def _create_device_model(self, device):
        """Create a DeviceModel from Forward Enterprise device data."""
        manufacturer_name = str(device.get("manufacturer") or "").strip()
        device_type_name = str(device.get("device_type") or "").strip()

        # Note: We allow empty manufacturer/model here because the field validators
        # in DeviceModel will handle them by setting defaults to "Unknown"

        # Process device tags from Forward Enterprise
        device_tags = [{"name": f"SSoT Synced from {constants.SYSTEM_OF_RECORD}"}]
        forward_tags = device.get("tags", [])
        if isinstance(forward_tags, list):
            for tag in forward_tags:
                if isinstance(tag, str) and tag.strip():
                    device_tags.append({"name": tag.strip()})
                elif isinstance(tag, dict) and "name" in tag:
                    device_tags.append({"name": tag["name"].strip()})

        # Handle serial field - can be string or list depending on query format
        serial_raw = device.get("serial", "")
        if isinstance(serial_raw, list):
            serial_number = ""
            for serial in serial_raw:
                if serial and str(serial).strip() and str(serial).strip().lower() not in ["unknown", "null", "none"]:
                    serial_number = str(serial).strip()
                    break
        else:
            # Handle string format (old query format)
            serial_number = str(serial_raw).strip() if serial_raw else ""
            if serial_number.lower() in ["unknown", "null", "none"]:
                serial_number = ""

        data = {
            "name": device.get("name", "Unknown"),
            "location__name": normalize_location_name(device.get("location")),
            "location__location_type__name": "Site",
            "device_type__manufacturer__name": manufacturer_name,
            "device_type__model": device_type_name,
            "platform__name": device.get("platform"),
            "role__name": constants.DEFAULT_DEVICE_ROLE,
            "status__name": "Active",
            "serial": serial_number,
            "tags": device_tags,
            "system_of_record": constants.SYSTEM_OF_RECORD,
            "last_synced_from_sor": datetime.now().strftime("%Y-%m-%d"),
        }

        return DeviceModel(**data)

    def load_interfaces(self):
        """Load interfaces from separate interface query results."""
        if self.job:
            self.job.logger.info("Loading interfaces from separate query")

        # Group interfaces by device name
        interfaces_by_device = {}
        for interface_data in self.interfaces_data:
            device_name = interface_data.get("device")
            if device_name:
                interfaces_by_device.setdefault(device_name, []).append(interface_data)

        # Process each interface
        for device_name, interfaces in interfaces_by_device.items():
            # Find the corresponding device using just the device name as identifier
            try:
                self.get("device", device_name)
            except (KeyError, ObjectNotFound):
                # Device not found, skip
                continue

            for interface_data in interfaces:
                interface_name = interface_data.get("name")
                if not interface_name:
                    continue

                try:
                    # Map speed to proper interface type
                    speed = interface_data.get("type", 1000)
                    try:
                        speed_int = int(speed)
                        if speed_int >= 10000:
                            interface_type = "10gbase-t"
                        elif speed_int >= 1000:
                            interface_type = "1000base-t"
                        elif speed_int >= 100:
                            interface_type = "100base-tx"
                        else:
                            interface_type = "10base-t"
                    except (ValueError, TypeError):
                        interface_type = "1000base-t"  # Default fallback

                    interface = InterfaceModel(
                        name=interface_name,
                        device__name=device_name,
                        type=interface_type,  # Use mapped type instead of raw speed
                        enabled=interface_data.get("enabled") == "1",
                        mtu=interface_data.get("mtu", 1500),
                        mac_address=interface_data.get("mac_address", ""),
                        mgmt_only=False,  # Required field
                        status__name="Active",  # Required field
                        description=interface_data.get("comments", ""),
                        tags=[{"name": f"SSoT Synced from {constants.SYSTEM_OF_RECORD}"}],
                        system_of_record=constants.SYSTEM_OF_RECORD,
                        last_synced_from_sor=datetime.today().date().isoformat(),
                    )

                    self.add(interface)

                    # Add interface as child of device
                    try:
                        device = self.get("device", device_name)
                        device.add_child(interface)
                    except (AttributeError, ObjectNotFound) as exception:
                        if self.job:
                            self.job.logger.warning(
                                "Could not add interface %s as child of device %s: %s",
                                interface_name,
                                device_name,
                                exception,
                            )
                except (ValueError, TypeError) as exception:
                    if self.job:
                        self.job.logger.warning(
                            f"Failed to create interface {interface_name} for device {device_name}: {exception}"
                        )

    # -----------------
    # IPAM helpers
    # -----------------
    def load_vrf(self, vrf_name: str, namespace: str = "Global"):
        """Ensure a VRF DiffSync object exists for the given VRF name."""
        # Create unique identifier for VRF
        vrf_id = f"{vrf_name}__{namespace}"

        # Check if we've already processed this VRF
        if vrf_id in self.loaded_vrfs:
            return

        try:
            self.get("vrf", {"name": vrf_name, "namespace__name": namespace})
        except (KeyError, ObjectNotFound):
            # Create VRF object
            new_vrf = self.vrf(
                name=vrf_name,
                namespace__name=namespace,
                description=f"VRF imported from {constants.SYSTEM_OF_RECORD}: {vrf_name}",
                rd=f"FE:{vrf_name}",  # Use unique RD to avoid constraint violations
                tenant__name=None,
                uuid=None,
                system_of_record=constants.SYSTEM_OF_RECORD,
            )
            try:
                self.add(new_vrf)
                # Don't log here - this is just loading into DiffSync, not creating in Nautobot
                # Actual creation logging happens during sync phase
            except ObjectAlreadyExists:
                # VRF already exists in DiffSync - debug log for troubleshooting
                if self.job:
                    self.job.logger.debug("VRF %s already exists in DiffSync", vrf_name)

        # Mark this VRF as processed
        self.loaded_vrfs.add(vrf_id)

    def load_prefix(self, prefix: str, vrf_name: Optional[str] = None):
        """Ensure a Prefix DiffSync object exists for the given prefix (with namespace Global)."""
        # Split CIDR notation into network and prefix_length
        network_parts = prefix.strip().split("/")
        if len(network_parts) != 2:
            if self.job:
                self.job.logger.error("Invalid prefix format: %s. Expected format: network/prefix_length", prefix)
            return

        network_address = network_parts[0].strip()
        prefix_length = int(network_parts[1].strip())

        namespace = getattr(self, "namespace", None)
        ns_name = namespace.name if namespace else "Global"

        # Use get to check existence
        try:
            self.get("prefix", {"network": network_address, "prefix_length": prefix_length, "namespace__name": ns_name})
        except (KeyError, ObjectNotFound):
            # Create prefix object
            prefix_description = f"Prefix imported from {constants.SYSTEM_OF_RECORD}: {prefix}"
            if vrf_name:
                prefix_description += f" (VRF: {vrf_name})"

            # Only assign VRF if one is provided (not None or empty)
            # Format VRF reference as VRFDict for proper DiffSync handling
            vrf_list = [{"name": vrf_name, "namespace__name": ns_name}] if vrf_name and vrf_name.strip() else []

            new_prefix = self.prefix(
                network=network_address,
                prefix_length=prefix_length,
                namespace__name=ns_name,
                description=prefix_description,
                status__name="Active",
                vrfs=vrf_list,  # Assign VRF list to prefix
                uuid=None,
                system_of_record=constants.SYSTEM_OF_RECORD,
            )
            try:
                self.add(new_prefix)
                # Don't log here - this is just loading into DiffSync, not creating in Nautobot
                # Actual creation logging happens during sync phase
            except ObjectAlreadyExists:
                # Prefix already exists in DiffSync - debug log for troubleshooting
                if self.job:
                    self.job.logger.debug("Prefix %s already exists in DiffSync", prefix)

    def load_ipaddress(self, host_addr: str, mask_length: int, parent_network: str, parent_prefix_length: int):
        """Create an IPAddress object if it doesn't exist."""
        try:
            # Check by host and mask_length
            self.get("ipaddress", {"host": host_addr, "mask_length": mask_length})
        except (KeyError, ObjectNotFound):
            new_ip = self.ipaddress(
                host=host_addr,
                mask_length=mask_length,
                status__name="Active",
                parent__network=parent_network,
                parent__prefix_length=parent_prefix_length,
                system_of_record=constants.SYSTEM_OF_RECORD,
            )
            try:
                self.add(new_ip)
            except ObjectAlreadyExists:
                # IP address already exists in DiffSync - debug log for troubleshooting
                if self.job:
                    self.job.logger.debug("IP address %s/%s already exists in DiffSync", host_addr, mask_length)

    def load_ipassignment(self, host_address: str, dev_name: str, iface_name: str):
        """Assign an IP address to an interface (IPAddressToInterface)."""
        # First ensure the interface exists
        self._ensure_interface_exists(dev_name, iface_name)

        try:
            # Look for existing mapping
            self.get(
                "ipassignment",
                {"interface__device__name": dev_name, "interface__name": iface_name, "ip_address__host": host_address},
            )
        except (KeyError, ObjectNotFound):
            new_map = self.ipassignment(
                interface__device__name=dev_name,
                interface__name=iface_name,
                ip_address__host=host_address,
                uuid=None,
            )
            try:
                self.add(new_map)
            except ObjectAlreadyExists:
                # IP assignment already exists in DiffSync - debug log for troubleshooting
                if self.job:
                    self.job.logger.debug(
                        "IP assignment %s to %s:%s already exists in DiffSync", host_address, dev_name, iface_name
                    )

    def _ensure_interface_exists(self, device_name: str, interface_name: str):
        """Ensure an interface exists, creating it if necessary."""
        try:
            # Check if interface already exists
            self.get("interface", {"name": interface_name, "device__name": device_name})
            return
        except (KeyError, ObjectNotFound):
            # Interface doesn't exist, create it
            interface_type = self._determine_interface_type(interface_name)

            interface = InterfaceModel(
                name=interface_name,
                device__name=device_name,
                type=interface_type,
                enabled=True,
                mtu=1500,
                mac_address="",
                mgmt_only=interface_name.lower() in ["mgmt", "management", "ma1"],
                status__name="Active",
                description="Interface created from IPAM data",
                tags=[{"name": f"SSoT Synced from {constants.SYSTEM_OF_RECORD}"}],
                system_of_record=constants.SYSTEM_OF_RECORD,
                last_synced_from_sor=datetime.today().date().isoformat(),
            )

            try:
                self.add(interface)

                # Add interface as child of device
                try:
                    device = self.get("device", device_name)
                    device.add_child(interface)
                except (AttributeError, ObjectNotFound) as exception:
                    if self.job:
                        self.job.logger.warning(
                            "Could not add interface %s as child of device %s: %s",
                            interface_name,
                            device_name,
                            exception,
                        )

            except ObjectAlreadyExists:
                if self.job:
                    self.job.logger.debug("Interface %s already exists", interface_name)

    def _determine_interface_type(self, interface_name: str) -> str:
        """Determine interface type based on interface name patterns.

        Uses heuristics to map interface names to Nautobot interface types
        based on patterns defined in constants.INTERFACE_TYPE_MAP.

        Args:
            interface_name: The interface name from Forward Enterprise

        Returns:
            str: Nautobot interface type identifier
        """
        iface_lower = interface_name.lower()

        # Check for specific patterns using constants mapping
        if iface_lower.startswith("lo") or "loopback" in iface_lower:
            return constants.INTERFACE_TYPE_MAP.get("loopback", "virtual")

        if iface_lower in ["mgmt", "management"] or iface_lower.startswith("ma"):
            return constants.INTERFACE_TYPE_MAP.get("management", "1000base-t")

        if "/common/vlan" in iface_lower or "vlan" in iface_lower:
            return constants.INTERFACE_TYPE_MAP.get("vlan", "virtual")

        if iface_lower.startswith("vmk"):
            return "virtual"

        # Check for specific ethernet interface types (order matters - check more specific patterns first)
        if "hundredgigabitethernet" in iface_lower:
            return constants.INTERFACE_TYPE_MAP.get("hundredgigabitethernet", "100gbase-x-qsfp28")

        if "fortygigabitethernet" in iface_lower:
            return constants.INTERFACE_TYPE_MAP.get("fortygigabitethernet", "40gbase-x-qsfpp")

        if "tengigabitethernet" in iface_lower or "tengige" in iface_lower:
            return constants.INTERFACE_TYPE_MAP.get("tengigabitethernet", "10gbase-x-sfpp")

        if "fastethernet" in iface_lower or iface_lower.startswith("fa"):
            return constants.INTERFACE_TYPE_MAP.get("fastethernet", "100base-tx")

        if "gigabitethernet" in iface_lower or "gige" in iface_lower or iface_lower.startswith("gi"):
            return constants.INTERFACE_TYPE_MAP.get("gigabitethernet", "1000base-t")

        # Default to 1000base-t for physical interfaces
        return constants.INTERFACE_TYPE_MAP.get("ethernet", "1000base-t")

    def load(self):
        """Load all data models."""
        if self.job:
            self.job.logger.info("Executing device query to fetch data from Forward Enterprise")

        # Prefetch Nautobot objects to populate caches
        if self.job:
            self.job.logger.info("Prefetching Nautobot objects...")
        prefetch_nautobot_objects()

        # Get device query from extra_config or fall back to instance query/query_id
        device_query = self.client.get_device_query_from_config()
        device_query_id = self.client.get_device_query_id_from_config()

        # Always load device data first
        self.devices_data = self.client.execute_nqe_query(query=device_query, query_id=device_query_id)

        if not self.devices_data:
            if self.job:
                self.job.logger.warning("No data received from Forward Enterprise")
            return

        if self.job:
            self.job.logger.info("Received %s devices from Forward Enterprise", len(self.devices_data))

        # Load interface data if enabled
        if self.sync_interfaces:
            if self.job:
                self.job.logger.info("Executing interface query from Forward Enterprise")
            interface_query = self.client.get_interface_query_from_config()
            interface_query_id = self.client.get_interface_query_id_from_config()

            if interface_query or interface_query_id:
                self.interfaces_data = self.client.execute_nqe_query(query=interface_query, query_id=interface_query_id)
                if self.job:
                    self.job.logger.info("Received %s interfaces from Forward Enterprise", len(self.interfaces_data))
            else:
                if self.job:
                    self.job.logger.warning(
                        "Interface sync enabled but no interface_query or interface_query_id found in extra_config"
                    )

        # Load IPAM data if enabled
        if self.sync_ipam:
            if self.job:
                self.job.logger.info("Executing IPAM query from Forward Enterprise")
            ipam_query = self.client.get_ipam_query_from_config()
            ipam_query_id = self.client.get_ipam_query_id_from_config()

            if ipam_query or ipam_query_id:
                self.ipam_data = self.client.execute_nqe_query(query=ipam_query, query_id=ipam_query_id)
                if self.job:
                    self.job.logger.info("Received %s IPAM records from Forward Enterprise", len(self.ipam_data))
            else:
                if self.job:
                    self.job.logger.warning(
                        "IPAM sync enabled but no ipam_query or ipam_query_id found in extra_config"
                    )

        self.load_tags()
        self.load_locations()
        self.load_manufacturers()
        self.load_device_types()
        self.load_platforms()
        self.load_roles()
        self.load_devices()

        # Load interfaces based on sync_interfaces flag and available data
        if self.sync_interfaces:
            if hasattr(self, "interfaces_data") and self.interfaces_data:
                self.load_interfaces()
            else:
                if self.job:
                    self.job.logger.warning("Interface sync enabled but no interface data available")

        # Load IPAM objects based on sync_ipam flag and available data
        if self.sync_ipam:
            if hasattr(self, "ipam_data") and self.ipam_data:
                self.load_ipam()
            else:
                if self.job:
                    self.job.logger.warning("IPAM sync enabled but no IPAM data available")

        # Load VLANs if we have interface data (VLANs are extracted from interface names)
        if self.sync_interfaces and (hasattr(self, "interfaces_data") or hasattr(self, "ipam_data")):
            self.load_vlans()

        # Log summary of loaded objects
        if self.job:
            summary = []
            for model_name in self.top_level:
                count = len(list(self.get_all(model_name)))
                summary.append(f"{model_name}: {count}")
            self.job.logger.info("Loaded objects from Forward Enterprise: %s", ", ".join(summary))

    def load_ipam(self):
        """Load IPAM data (VRFs, Prefixes, IP addresses, and assignments) from Forward Enterprise."""
        if self.job:
            self.job.logger.info("Processing %s IPAM records from Forward Enterprise", len(self.ipam_data))

        # Track unique VRFs for summary
        unique_vrfs = set()

        # Track processed IPs to avoid duplicates
        processed_ips = set()
        processed_prefixes = set()

        # Process each IPAM record
        for ipam_record in self.ipam_data:
            device_name = ipam_record.get("device")
            interface_name = ipam_record.get("interface")
            # Don't assign default VRF - use None if missing
            vrf_name = ipam_record.get("vrf") if ipam_record.get("vrf") else None
            ip_address = ipam_record.get("ip")
            prefix_length = ipam_record.get("prefixLength")

            # Track unique VRFs (including None for missing VRFs)
            unique_vrfs.add(vrf_name)

        # Log summary of unique VRFs found
        if self.job:
            vrf_list = sorted([v for v in unique_vrfs if v is not None])
            no_vrf_count = len([v for v in unique_vrfs if v is None])
            self.job.logger.info(
                "Found %s unique VRFs in IPAM data + %s records with no VRF", len(vrf_list), no_vrf_count
            )

        # Create all VRFs first before processing prefixes
        # Use the configured namespace from the job, not hard-coded "Global"
        namespace_obj = getattr(self, "namespace", None)
        namespace = namespace_obj.name if namespace_obj else "Global"
        for vrf_name in unique_vrfs:
            if vrf_name:  # Skip None VRFs
                self.load_vrf(vrf_name, namespace)

        # Process each IPAM record again for actual processing
        for ipam_record in self.ipam_data:
            device_name = ipam_record.get("device")
            interface_name = ipam_record.get("interface")
            # Don't assign default VRF - use None if missing
            vrf_name = ipam_record.get("vrf") if ipam_record.get("vrf") else None
            ip_address = ipam_record.get("ip")
            prefix_length = ipam_record.get("prefixLength")

            if not all([device_name, interface_name, ip_address, prefix_length]):
                if self.job:
                    self.job.logger.warning("Skipping incomplete IPAM record: %s", ipam_record)
                continue

            try:
                # Calculate network prefix
                mask_length = int(prefix_length)
                network = ipaddress.ip_network(f"{ip_address}/{mask_length}", strict=False)
                prefix_str = network.with_prefixlen

                # Create prefix (with VRF assignment only if VRF exists) - avoid duplicates
                prefix_key = f"{prefix_str}|{vrf_name}"
                if prefix_key not in processed_prefixes:
                    self.load_prefix(prefix_str, vrf_name)
                    processed_prefixes.add(prefix_key)

                # Create IP address - avoid duplicates
                ip_key = f"{ip_address}/{mask_length}"
                if ip_key not in processed_ips:
                    self.load_ipaddress(ip_address, mask_length, network.network_address.compressed, network.prefixlen)
                    processed_ips.add(ip_key)

                # Create IP assignment to interface (this can have duplicates for different interfaces)
                self.load_ipassignment(ip_address, device_name, interface_name)

            except (KeyError, ValueError, TypeError) as exception:
                if self.job:
                    self.job.logger.warning("Failed to process IPAM record %s: %s", ipam_record, exception)

    def load_vlans(self):
        """Extract and load VLAN information from interface names and data, scoped by location."""
        if self.job:
            self.job.logger.info("Extracting VLANs from interface data, scoped by device location")

        # Extract VLANs grouped by location using utility function
        vlans_by_location = extract_vlans_by_location(self)

        # Create VLAN objects for each unique VLAN ID found per location
        total_vlans = 0
        for location_name, vlan_ids in vlans_by_location.items():
            for vlan_id in vlan_ids:
                self.load_vlan(vlan_id, location_name)
                total_vlans += 1

        if self.job and total_vlans > 0:
            self.job.logger.info("Found %s unique VLANs across %s locations", total_vlans, len(vlans_by_location))

    def load_vlan(self, vlan_id, location_name):
        """Create a VLAN DiffSync object scoped to a specific location."""
        vlan_name = f"VLAN-{vlan_id}"
        vlan_group_name = create_vlan_group_name(location_name)

        # Check if VLAN already exists
        try:
            self.get("vlan", {"vid": vlan_id, "name": vlan_name, "vlan_group__name": vlan_group_name})
            return
        except (KeyError, ObjectNotFound):
            pass

        # Create VLAN object
        new_vlan = self.vlan(
            vid=vlan_id,
            name=vlan_name,
            vlan_group__name=vlan_group_name,
            description=f"VLAN {vlan_id} imported from {constants.SYSTEM_OF_RECORD} interface data",
            status__name="Active",
            tenant__name=None,
            role=None,
            system_of_record=constants.SYSTEM_OF_RECORD,
        )

        try:
            self.add(new_vlan)
            # Don't log here - this is just loading into DiffSync, not creating in Nautobot
        except ObjectAlreadyExists:
            # VLAN already exists in DiffSync - debug log for troubleshooting
            if self.job:
                self.job.logger.debug(
                    "VLAN %s (VID: %s) already exists in DiffSync for location %s", vlan_name, vlan_id, location_name
                )
