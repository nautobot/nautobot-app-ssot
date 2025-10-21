"""Nautobot DiffSync models for LibreNMS SSoT."""

import os
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType, LocationType
from nautobot.dcim.models import Interface as ORMInterface
from nautobot.dcim.models import Location as ORMLocation
from nautobot.dcim.models import Manufacturer as ORMManufacturer
from nautobot.dcim.models import Platform as ORMPlatform
from nautobot.dcim.models import SoftwareImageFile as ORMSoftwareImageFile
from nautobot.dcim.models import SoftwareVersion as ORMSoftwareVersion
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER

from nautobot_ssot.integrations.librenms.constants import (
    LIBRENMS_LIB_MAPPER,
    LIBRENMS_LIB_MAPPER_REVERSE,
    os_manufacturer_map,
)
from nautobot_ssot.integrations.librenms.diffsync.models.base import Device, Location, Port
from nautobot_ssot.integrations.librenms.utils import check_sor_field


def ensure_ip_address(ip_address: str, ip_prefix: str, adapter: object):
    """Safely returns an IPAddress."""
    _namespace = Namespace.objects.get_or_create(name=adapter.job.tenant.name)[0]
    _namespace.validated_save()
    _prefix = Prefix.objects.get_or_create(
        prefix=ip_prefix, namespace=_namespace, status=Status.objects.get(name="Active")
    )[0]
    _prefix.validated_save()
    _ipaddress = IPAddress.objects.get_or_create(
        address=ip_address, parent=_prefix, namespace=_namespace, status=Status.objects.get(name="Active")
    )[0]
    _ipaddress.validated_save()

    return _ipaddress


def ensure_interface(interface_name: str, device: ORMDevice):
    """Safely returns an Interface."""
    _interface, created = ORMInterface.objects.get_or_create(
        name=interface_name, device=device, defaults={"status": Status.objects.get(name="Active"), "type": "virtual"}
    )
    if created:
        _interface.validated_save()
    return _interface


def ensure_role(role_name: str, content_type):
    """Safely returns a Role that support given ContentType."""
    content_type = ContentType.objects.get_for_model(content_type)
    role, _ = Role.objects.get_or_create(name=role_name)
    role.content_types.add(content_type)
    return role


def ensure_platform(platform_name: str, manufacturer: str):
    """Safely returns a Platform that support Devices."""
    _manufacturer, _ = ORMManufacturer.objects.get_or_create(name=manufacturer)
    _network_driver = LIBRENMS_LIB_MAPPER.get(ANSIBLE_LIB_MAPPER.get(platform_name, platform_name), platform_name)
    _platform, _ = ORMPlatform.objects.get_or_create(
        name=platform_name, defaults={"network_driver": _network_driver, "manufacturer": _manufacturer}
    )
    return _platform


def ensure_software_version(platform: ORMPlatform, manufacturer: str, version: str, device_type: DeviceType):
    """Safely returns a SoftwareVersion."""
    _image_file_name = f"{version}.bin"
    _status = Status.objects.get(name="Active")
    _software_version = ORMSoftwareVersion.objects.get_or_create(platform=platform, version=version, status=_status)[0]
    _software_image = ORMSoftwareImageFile.objects.get_or_create(
        software_version=_software_version, image_file_name=_image_file_name, status=_status
    )[0]
    _software_image.device_types.add(device_type)
    _software_image.validated_save()
    return _software_version


