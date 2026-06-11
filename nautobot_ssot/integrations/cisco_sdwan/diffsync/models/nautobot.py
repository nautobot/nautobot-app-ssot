"""Nautobot DiffSync models for the Cisco SD-WAN SSoT integration."""

from django.core.exceptions import ObjectDoesNotExist
from nautobot.dcim.models import Device as NBDevice
from nautobot.dcim.models import Interface as NBInterface
from nautobot.extras.models import Status as NBStatus
from nautobot.ipam.models import IPAddressToInterface as NBIPAddressToInterface

from nautobot_ssot.integrations.cisco_sdwan.constants import (
    DATA_SOURCE_NAME,
    DEFAULT_IPADDRESS_STATUS,
    DEVICE_RETIRED_STATUS,
    PRIMARY_IP_INTERFACES,
    SOFTWARE_VERSION_PLATFORM_NAME,
)
from nautobot_ssot.integrations.cisco_sdwan.diffsync.models.base import (
    Device,
    DeviceType,
    Interface,
    IPAddressToInterface,
    SoftwareVersion,
)
from nautobot_ssot.integrations.cisco_sdwan.utils.nautobot import get_or_create_ip_address, get_or_create_vrf

# Limit shared objects (DeviceTypes, SoftwareVersions) loaded from Nautobot to those
# previously synchronized by this integration. The MetadataType is created by the SSoT
# framework when this Job is listed in the `enable_metadata_for` setting.
OBJECT_METADATA_FILTER = {
    "associated_object_metadata__metadata_type__name": f"Last sync from {DATA_SOURCE_NAME}",
}


