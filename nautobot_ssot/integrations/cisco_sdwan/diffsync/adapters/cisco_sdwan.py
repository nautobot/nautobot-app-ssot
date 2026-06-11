"""Cisco SD-WAN adapter for the Cisco SD-WAN SSoT integration."""

from diffsync import Adapter, DiffSyncModel
from diffsync.exceptions import ObjectNotFound
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from netutils.ip import ipaddress_interface, is_ip_within, netmask_to_cidr

from nautobot_ssot.integrations.cisco_sdwan.constants import (
    DEFAULT_INTERFACE_STATUS,
    DEFAULT_INTERFACE_TYPE,
    EXCLUDED_INTERFACES,
    EXCLUDED_PREFIXES,
    NULL_MTU_VALUES,
    SDWAN_IF_UP_STATES,
    SDWAN_NULL_IP_ADDRESSES,
    SOFTWARE_VERSION_PLATFORM_NAME,
)
from nautobot_ssot.integrations.cisco_sdwan.diffsync.models.cisco_sdwan import (
    CiscoSdwanDevice,
    CiscoSdwanDeviceType,
    CiscoSdwanInterface,
    CiscoSdwanIPAddressToInterface,
    CiscoSdwanSoftwareVersion,
)
from nautobot_ssot.integrations.cisco_sdwan.utils.cisco_sdwan import (
    CiscoSdwanManager,
    normalize_device_model,
    normalize_software_version,
)


