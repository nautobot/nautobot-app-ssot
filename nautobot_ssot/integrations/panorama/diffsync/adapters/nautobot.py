"""Nautobot Adapter for Panorama SSoT plugin."""

from diffsync import DiffSyncModel
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from nautobot.dcim.models import ControllerManagedDeviceGroup, Device, DeviceType, Interface
from nautobot.ipam.models import IPAddress, IPAddressToInterface

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.panorama.diffsync.models.nautobot import (
    NautobotControllerManagedDeviceGroup,
    NautobotDeviceToControllerManagedDeviceGroup,
    NautobotDeviceType,
    NautobotFirewall,
    NautobotFirewallInterface,
    NautobotIPAddressToInterface,
    NautobotLogicalGroup,
    NautobotLogicalGroupToDevice,
    NautobotLogicalGroupToVirtualSystem,
    NautobotSoftwareVersion,
    NautobotSoftwareVersionToDevice,
    NautobotVirtualSystemAssociation,
    NautobotVsys,
)
from nautobot_ssot.integrations.panorama.models import (
    LogicalGroupToDevice,
    LogicalGroupToVirtualSystem,
    VirtualSystem,
    VirtualSystemAssociation,
)

app_settings = settings.PLUGINS_CONFIG.get("nautobot_ssot")


class PanoSSoTNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    logicalgroup = NautobotLogicalGroup
    device_type = NautobotDeviceType
    firewall = NautobotFirewall
    firewall_interface = NautobotFirewallInterface
    ip_address_to_interface = NautobotIPAddressToInterface
    vsys = NautobotVsys
    virtualsystemassociation = NautobotVirtualSystemAssociation
    logicalgrouptovirtualsystem = NautobotLogicalGroupToVirtualSystem
    logicalgrouptodevice = NautobotLogicalGroupToDevice
    softwareversion = NautobotSoftwareVersion
    softwareversiontodevice = NautobotSoftwareVersionToDevice
    controllermanageddevicegroup = NautobotControllerManagedDeviceGroup
    devicetocontrollermanageddevicegroup = NautobotDeviceToControllerManagedDeviceGroup

    top_level = [
        "device_type",
        "firewall",
        "firewall_interface",
        "ip_address_to_interface",
        "vsys",
        "virtualsystemassociation",
        "logicalgroup",
        "logicalgrouptovirtualsystem",
        "logicalgrouptodevice",
        "softwareversion",
        "softwareversiontodevice",
        "controllermanageddevicegroup",
        "devicetocontrollermanageddevicegroup",
    ]

    def __init__(self, *args, **kwargs):
        """Initialize PanoSSoTNautobotAdapter."""
        super().__init__(*args, **kwargs)
        self._backend = "Nautobot"
        self.firewall_primary_ip_map = {}

    def get_or_add(self, obj: "DiffSyncModel") -> "DiffSyncModel":
        """Ensures a model is added.

        Args:
            obj (DiffSyncModel): Instance of model

        Returns:
            DiffSyncModel: Instance of model that has been added
        """
        model = obj.get_type()
        ids = obj.get_unique_id()
        try:
            return self.store.get(model=model, identifier=ids)
        except ObjectNotFound:
            self.add(obj=obj)
            return obj

    def load(self):
        """Generic implementation of the load function."""
        if not hasattr(self, "top_level") or not self.top_level:
            raise ValueError("'top_level' needs to be set on the class")

        loaders = {
            "logicalgroup": ("Loading Nautobot Logical Groups", self.load_logical_groups),
            "logicalgrouptovirtualsystem": (
                "Loading Nautobot Device Group to Vsys associations",
                self.load_logical_groups_to_virtual_systems,
            ),
            "logicalgrouptodevice": (
                "Loading Nautobot Device Group to Firewall associations",
                self.load_logical_groups_to_devices,
            ),
            "device_type": (
                "Loading Nautobot Device Types",
                self.load_device_types,
            ),
            "firewall": (
                "Loading Nautobot Firewalls",
                self.load_firewalls,
            ),
            "firewall_interface": (
                "Loading Nautobot Firewall Interfaces",
                self.load_firewall_interfaces,
            ),
            "ip_address_to_interface": (
                "Loading Nautobot IP Address to Interface",
                self.load_ip_address_to_interface_objects,
            ),
            "softwareversiontodevice": (
                "Loading Nautobot Software Versions to Devices",
                self.load_software_versions_to_devices,
            ),
            "devicetocontrollermanageddevicegroup": (
                "Loading Nautobot Devices to Controller Managed Device Groups",
                self.load_devices_to_controller_managed_device_groups,
            ),
            "vsys": (
                "Loading Nautobot Virtual Systems",
                self.load_virtual_system_objects,
            ),
            "virtualsystemassociation": (
                "Loading Nautobot Interface to Vsys associations",
                self.load_virtual_system_associations,
            ),
        }
        for model_name in self.top_level:
            loader = loaders.get(model_name)
            if loader:
                log_msg, func = loader
                self.job.logger.info(log_msg)
                func()
            else:
                self.job.logger.info(f"Loading {model_name} from Nautobot")
                diffsync_model = self._get_diffsync_class(model_name)
                self._load_objects(diffsync_model)

    def sync_complete(self, source, diff, *args, **kwargs):
        """Sync complete callback. Only called if there is a diff."""
        # Create a custom relationship for app containters
        if source._backend == "Nautobot":
            return

        # Update firewall primary IP assignments
        # Used if the primary ip appears in the diff when creating or updating a firewall
        if self.firewall_primary_ip_map:
            self.job.logger.info("Updating firewall primary IP assignments")
            for firewall, ip in self.firewall_primary_ip_map.items():
                try:
                    device = Device.objects.get(serial=firewall)
                    primary_ip = IPAddress.objects.get(host=ip)
                    device.primary_ip4 = primary_ip
                    device.validated_save()
                except Exception as err:
                    self.job.logger.error(f"Failed to update primary IP for {firewall}, {err}")
                    continue

    def load_device_types(self):
        """Load Nautobot DeviceType objects."""
        manufacturer_name = app_settings.get("panorama_firewall_platform_name", "Palo Alto")
        for device_type_obj in DeviceType.objects.filter(manufacturer__name=manufacturer_name):
            device_type = self.device_type(
                model=device_type_obj.model,
                part_number=device_type_obj.part_number,
                manufacturer__name=device_type_obj.manufacturer.name,
            )
            self.add(device_type)

    def load_firewalls(self):
        """Load Nautobot Firewall objects."""
        for firewall_obj in Device.objects.filter(serial__in=self.job.loaded_panorama_devices):
            try:
                # Determine the management interface name
                if firewall_obj.primary_ip4:
                    management_interface = Interface.objects.filter(
                        device=firewall_obj, ip_addresses__in=[firewall_obj.primary_ip4]
                    ).first()
                else:
                    management_interface = None
                firewall = self.firewall(
                    serial=firewall_obj.serial,
                    name=firewall_obj.name,
                    model=firewall_obj.device_type.model,
                    management_ip=str(firewall_obj.primary_ip4) if firewall_obj.primary_ip4 else "",
                    management_interface_name=management_interface.name if management_interface else "",
                )
                self.add(firewall)
            except Exception as err:
                self.job.logger.error(f"Error loading Nautobot Firewall {firewall_obj}, {err}")
                continue

    def load_firewall_interfaces(self):
        """Load Nautobot Firewall objects."""
        for interface_obj in Interface.objects.filter(device__serial__in=self.job.loaded_panorama_devices):
            try:
                firewall_interface = self.firewall_interface(
                    device__serial=interface_obj.device.serial,
                    name=interface_obj.name,
                    status__name=interface_obj.status.name,
                    type=interface_obj.type,
                    description=interface_obj.description,
                    pk=interface_obj.pk,
                )
                self.add(firewall_interface)
            except Exception as err:
                self.job.logger.error(f"Error loading Nautobot interface {interface_obj},  {err}")
                continue

    def load_ip_address_to_interface_objects(self):
        """Load Nautobot DeviceType objects."""
        for interface_assignment in IPAddressToInterface.objects.filter(
            interface__device__serial__in=self.job.loaded_panorama_devices
        ):
            try:
                ip_address_to_interface = self.ip_address_to_interface(
                    interface__device__serial=interface_assignment.interface.device.serial,
                    interface__name=interface_assignment.interface.name,
                    ip_address__host=str(interface_assignment.ip_address.host),
                    ip_address__mask_length=str(interface_assignment.ip_address.mask_length),
                )
                self.add(ip_address_to_interface)
            except Exception as err:
                self.job.logger.error(
                    f"Error loading Nautobot IP address to interface association {interface_assignment}, {err}"
                )
                continue

    def load_software_versions_to_devices(self):
        """Load Nautobot SoftwareVersionToDevice objects."""
        for device in Device.objects.filter(serial__in=self.job.loaded_panorama_devices):
            try:
                softwareversiontodevice = self.softwareversiontodevice(
                    device__serial=device.serial,
                    platform__name=device.platform.name,
                    version=device.software_version.version if device.software_version else "",
                )
                self.add(softwareversiontodevice)
            except Exception as err:
                self.job.logger.error(f"Error loading software version to device for {device}, {err}")
                continue

    def load_devices_to_controller_managed_device_groups(self):
        """Load Nautobot DeviceToControllerManagedDeviceGroup objects."""
        for device_serial in self.job.loaded_panorama_devices:
            try:
                device = Device.objects.get(serial=device_serial)
                device_group = ControllerManagedDeviceGroup.objects.get(
                    devices__in=[device], name__icontains="panorama devices"
                )
            except (
                ObjectDoesNotExist
            ):  # if the panorama devices have not been added to a controller managed device group, this is expected
                continue
            # It is possible to add a device to multiple controller managed device groups. To account for this, we assume the device
            # group will contain "Panorama Devices" in the name, and we will only add the device to that group. In the unlikely event
            # that multiple device groups contain "Panorama Devices" in the name, we will log an error and skip adding the device to the group.
            # "Panorama Devices" is appended to the controller name in the Panrama adapter when defining the contoller managed device gorup name.
            except MultipleObjectsReturned as err:
                self.job.logger.error(f"Multiple controller managed device groups found for {device_serial}: {err}")
                continue
            try:
                controllermanageddevicegroup = self.devicetocontrollermanageddevicegroup(
                    device__serial=device_serial,
                    controllermanageddevicegroup__name=device_group.name,
                )
                self.add(controllermanageddevicegroup)
            except Exception as err:
                self.job.logger.error(f"Error loading device to controller managed device group for {device}, {err}")
                continue

    def load_virtual_system_objects(self):
        """Load Nautobot VirtualSystem objects."""
        for vsys_obj in VirtualSystem.objects.filter(device__serial__in=self.job.loaded_panorama_devices):
            try:
                vsys = self.vsys(
                    name=vsys_obj.name,
                    parent=vsys_obj.device.serial,
                )
                self.add(vsys)
            except ObjectAlreadyExists:
                pass
            except Exception as err:
                self.job.logger.error(f"Error loading Nautobot VirtualSystem {vsys_obj}, {err}")
                continue

    def load_virtual_system_associations(self):
        """Load Nautobot VirtualSystemAssociation objects."""
        interfaces = Interface.objects.filter(device__serial__in=self.job.loaded_panorama_devices)
        for virtualsystemassociation_obj in VirtualSystemAssociation.objects.filter(iface__in=interfaces):
            try:
                virtualsystemassociation = self.virtualsystemassociation(
                    vsys__device__serial=virtualsystemassociation_obj.vsys.device.serial,
                    vsys__name=virtualsystemassociation_obj.vsys.name,
                    iface__name=virtualsystemassociation_obj.iface.name,
                    iface__device__serial=virtualsystemassociation_obj.iface.device.serial,
                )
                self.add(virtualsystemassociation)
            except Exception as err:
                self.job.logger.error(f"Error loading virtual system association {virtualsystemassociation_obj}, {err}")

    def load_logical_groups(self):
        """Load Nautobot LogicalGroup objects."""
        for group in self.job.panorama_controller.logical_groups.all():
            parent = None
            if group.parent:
                parent = group.parent.name

            logicalgroup = self.logicalgroup(
                name=group.name,
                panorama=str(group.control_plane.id),
                parent=parent,
            )
            self.add(logicalgroup)

    def load_logical_groups_to_devices(self):
        """Load Nautobot LogicalGroupToDevice objects."""
        for logicalgrouptodevice_obj in LogicalGroupToDevice.objects.filter(
            device__serial__in=self.job.loaded_panorama_devices
        ):
            try:
                logicalgrouptodevice = self.logicalgrouptodevice(
                    group__name=logicalgrouptodevice_obj.group.name,
                    device__serial=logicalgrouptodevice_obj.device.serial,
                )
                self.add(logicalgrouptodevice)
            except Exception as err:
                self.job.logger.error(
                    f"Error loading logical group to device association {logicalgrouptodevice_obj}, {err}"
                )
                continue

    def load_logical_groups_to_virtual_systems(self):
        """Load Nautobot LogicalGroupToVirtualSystem objects."""
        for logicalgrouptovirtualsystem_obj in LogicalGroupToVirtualSystem.objects.filter(
            vsys__device__serial__in=self.job.loaded_panorama_devices
        ):
            try:
                logicalgrouptovirtualsystem = self.logicalgrouptovirtualsystem(
                    group__name=logicalgrouptovirtualsystem_obj.group.name,
                    vsys__name=logicalgrouptovirtualsystem_obj.vsys.name,
                    vsys__device__serial=logicalgrouptovirtualsystem_obj.vsys.device.serial,
                )
                self.add(logicalgrouptovirtualsystem)
            except Exception as err:
                self.job.logger.error(
                    f"Error loading logical group to virtual system association {logicalgrouptovirtualsystem_obj}, {err}"
                )
                continue
