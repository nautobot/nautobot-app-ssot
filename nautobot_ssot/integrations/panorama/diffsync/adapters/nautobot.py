"""Nautobot Adapter for Panorama SSoT plugin."""

from diffsync import DiffSyncModel
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from nautobot.dcim.models import (
    ControllerManagedDeviceGroup,
    Device,
    DeviceType,
    Interface,
    InterfaceVDCAssignment,
    VirtualDeviceContext,
)
from nautobot.ipam.models import IPAddress, IPAddressToInterface

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.panorama.diffsync.models.nautobot import (
    NautobotControllerManagedDeviceGroup,
    NautobotDeviceToControllerManagedDeviceGroup,
    NautobotDeviceType,
    NautobotFirewall,
    NautobotFirewallInterface,
    NautobotIPAddressToInterface,
    NautobotSoftwareVersion,
    NautobotSoftwareVersionToDevice,
    NautobotVdc,
    NautobotVdcToControllerManagedDeviceGroup,
    NautobotVirtualDeviceContextAssociation,
)
from nautobot_ssot.integrations.panorama.models import (
    VirtualDeviceContextToControllerManagedDeviceGroup,
)

app_settings = settings.PLUGINS_CONFIG.get("nautobot_ssot")


class PanoSSoTNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    device_type = NautobotDeviceType
    firewall = NautobotFirewall
    firewall_interface = NautobotFirewallInterface
    ip_address_to_interface = NautobotIPAddressToInterface
    vdc = NautobotVdc
    virtualdevicecontextassociation = NautobotVirtualDeviceContextAssociation
    softwareversion = NautobotSoftwareVersion
    softwareversiontodevice = NautobotSoftwareVersionToDevice
    controllermanageddevicegroup = NautobotControllerManagedDeviceGroup
    devicetocontrollermanageddevicegroup = NautobotDeviceToControllerManagedDeviceGroup
    vdctocontrollermanageddevicegroup = NautobotVdcToControllerManagedDeviceGroup

    top_level = [
        "device_type",
        "firewall",
        "firewall_interface",
        "ip_address_to_interface",
        "vdc",
        "virtualdevicecontextassociation",
        "softwareversion",
        "softwareversiontodevice",
        "controllermanageddevicegroup",
        "devicetocontrollermanageddevicegroup",
        "vdctocontrollermanageddevicegroup",
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
            "controllermanageddevicegroup": (
                "Loading Nautobot Controller Managed Device Groups",
                self.load_controller_managed_device_groups,
            ),
            "devicetocontrollermanageddevicegroup": (
                "Loading Nautobot Devices to Controller Managed Device Groups",
                self.load_devices_to_controller_managed_device_groups,
            ),
            "vdctocontrollermanageddevicegroup": (
                "Loading Nautobot VDC to Controller Managed Device Group associations",
                self.load_vdcs_to_controller_managed_device_groups,
            ),
            "vdc": (
                "Loading Nautobot Virtual Device Contexts",
                self.load_virtual_device_contexts,
            ),
            "virtualdevicecontextassociation": (
                "Loading Nautobot Interface to VDC associations",
                self.load_virtual_device_context_associations,
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

    def load_controller_managed_device_groups(self):
        """Load Nautobot ControllerManagedDeviceGroup objects for the current controller."""
        for cmdg in ControllerManagedDeviceGroup.objects.filter(controller=self.job.panorama_controller):
            try:
                parent_name = cmdg.parent.name if cmdg.parent else None
                controllermanageddevicegroup = self.controllermanageddevicegroup(
                    name=cmdg.name,
                    controller__name=cmdg.controller.name,
                    parent__name=parent_name,
                )
                self.add(controllermanageddevicegroup)
            except Exception as err:
                self.job.logger.error(f"Error loading controller managed device group {cmdg}, {err}")
                continue

    def load_devices_to_controller_managed_device_groups(self):
        """Load Nautobot DeviceToControllerManagedDeviceGroup objects."""
        for device_serial in self.job.loaded_panorama_devices:
            try:
                device = Device.objects.get(serial=device_serial)
                if device.controller_managed_device_group:
                    self.add(
                        self.devicetocontrollermanageddevicegroup(
                            device__serial=device_serial,
                            controllermanageddevicegroup__name=device.controller_managed_device_group.name,
                        )
                    )
            except ObjectDoesNotExist:
                continue
            except Exception as err:
                self.job.logger.error(f"Error loading device to CMDG for {device_serial}, {err}")
                continue

    def load_vdcs_to_controller_managed_device_groups(self):
        """Load Nautobot VdcToControllerManagedDeviceGroup objects."""
        for assignment in VirtualDeviceContextToControllerManagedDeviceGroup.objects.filter(
            virtual_device_context__device__serial__in=self.job.loaded_panorama_devices
        ):
            try:
                self.add(
                    self.vdctocontrollermanageddevicegroup(
                        controller_managed_device_group__name=assignment.controller_managed_device_group.name,
                        virtual_device_context__device__serial=assignment.virtual_device_context.device.serial,
                        virtual_device_context__name=assignment.virtual_device_context.name,
                    )
                )
            except Exception as err:
                self.job.logger.error(f"Error loading VDC-to-CMDG for {assignment}, {err}")
                continue

    def load_virtual_device_contexts(self):
        """Load Nautobot VirtualDeviceContext objects."""
        for vdc_obj in VirtualDeviceContext.objects.filter(device__serial__in=self.job.loaded_panorama_devices):
            try:
                vdc = self.vdc(
                    name=vdc_obj.name,
                    parent=vdc_obj.device.serial,
                )
                self.add(vdc)
            except ObjectAlreadyExists:
                pass
            except Exception as err:
                self.job.logger.error(f"Error loading Nautobot VirtualDeviceContext{vdc_obj}, {err}")
                continue

    def load_virtual_device_context_associations(self):
        """Load Nautobot VirtualDeviceContextAssociation objects."""
        interfaces = Interface.objects.filter(device__serial__in=self.job.loaded_panorama_devices)
        for virtualdevicecontextassociation_obj in InterfaceVDCAssignment.objects.filter(interface__in=interfaces):
            try:
                virtualdevicecontextassociation = self.virtualdevicecontextassociation(
                    virtual_device_context__device__serial=virtualdevicecontextassociation_obj.virtual_device_context.device.serial,
                    virtual_device_context__name=virtualdevicecontextassociation_obj.virtual_device_context.name,
                    interface__name=virtualdevicecontextassociation_obj.interface.name,
                    interface__device__serial=virtualdevicecontextassociation_obj.interface.device.serial,
                )
                self.add(virtualdevicecontextassociation)
            except Exception as err:
                self.job.logger.error(
                    f"Error loading virtual device context assignment {virtualdevicecontextassociation_obj}, {err}"
                )