class CiscoSdwanRemoteAdapter(Adapter):
    """DiffSync adapter for the Cisco Catalyst SD-WAN Manager."""

    device = CiscoSdwanDevice
    device_type = CiscoSdwanDeviceType
    interface = CiscoSdwanInterface
    ip_address_to_interface = CiscoSdwanIPAddressToInterface
    software_version = CiscoSdwanSoftwareVersion

    top_level = [
        "device_type",
        "software_version",
        "device",
        "interface",
        "ip_address_to_interface",
    ]

    def __init__(self, *args, job=None, sync=None, **kwargs):
        """Initialize the Cisco SD-WAN adapter.

        Args:
            job (object, optional): Cisco SD-WAN SSoT job. Defaults to None.
            sync (object, optional): SSoT Sync object. Defaults to None.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        # Initiate the SD-WAN Manager API client with credentials from the Controller's ExternalIntegration
        _sg = self.job.controller.external_integration.secrets_group
        username = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        password = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        self.sdwan_manager = CiscoSdwanManager(
            job=self.job,
            username=username,
            password=password,
            verify=self.job.controller.external_integration.verify_ssl,
            base_url=self.job.controller.external_integration.remote_url,
        )
        # Initiate the SD-WAN device cache
        self.sdwan_devices = []

    def get_or_add(self, obj: "DiffSyncModel") -> "DiffSyncModel":
        """Ensure a model is added to the store.

        Args:
            obj (DiffSyncModel): Instance of model.

        Returns:
            DiffSyncModel: Instance of model that has been added.
        """
        model = obj.get_type()
        ids = obj.get_unique_id()
        try:
            return self.store.get(model=model, identifier=ids)
        except ObjectNotFound:
            self.add(obj=obj)
            return obj

    def load_cache(self):
        """Cache SD-WAN objects from the Catalyst SD-WAN Manager."""
        # cache SD-WAN devices
        self.job.logger.info("Creating a device cache from the Catalyst SD-WAN Manager.")
        self.sdwan_devices = self.sdwan_manager.get_devices(device_filter=self.job.devices)
        # normalize device model
        for device in self.sdwan_devices:
            if device.get("deviceModel"):
                device["deviceModel"] = normalize_device_model(
                    device_model=device["deviceModel"], pattern=self.job.model_normalization
                )
        # cache SD-WAN device interfaces
        self.job.logger.info(
            "Creating a device interfaces cache from the Catalyst SD-WAN Manager. "
            "This step may take several minutes to complete."
        )
        self.sdwan_devices = self.sdwan_manager.get_interfaces(devices=self.sdwan_devices)

    def load_device_types(self):
        """Load DeviceTypes from the Catalyst SD-WAN Manager."""
        device_models = set()
        # Creating a set of device models that exist in SD-WAN
        for device in self.sdwan_devices:
            if device.get("deviceModel"):
                device_models.add(device.get("deviceModel"))
        # Loop through the device model set to load DeviceTypes
        for device_model in device_models:
            device_type = self.get_or_add(
                self.device_type(
                    model=device_model,
                    part_number=device_model,
                    manufacturer__name=self.job.device_platform.manufacturer.name,
                )
            )
            if self.job.debug:
                self.job.logger.debug(f"Device Type: {device_type} added from the Catalyst SD-WAN Manager.")

    def load_software_versions(self):
        """Load SoftwareVersions from the Catalyst SD-WAN Manager."""
        software_versions = set()
        # Creating a set of software versions that exist in SD-WAN
        for device in self.sdwan_devices:
            if device.get("version"):
                software_versions.add(normalize_software_version(device.get("version")))
        # Loop through the software version set to load SoftwareVersions
        for software_version in software_versions:
            software_version_obj = self.get_or_add(
                self.software_version(
                    version=software_version,
                    platform__name=SOFTWARE_VERSION_PLATFORM_NAME,
                    status__name="Active",
                )
            )
            if self.job.debug:
                self.job.logger.debug(
                    f"Software Version: {software_version_obj} added from the Catalyst SD-WAN Manager."
                )

    def load_devices(self):
        """Load Devices from the Catalyst SD-WAN Manager."""
        for device in self.sdwan_devices:
            software_version = normalize_software_version(device.get("version"))
            device_obj = self.get_or_add(
                self.device(
                    name=device.get("host-name"),
                    status__name=self.job.device_status.name,
                    location__name=self.job.device_location.name,
                    platform__name=self.job.device_platform.name,
                    role__name=self.job.device_role.name,
                    device_type__model=device.get("deviceModel"),
                    serial=device.get("uuid", "").split("-")[-1],
                    secrets_group__name=self.job.device_secrets_group.name,
                    tenant__name=self.job.device_tenant.name if self.job.device_tenant else None,
                    software_version__version=software_version,
                    software_version__platform__name=SOFTWARE_VERSION_PLATFORM_NAME if software_version else None,
                )
            )
            if self.job.debug:
                self.job.logger.debug(f"Device: {device_obj} added from the Catalyst SD-WAN Manager.")

    def _validate_ip_address(self, interface: dict) -> str | None:
        """Validate and normalize an interface IP address, returning None if invalid or excluded."""
        ip = (interface.get("ip-address") or "").strip()
        if not ip or ip in SDWAN_NULL_IP_ADDRESSES:
            return None

        ifname = interface.get("ifname")
        device_id = interface.get("vdevice-name")

        mask = (interface.get("ipv4-subnet-mask") or "").strip()
        ip_interface = ip
        if mask:
            try:
                prefix_length = netmask_to_cidr(netmask=mask)
                ip_interface = f"{ip}/{prefix_length}"
            except ValueError as exc:
                self.job.logger.error(
                    f"Invalid subnet mask '{mask}' for IP {ip} (ifname={ifname}, device={device_id}): {exc}"
                )
                return None

        try:
            ip_host = str(ipaddress_interface(ip_interface, attr="ip"))
        except ValueError as exc:
            self.job.logger.error(f"Invalid IP '{ip_interface}' (ifname={ifname}, device={device_id}): {exc}")
            return None

        for prefix in EXCLUDED_PREFIXES:
            if is_ip_within(ip_host, prefix):
                if self.job.debug:
                    self.job.logger.debug(
                        f"Excluded IP '{ip_interface}' (ifname={ifname}, device={device_id}) within {prefix}."
                    )
                return None

        return ip_interface

    def _load_ip_address(self, device: dict, interface: dict) -> None:
        """Load IPAddressToInterface assignments from the Catalyst SD-WAN Manager."""
        ip_interface = self._validate_ip_address(interface)
        if ip_interface:
            ip_address__host = str(ipaddress_interface(ip_interface, attr="ip"))
            ip_address__mask_length = ipaddress_interface(ip_interface, attr="network.prefixlen")
            ip_address_to_interface_obj = self.get_or_add(
                self.ip_address_to_interface(
                    ip_address__host=ip_address__host,
                    ip_address__mask_length=ip_address__mask_length,
                    interface__device__name=device.get("host-name"),
                    interface__name=interface.get("ifname"),
                    interface__vrf__name=interface.get("vpn-id", ""),
                )
            )
            if self.job.debug:
                self.job.logger.debug(
                    f"IP Address to Interface: {ip_address_to_interface_obj} added from the Catalyst SD-WAN Manager."
                )

    def load_interfaces(self):
        """Load Interfaces from the Catalyst SD-WAN Manager."""
        for device in self.sdwan_devices:
            interfaces = device.get("interfaces", [])
            for interface in interfaces:
                if interface.get("ifname", "").lower() not in [excluded.lower() for excluded in EXCLUDED_INTERFACES]:
                    # Load Interface
                    interface_obj = self.get_or_add(
                        self.interface(
                            name=interface.get("ifname"),
                            device__name=device.get("host-name"),
                            status__name=DEFAULT_INTERFACE_STATUS,
                            type=DEFAULT_INTERFACE_TYPE,
                            mtu=interface.get("mtu") if interface.get("mtu", "") not in NULL_MTU_VALUES else None,
                            description=interface.get("description", ""),
                            enabled=(interface.get("if-admin-status", "").lower() in SDWAN_IF_UP_STATES),
                        )
                    )
                    if self.job.debug:
                        self.job.logger.debug(
                            f"Interface: {interface_obj} of device {device.get('host-name')} added "
                            "from the Catalyst SD-WAN Manager."
                        )
                    # Load IP Address and IPAddressToInterface
                    self._load_ip_address(device, interface)

    def load(self):
        """Load data from Cisco SD-WAN into SSoT models."""
        if self.job.debug:
            self.job.logger.debug(f"Catalyst SD-WAN Manager Version: {self.sdwan_manager.get_server_version()}")
        # Load Cache
        self.load_cache()
        # Load SD-WAN device types
        self.job.logger.info("Loading Device Types from Device Cache.")
        self.load_device_types()
        # Load SD-WAN Software Versions
        self.job.logger.info("Loading Software Versions from Device Cache.")
        self.load_software_versions()
        # Load SD-WAN devices
        self.job.logger.info("Loading Devices from Device Cache.")
        self.load_devices()
        # Load SD-WAN interfaces and IP Addresses
        self.job.logger.info("Loading Interfaces from Device Cache.")
        self.load_interfaces()