def ensure_location(
    location_data: dict,
    location_type: LocationType,
    parent_location_name: str = None,
    parent_location_type: LocationType = None,
):
    """Safely returns a Location."""
    # Get or create an Active status for locations
    status, _ = Status.objects.get_or_create(name="Active")

    # Extract location name and parent from location_data
    location_name = location_data.get("name")
    # Use parent from location_data if not provided as parameter
    if parent_location_name is None:
        parent_location_name = location_data.get("parent")

    # First, try to find existing location by name and location type
    # We need to handle parent relationships properly
    if parent_location_name:
        # For locations with a parent, we need to find the parent first
        parent_location_type = location_type.parent if location_type.parent else location_type
        try:
            parent_location = ORMLocation.objects.get(
                name__iexact=parent_location_name, location_type=parent_location_type
            )
        except ORMLocation.MultipleObjectsReturned:
            # If multiple parent locations with same name and type, use the first one
            parent_location = ORMLocation.objects.filter(
                name__iexact=parent_location_name, location_type=parent_location_type
            ).first()
        except ORMLocation.DoesNotExist:
            # Parent doesn't exist, we'll create it later
            parent_location = None

        # Now look for the location with the specific parent
        if parent_location:
            try:
                existing_location = ORMLocation.objects.get(
                    name__iexact=location_name, location_type=location_type, parent=parent_location
                )
                return existing_location
            except ORMLocation.DoesNotExist:
                pass
            except ORMLocation.MultipleObjectsReturned:
                # If multiple locations with same name, type, and parent, use the first one
                existing_location = ORMLocation.objects.filter(
                    name__iexact=location_name, location_type=location_type, parent=parent_location
                ).first()
                return existing_location
    else:
        # For root locations (no parent), look for locations with no parent
        try:
            existing_location = ORMLocation.objects.get(
                name__iexact=location_name, location_type=location_type, parent__isnull=True
            )
            return existing_location
        except ORMLocation.DoesNotExist:
            pass
        except ORMLocation.MultipleObjectsReturned:
            # If multiple root locations with same name and type, use the first one
            existing_location = ORMLocation.objects.filter(
                name__iexact=location_name, location_type=location_type, parent__isnull=True
            ).first()
            return existing_location

    # If no existing location found, create a new one
    if parent_location_name:
        # Use the parent_location we found earlier, or create it if it doesn't exist
        if "parent_location" not in locals() or parent_location is None:
            # Recursively ensure the parent location exists
            parent_location_data = {
                "name": parent_location_name,
                "parent": None,  # Parent locations don't have parents in this context
            }
            parent_location = ensure_location(location_data=parent_location_data, location_type=parent_location_type)

        _location = ORMLocation.objects.create(
            name=location_name, parent=parent_location, location_type=location_type, status=status
        )
    else:
        _location = ORMLocation.objects.create(name=location_name, location_type=location_type, status=status)
    return _location