class NautobotDevice(Device):
    """Nautobot implementation of Device model."""

    @classmethod
    def get_queryset(cls, data):  # pylint: disable=arguments-differ
        """Get the queryset for the model."""
        queryset = cls._model.objects.filter(controller_managed_device_group=data["managed_device_group"]).exclude(
            status__name=DEVICE_RETIRED_STATUS
        )
        if data.get("devices"):
            queryset = queryset.filter(id__in=data.get("devices"))
        queryset = queryset.select_related(
            "device_type",
            "platform",
            "tenant",
            "status",
            "location",
            "primary_ip4",
            "software_version",
            "secrets_group",
            "role",
        )
        return queryset

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Nautobot from NautobotDevice object."""
        if NBDevice.objects.filter(name=ids.get("name")).exists():
            # Devices that are marked as Retired in Nautobot but retrieved from the SD-WAN Manager
            obj = NBDevice.objects.get(name=ids.get("name"))
            adapter.job.logger.error(
                f"Device {obj.name} cannot be created as it already exists in Nautobot with status {obj.status.name}."
            )
            return None
        model_instance = super().create(adapter=adapter, ids=ids, attrs=attrs)
        obj = NBDevice.objects.get(name=ids.get("name"))
        adapter.job.managed_device_group.devices.add(obj)
        return model_instance

    def update(self, attrs):
        """Update the ORM object corresponding to this diffsync object."""
        obj = self.get_from_db()
        # Keep the existing location on updates; devices are only placed at the staging
        # location on creation and their location is managed in Nautobot afterwards.
        if "location__name" in attrs:
            if self.adapter.job.debug:
                self.adapter.job.logger.info(
                    f"Location of {self.name} will not be updated to avoid overriding the location data in Nautobot."
                )
            attrs["location__name"] = self.location__name
        # SoftwareVersion is resolved by (version, platform) so both attributes must be present together.
        if ("software_version__version" in attrs) and ("software_version__platform__name" not in attrs):
            attrs["software_version__platform__name"] = (
                obj.software_version.platform.name if obj.software_version else SOFTWARE_VERSION_PLATFORM_NAME
            )
        if ("software_version__platform__name" in attrs) and ("software_version__version" not in attrs):
            if obj.software_version:
                attrs["software_version__version"] = obj.software_version.version
            else:
                attrs.pop("software_version__platform__name")
        return super().update(attrs)

    def delete(self):
        """Soft-delete a Device in Nautobot by setting its status to the configured retired status."""
        obj = self.get_from_db()
        obj.status = NBStatus.objects.get(name=DEVICE_RETIRED_STATUS)
        obj.validated_save()
        return self


class NautobotDeviceType(DeviceType):
    """Nautobot implementation of DeviceType model."""

    @classmethod
    def get_queryset(cls, data):  # pylint: disable=arguments-differ
        """Get the queryset for the model."""
        queryset = cls._model.objects.filter(**OBJECT_METADATA_FILTER).select_related("manufacturer").distinct()
        if data.get("devices"):
            queryset = queryset.filter(devices__in=data.get("devices"))
        return queryset


class NautobotInterface(Interface):
    """Nautobot implementation of Interface model."""

    @classmethod
    def get_queryset(cls, data):  # pylint: disable=arguments-differ
        """Get the queryset for the model."""
        queryset = cls._model.objects.filter(
            device__controller_managed_device_group=data["managed_device_group"]
        ).select_related("status", "device")
        if data.get("devices"):
            queryset = queryset.filter(device__in=data.get("devices"))
        return queryset


class NautobotIPAddressToInterface(IPAddressToInterface):
    """Nautobot implementation of IPAddressToInterface model."""

    @classmethod
    def get_queryset(cls, data):  # pylint: disable=arguments-differ
        """Get the queryset for the model."""
        queryset = (
            cls._model.objects.filter(interface__device__controller_managed_device_group=data["managed_device_group"])
            .select_related("interface", "ip_address", "interface__vrf", "interface__device")
            .distinct()
        )
        if data.get("devices"):
            queryset = queryset.filter(interface__device__in=data.get("devices"))
        return queryset

    @classmethod
    def _replace_existing_assignments(cls, adapter, interface, ip_address_obj):
        """Remove existing IP assignments from an Interface before assigning a new IP Address.

        The SD-WAN Manager reports a single IPv4 address per interface, so any other address
        currently assigned to the interface is unassigned. The IPAddress objects themselves are
        only deleted when the Job is run with `delete_replaced_ips` enabled and they are no
        longer assigned to any other interface.
        """
        for assignment in NBIPAddressToInterface.objects.filter(interface=interface).exclude(ip_address=ip_address_obj):
            old_ip = assignment.ip_address
            assignment.delete()
            if (
                getattr(adapter.job, "delete_replaced_ips", False)
                and not NBIPAddressToInterface.objects.filter(ip_address=old_ip).exists()
            ):
                try:
                    if adapter.job.debug:
                        adapter.job.logger.debug(f"Deleting replaced IPAddress {old_ip} from {interface.device}.")
                    old_ip.delete()
                except Exception as err:  # pylint: disable=broad-exception-caught
                    adapter.job.logger.warning(f"Unable to delete replaced IPAddress {old_ip}: {err}")

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Nautobot."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating IPAddressToInterface {ids} {attrs}")

        # Get the Interface
        interface = NBInterface.objects.get(name=ids["interface__name"], device__name=ids["interface__device__name"])

        # Get or create the IP Address
        address = f"{ids['ip_address__host']}/{ids['ip_address__mask_length']}"
        ip_address_obj, _ = get_or_create_ip_address(
            adapter=adapter, address=address, status=NBStatus.objects.get(name=DEFAULT_IPADDRESS_STATUS)
        )

        # Create VRF associations
        if attrs.get("interface__vrf__name"):
            vrf = get_or_create_vrf(adapter, attrs.get("interface__vrf__name"))
            if vrf not in interface.device.vrfs.all():
                interface.device.vrfs.add(vrf)
            interface.vrf = vrf
            interface.validated_save()

        if not ip_address_obj:
            return None

        try:
            NBIPAddressToInterface.objects.get(interface=interface, ip_address=ip_address_obj)
            adapter.job.logger.info(f"IPAddress {ip_address_obj} already assigned to {interface} on {interface.device}")
        except ObjectDoesNotExist:
            # Unassign (and optionally delete) any other address on the interface first
            cls._replace_existing_assignments(adapter=adapter, interface=interface, ip_address_obj=ip_address_obj)
            ip_address_assignment = NBIPAddressToInterface(interface=interface, ip_address=ip_address_obj)
            if adapter.job.debug:
                adapter.job.logger.debug(f"Assigning {ip_address_obj} to {interface} on {interface.device}")
            ip_address_assignment.validated_save()
            # Refresh state from the database, otherwise `interface.device.primary_ip4`
            # fails if the address of a primary IP interface is changed.
            interface.refresh_from_db()

        if interface.name in PRIMARY_IP_INTERFACES and ip_address_obj != interface.device.primary_ip4:
            interface.device.primary_ip4 = ip_address_obj
            interface.device.validated_save()

        return super().create_base(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddressToInterface in Nautobot."""
        obj = self.get_from_db()

        # Create VRF associations
        vrf_name = attrs.get("interface__vrf__name")
        if vrf_name:
            vrf_obj = get_or_create_vrf(adapter=self.adapter, vrf_name=vrf_name)
            if not obj.interface.vrf or vrf_name != obj.interface.vrf.name:
                if vrf_obj not in obj.interface.device.vrfs.all():
                    obj.interface.device.vrfs.add(vrf_obj)
                obj.interface.vrf = vrf_obj
                obj.interface.validated_save()
        return super().update_base(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot."""
        obj = self.get_from_db()
        vrf = obj.interface.vrf
        if vrf:
            # Remove the VRF association from the Interface
            obj.interface.vrf = None
            obj.interface.validated_save()
            # Remove the VRF association from the Device if no other interface uses it
            if vrf.interfaces.filter(device=obj.interface.device).count() == 0:
                obj.interface.device.vrfs.remove(vrf)
            # Delete the VRF from Nautobot if it is no longer used at all
            if vrf.interfaces.count() == 0:
                vrf.delete()
        return super().delete_base()


class NautobotSoftwareVersion(SoftwareVersion):
    """Nautobot implementation of SoftwareVersion model."""

    @classmethod
    def get_queryset(cls, data):  # pylint: disable=arguments-differ
        """Get the queryset for the model."""
        queryset = (
            cls._model.objects.filter(platform__name=SOFTWARE_VERSION_PLATFORM_NAME)
            .filter(**OBJECT_METADATA_FILTER)
            .select_related("status", "platform")
            .distinct()
        )
        if data.get("devices"):
            queryset = queryset.filter(devices__in=data.get("devices"))
        return queryset
