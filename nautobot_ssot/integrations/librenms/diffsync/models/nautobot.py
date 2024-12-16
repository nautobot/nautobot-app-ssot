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

from nautobot_ssot.integrations.librenms.constants import os_manufacturer_map
from nautobot_ssot.integrations.librenms.diffsync.models.base import Device, Location, Port
from nautobot_ssot.integrations.librenms.utils import check_sor_field, get_city_state_geocode
from nautobot_ssot.integrations.librenms.utils.nautobot import (
    verify_platform,
)


def ensure_location(location_name: str, content_type, parent, location_type_name: str = "Site"):
    """Safely returns a Location with a LocationType that support given ContentType."""
    location_type, _ = LocationType.objects.get_or_create(name=location_type_name)
    content_type = ContentType.objects.get_for_model(content_type)
    location_type.content_types.add(content_type)
    status = Status.objects.get(name="Active")
    if parent:
        parent, _ = LocationType.objects.get_or_create(name=parent.name)
        return ORMLocation.objects.get_or_create(name=location_name, location_type=location_type, status=status)[0]
    else:
        return ORMLocation.objects.get_or_create(name=location_name, location_type=location_type, status=status)[0]


def ensure_role(role_name: str, content_type):
    """Safely returns a Role that support given ContentType."""
    content_type = ContentType.objects.get_for_model(content_type)
    role, _ = Role.objects.get_or_create(name=role_name)
    role.content_types.add(content_type)
    return role


def ensure_platform(platform_name: str, manufacturer: str):
    """Safely returns a Platform that support Devices."""
    try:
        _manufacturer = ORMManufacturer.objects.get_or_create(name=manufacturer)[0]
        _platform = ORMPlatform.objects.get(name=platform_name, manufacturer=_manufacturer)
        return _platform
    except ORMPlatform.DoesNotExist:
        _platform = verify_platform(platform_name=platform_name, manu=_manufacturer.id)
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


class NautobotLocation(Location):
    """Nautobot implementation of LibreNMS Location model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Location in Nautobot from NautobotLocation object."""
        if adapter.job.debug:
            adapter.job.logger.debug(f'Creating Nautobot Location {ids["name"]}')

        _unknown_parent = ensure_location(location_name="Unknown", content_type=ORMDevice, parent=None, location_type_name="City")

        if adapter.job.sync_location_parents:
            if "latitude" in attrs and "longitude" in attrs:
                if attrs["latitude"] is not None and attrs["longitude"] is not None:
                    _location_info = get_city_state_geocode(latitude=attrs["latitude"], longitude=attrs["longitude"])
                    if _location_info:
                        _state = ensure_location(location_name=_location_info["state"], content_type=ORMDevice, parent=None, location_type_name="State")
                        _city = ensure_location(
                            location_name=_location_info["city"], content_type=ORMDevice, parent=_state, location_type_name="City"
                        )
                        _parent = _city

        _parent = _unknown_parent

        new_location = ORMLocation(
            name=ids["name"],
            latitude=attrs["latitude"],
            longitude=attrs["longitude"],
            status=Status.objects.get(name=attrs["status"]),
            location_type=LocationType.objects.get(name="Site"),
            parent=_parent,
        )
        new_location.custom_field_data.update(
            {"system_of_record": os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")}
        )
        new_location.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_location.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Location in Nautobot from NautobotLocation object."""
        if self.adapter.job.debug:
            self.adapter.job.logger.debug(f"Updating Nautobot Location {self.name}")

        location = ORMLocation.objects.get(name=self.name)
        if "latitude" in attrs:
            location.latitude = attrs["latitude"]
        if "longitude" in attrs:
            location.longitude = attrs["longitude"]
        if "status" in attrs:
            location.status = Status.objects.get(name=attrs["status"])
        if "parent" in attrs and location.parent.name != "Unknown":
            location.parent = ensure_location(
                location_name=attrs["parent"], content_type=ORMDevice, location_type_name="City"
            )
        if not check_sor_field(location):
            location.custom_field_data.update(
                {"system_of_record": os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")}
            )
        location.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        location.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Location in Nautobot from NautobotLocation object."""
        self.adapter.job.logger.debug(f"Deleting Nautobot Location {self.name}")
        location = ORMLocation.objects.get(id=self.id)
        super().delete()
        location.delete()
        return self


class NautobotDevice(Device):
    """Nautobot implementation of LibreNMS Device model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Nautobot from NautobotDevice object."""
        adapter.job.logger.debug(f'Creating Nautobot Device {ids["name"]}')
        _manufacturer = ORMManufacturer.objects.get_or_create(name=os_manufacturer_map[attrs["platform"]])[0]
        _platform = ensure_platform(platform_name=attrs["platform"], manufacturer=_manufacturer.name)
        _device_type = DeviceType.objects.get_or_create(model=attrs["device_type"], manufacturer=_manufacturer)[0]
        new_device = ORMDevice(
            name=ids["name"],
            device_type=_device_type,
            status=Status.objects.get_or_create(name=attrs["status"])[0],
            role=ensure_role(role_name=attrs["role"], content_type=ORMDevice),
            location=ORMLocation.objects.get(name=attrs["location"]),
            platform=_platform,
            serial=attrs["serial_no"],
            software_version=ensure_software_version(
                platform=_platform,
                manufacturer=_manufacturer.name,
                version=attrs["os_version"],
                device_type=_device_type,
            ),
        )
        new_device.custom_field_data.update(
            {"system_of_record": os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")}
        )
        new_device.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_device.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in Nautobot from NautobotDevice object."""
        self.adapter.job.logger.debug(f"Updating Nautobot Device {self.name} with {attrs}")
        device = ORMDevice.objects.get(id=self.uuid)
        if "status" in attrs:
            device.status = Status.objects.get_or_create(name=attrs["status"])[0]
        if "role" in attrs:
            device.role = ensure_role(role_name=attrs["role"], content_type=ORMDevice)
        if "location" in attrs:
            device.location = ORMLocation.objects.get(name=attrs["location"])
        if "serial_no" in attrs:
            device.serial = attrs["serial_no"]
        if "platform" in attrs:
            _manufacturer = ORMManufacturer.objects.get_or_create(name=os_manufacturer_map[attrs["os"]])[0]
            device.platform = (ensure_platform(platform_name=attrs["os"], manufacturer=_manufacturer.name),)
        if "os_version" in attrs:
            _software_version = ensure_software_version(
                platform=device.platform,
                manufacturer=device.platform.manufacturer.name,
                version=attrs["os_version"],
                device_type=device.device_type,
            )
            _software_version.devices.add(device)
        if not check_sor_field(device):
            device.custom_field_data.update(
                {"system_of_record": os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")}
            )
        device.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
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
        adapter.job.logger.debug(f'Creating Nautobot Interface {ids["name"]}')

        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Port in Nautobot from NautobotPort object."""
        self.adapter.job.logger.debug(f"Updating Nautobot Interface {self.name}")

        return super().update(attrs)

    def delete(self):
        """Delete Port in Nautobot from NautobotPort object."""
        self.adapter.job.logger.debug(f"Deleting Nautobot Interface {self.name}")

        port = ORMInterface.objects.get(id=self.uuid)
        super().delete()
        port.delete()
        return self