class NautobotLocation(Location):
    """Nautobot implementation of LibreNMS Location model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Location in Nautobot from NautobotLocation object."""
        if adapter.job.debug:
            adapter.job.logger.debug(f'Creating Nautobot Location {ids["name"]}')

        # Check if location already exists to avoid ValidationError
        try:
            existing_location = ORMLocation.objects.get(name=ids["name"], parent__isnull=True)
            if adapter.job.debug:
                adapter.job.logger.debug(f'Location {ids["name"]} already exists, skipping creation')
            return None
        except ORMLocation.DoesNotExist:
            pass  # Location doesn't exist, proceed with creation
        except ORMLocation.MultipleObjectsReturned:
            adapter.job.logger.warning(f'Multiple locations found with name {ids["name"]}, using first one')
            existing_location = ORMLocation.objects.filter(name=ids["name"], parent__isnull=True).first()
            return existing_location

        try:
            if adapter.job.debug:
                adapter.job.logger.debug(f"Location Type {adapter.job.location_type}")
            _location_type = LocationType.objects.get(id=adapter.job.location_type.id)
        except LocationType.DoesNotExist:
            adapter.job.logger.warning(
                f"Location Type {adapter.job.location_type} does not exist. Using default Site Location Type."
            )
            _location_type = LocationType.objects.get(name="Site")

        new_location = ORMLocation(
            name=ids["name"],
            latitude=attrs["latitude"],
            longitude=attrs["longitude"],
            status=Status.objects.get(name=attrs["status"]),
            location_type=_location_type,
        )
        if adapter.tenant:
            new_location.tenant = adapter.tenant
        new_location.custom_field_data.update(
            {
                "system_of_record": os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS"),
                "last_synced_from_sor": datetime.today().date().isoformat(),
            }
        )
        new_location.validated_save()
        return None

    def update(self, attrs):
        """Update Location in Nautobot from NautobotLocation object."""
        if self.adapter.job.debug:
            self.adapter.job.logger.debug(f"Updating Nautobot Location {self.name}")

        # Build query based on parent relationship
        query_kwargs = {"name": self.name, "location_type": self.adapter.job.location_type}

        # Handle parent relationship properly
        if hasattr(self, "parent") and self.parent:
            # Find the parent location first
            try:
                parent_location = ORMLocation.objects.get(
                    name__iexact=self.parent, location_type=self.adapter.job.location_type.parent
                )
                query_kwargs["parent"] = parent_location
            except ORMLocation.MultipleObjectsReturned:
                parent_location = ORMLocation.objects.filter(
                    name__iexact=self.parent, location_type=self.adapter.job.location_type.parent
                ).first()
                query_kwargs["parent"] = parent_location
            except ORMLocation.DoesNotExist:
                self.adapter.job.logger.error(
                    f"Parent location {self.parent} not found for updating location {self.name}"
                )
                return None
        else:
            # Root location (no parent)
            query_kwargs["parent__isnull"] = True

        try:
            location = ORMLocation.objects.get(**query_kwargs)
        except ORMLocation.MultipleObjectsReturned:
            # If multiple locations with same criteria, use the first one
            location = ORMLocation.objects.filter(**query_kwargs).first()
        except ORMLocation.DoesNotExist:
            self.adapter.job.logger.error(
                f"Location {self.name} with type {self.adapter.job.location_type} not found for update"
            )
            return None
        if "latitude" in attrs:
            location.latitude = attrs["latitude"]
        if "longitude" in attrs:
            location.longitude = attrs["longitude"]
        if "status" in attrs:
            location.status = Status.objects.get(name=attrs["status"])
        custom_fields = {"last_synced_from_sor": datetime.today().date().isoformat()}
        if not check_sor_field(location):
            custom_fields["system_of_record"] = os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")
        location.custom_field_data.update(custom_fields)
        location.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Location in Nautobot from NautobotLocation object."""
        self.adapter.job.logger.debug(f"Deleting Nautobot Location {self.name}")
        try:
            location = ORMLocation.objects.get(id=self.uuid)
        except ORMLocation.MultipleObjectsReturned:
            # This shouldn't happen with UUID, but handle it just in case
            location = ORMLocation.objects.filter(id=self.uuid).first()
        except ORMLocation.DoesNotExist:
            self.adapter.job.logger.error(f"Location with UUID {self.uuid} not found for deletion")
            return self
        super().delete()
        location.delete()
        return self


class NautobotDevice(Device):
    """Nautobot implementation of LibreNMS Device model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Nautobot from NautobotDevice object."""
        if adapter.job.debug:
            adapter.job.logger.debug(f'Creating Nautobot Device {ids["name"]}')
            adapter.job.logger.debug(f"N_Model ids: {ids}")
        manufacturer_name = os_manufacturer_map.get(
            LIBRENMS_LIB_MAPPER_REVERSE.get(ANSIBLE_LIB_MAPPER.get(attrs["platform"], attrs["platform"])),
            attrs["platform"],
        )
        if manufacturer_name is None:
            raise ValueError(f"Manufacturer is required for device {ids['name']}")
        _manufacturer = ORMManufacturer.objects.get_or_create(name=manufacturer_name)[0]
        _platform = ensure_platform(platform_name=attrs["platform"], manufacturer=_manufacturer.name)
        adapter.job.logger.debug(f"Platform: {_platform}")
        _device_type = DeviceType.objects.get_or_create(model=attrs["device_type"], manufacturer=_manufacturer)[0]
        # Get location data from the device attributes
        location_name = attrs["location"]
        parent_location_name = attrs.get("parent_location")
        # Get IP address and prefix length from the device attributes
        ip_address = attrs.get("ip_address")
        ip_prefix = attrs.get("ip_prefix")
        _ipaddress = None  # Initialize to None
        if ip_address and ip_prefix:
            _ipaddress = ensure_ip_address(ip_address=ip_address, ip_prefix=ip_prefix, adapter=adapter)

        location_data = {"name": location_name, "parent": parent_location_name}
        _location = ensure_location(location_data=location_data, location_type=adapter.job.location_type)
        if adapter.job.debug:
            adapter.job.logger.debug(f'Device Location {attrs["location"]}')

        _tenant = adapter.tenant

        try:
            new_device = ORMDevice(
                name=ids["name"],
                device_type=_device_type,
                status=Status.objects.get(name=attrs["status"]),
                role=ensure_role(role_name=attrs["role"], content_type=ORMDevice),
                tenant=_tenant,
                location=_location,
                platform=_platform,
                serial=attrs["serial_no"],
                software_version=ensure_software_version(
                    platform=_platform,
                    manufacturer=_manufacturer.name,
                    version=attrs["os_version"],
                    device_type=_device_type,
                ),
            )
        except ORMLocation.DoesNotExist:
            adapter.job.logger.error(f"Location {attrs['location']} does not exist. Skipping device {ids['name']}.")
            return None
        custom_fields = {
            "librenms_device_id": attrs["device_id"],
            "system_of_record": os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS"),
            "last_synced_from_sor": datetime.today().date().isoformat(),
        }

        # Add SNMP location as custom field if available
        if attrs.get("snmp_location"):
            custom_fields["snmp_location"] = attrs["snmp_location"]

        new_device.custom_field_data.update(custom_fields)
        new_device.validated_save()

        # Set primary IP and interface after device is created and saved
        if _ipaddress:
            _interface = ensure_interface(interface_name="Management", device=new_device)
            # Create the IP address to interface relationship
            IPAddressToInterface.objects.get_or_create(
                ip_address=_ipaddress, interface=_interface, defaults={"vm_interface": None}
            )
            new_device.primary_ip4 = _ipaddress
            new_device.validated_save()

        # Remove tenant from attrs since we've already handled it
        attrs_copy = attrs.copy()
        attrs_copy.pop("tenant", None)
        return super().create(adapter=adapter, ids=ids, attrs=attrs_copy)

    def update(self, attrs):
        """Update Device in Nautobot from NautobotDevice object."""
        self.adapter.job.logger.debug(f"Updating Nautobot Device {self.name} with {attrs}")
        device = ORMDevice.objects.get(id=self.uuid)
        if "device_id" in attrs:
            device.custom_field_data["librenms_device_id"] = attrs["device_id"]
        if "status" in attrs:
            device.status = Status.objects.get_or_create(name=attrs["status"])[0]
        if "role" in attrs:
            device.role = ensure_role(role_name=attrs["role"], content_type=ORMDevice)
        if "location" in attrs:
            # Get location data from the device attributes
            location_name = attrs["location"]
            parent_location_name = attrs.get("parent_location")

            # Ensure the location exists with proper parent
            location_data = {"name": location_name, "parent": parent_location_name}
            _location = ensure_location(location_data=location_data, location_type=self.adapter.job.location_type)
            device.location = _location
        if "serial_no" in attrs:
            device.serial = attrs["serial_no"]
        if "platform" in attrs:
            # Get the original OS name for manufacturer lookup
            if self.adapter.job.debug:
                self.adapter.job.logger.debug(f"N_Model attrs: {attrs}")
            if self.adapter.job.debug:
                self.adapter.job.logger.debug(f"N_ModelManufacturer for {self.name} from attrs: {self.manufacturer}")
            _platform = ensure_platform(platform_name=attrs["platform"], manufacturer=self.manufacturer)
            device.platform = _platform
        if "os_version" in attrs:
            _software_version = ensure_software_version(
                platform=_platform,
                manufacturer=self.manufacturer.name,
                version=attrs["os_version"],
                device_type=device.device_type,
            )
            _software_version.devices.add(device)

        ip_address = attrs.get("ip_address")
        ip_prefix = attrs.get("ip_prefix")
        if ip_address and ip_prefix:
            _ipaddress = ensure_ip_address(ip_address=ip_address, ip_prefix=ip_prefix, adapter=self.adapter)
            _interface = ensure_interface(interface_name="Management", device=device)
            IPAddressToInterface.objects.get_or_create(
                ip_address=_ipaddress, interface=_interface, defaults={"vm_interface": None}
            )
            device.primary_ip4 = _ipaddress
        custom_fields = {"last_synced_from_sor": datetime.today().date().isoformat()}
        if not check_sor_field(device):
            custom_fields["system_of_record"] = os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")

        # Add SNMP location as custom field if available
        if attrs.get("snmp_location"):
            custom_fields["snmp_location"] = attrs["snmp_location"]

        device.custom_field_data.update(custom_fields)
        device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Device in Nautobot from NautobotDevice object."""
        self.adapter.job.logger.debug(f"Deleting Nautobot Device {self.name}")
        dev = ORMDevice.objects.get(id=self.uuid)
        super().delete()
        dev.delete()
        return self


class NautobotPort(Port):
    """Nautobot implementation of LibreNMS Port model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Port in Nautobot from NautobotPort object."""
        raise NotImplementedError("NautobotPort create not yet implemented")
        adapter.job.logger.debug(f'Creating Nautobot Interface {ids["name"]}')

        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Port in Nautobot from NautobotPort object."""
        raise NotImplementedError("NautobotPort update not yet implemented")
        self.adapter.job.logger.debug(f"Updating Nautobot Interface {self.name}")

        return super().update(attrs)

    def delete(self):
        """Delete Port in Nautobot from NautobotPort object."""
        raise NotImplementedError("NautobotPort delete not yet implemented")
        self.adapter.job.logger.debug(f"Deleting Nautobot Interface {self.name}")

        port = ORMInterface.objects.get(id=self.uuid)
        super().delete()
        port.delete()
        return self
