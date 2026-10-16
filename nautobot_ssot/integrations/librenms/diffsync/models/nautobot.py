"""Nautobot DiffSync models for LibreNMS SSoT."""

import os
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
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
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER, ANSIBLE_LIB_MAPPER_REVERSE

from nautobot_ssot.integrations.librenms.constants import LIBRENMS_OS_TO_NETWORK_DRIVER
from nautobot_ssot.integrations.librenms.diffsync.models.base import Device, Location, Port
from nautobot_ssot.integrations.librenms.utils import check_sor_field
from nautobot_ssot.integrations.librenms.utils.nautobot import librenms_os_to_network_driver


def ensure_ip_address(ip_address: str, ip_prefix: str, adapter: object):
    """Safely returns an IPAddress."""
    # Tenant is optional; without one, IPs live in the default Global namespace.
    _namespace_name = adapter.job.tenant.name if adapter.job.tenant else "Global"
    _namespace = Namespace.objects.get_or_create(name=_namespace_name)[0]
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


def consolidated_platforms_enabled(adapter) -> bool:
    """Platform-naming mode stashed on the adapter. Defaults to legacy."""
    return bool(getattr(adapter, "consolidated_platforms", False))


def legacy_network_driver(platform_name: str) -> str:
    """Valid network driver for a legacy FQCN- or raw-OS-named Platform."""
    # Derived from the name, not the raw OS: legacy naming collapses ios and iosxe onto one
    # cisco.ios.ios row, so using the raw OS would make the driver depend on processing order.
    return ANSIBLE_LIB_MAPPER.get(platform_name) or librenms_os_to_network_driver(platform_name)


def _legacy_alias_names(driver: str) -> list:
    """Platform names legacy naming would have used for this driver."""
    names = []
    # FQCN only counts if it maps back to this driver; else cisco_xe would steal cisco.ios.ios.
    fqcn = ANSIBLE_LIB_MAPPER_REVERSE.get(driver)
    if fqcn and ANSIBLE_LIB_MAPPER.get(fqcn) == driver:
        names.append(fqcn)
    names.extend(
        librenms_os
        for librenms_os, mapped in LIBRENMS_OS_TO_NETWORK_DRIVER.items()
        if mapped == driver and librenms_os != driver
    )
    return names


def _platform_manufacturer_conflicts(platform, manufacturer) -> bool:
    """Whether reusing this Platform would contradict the device's Manufacturer."""
    return platform.manufacturer_id is not None and platform.manufacturer_id != manufacturer.pk


def _resolve_platform_by_driver(driver: str, manufacturer, logger=None):
    """Existing Platform for this network driver, or None."""
    # filter() + ranking, never get(): duplicate drivers are a legitimate intermediate state.
    candidates = list(ORMPlatform.objects.filter(network_driver__iexact=driver))
    if not candidates:
        return None

    usable = [platform for platform in candidates if not _platform_manufacturer_conflicts(platform, manufacturer)]
    if logger:
        for platform in candidates:
            if _platform_manufacturer_conflicts(platform, manufacturer):
                logger.warning(
                    f'Not reusing Platform "{platform.name}" for network driver "{driver}": its Manufacturer '
                    f'"{platform.manufacturer}" conflicts with "{manufacturer.name}".'
                )
    if not usable:
        return None

    # Exact name, then matching manufacturer, then null; name breaks ties for determinism.
    usable.sort(
        key=lambda platform: (platform.name != driver, platform.manufacturer_id != manufacturer.pk, platform.name)
    )
    chosen = usable[0]
    if len(usable) > 1 and logger:
        logger.warning(
            f'Multiple Platforms share network driver "{driver}" '
            f"({', '.join(sorted(platform.name for platform in usable))}). Using \"{chosen.name}\". "
            "Run the LibreNMS Platform Consolidation job to merge them."
        )
    return chosen


def _adopt_legacy_platform(driver: str, manufacturer, logger=None):
    """Adopt a legacy-named Platform for this driver, in place."""
    # Never renames or rewrites network_driver -- that is the consolidation job's job. This is
    # what makes enabling librenms_consolidated_platforms a non-event for existing data.
    for name in _legacy_alias_names(driver):
        # order_by so a case-only duplicate resolves the same way every run.
        platform = ORMPlatform.objects.filter(name__iexact=name).order_by("name").first()
        if platform is None:
            continue
        existing_driver = (platform.network_driver or "").strip()
        # Only claim a row that nobody else has staked a driver on.
        if existing_driver and existing_driver != platform.name:
            continue
        if _platform_manufacturer_conflicts(platform, manufacturer):
            continue
        if logger:
            logger.info(
                f'Adopting existing Platform "{platform.name}" for network driver "{driver}" without renaming it.'
            )
        return platform
    return None


def ensure_platform(platform_name: str, manufacturer: str, adapter=None):
    """Safely returns a Platform that supports Devices.

    Legacy mode names Platforms after the Ansible FQCN; consolidated mode after the network
    driver, shared with device-onboarding. Both modes give new Platforms a valid network_driver.
    Existing Platforms are never renamed, and a disagreeing driver is never overwritten.

    Args:
        platform_name (str): FQCN in legacy mode; driver, or raw OS with no driver, in consolidated.
        manufacturer (str): Name of the device's Manufacturer.
        adapter (object, optional): Read for the mode and the job logger.

    Returns:
        Platform: Found, adopted or created Platform.
    """
    _manufacturer, _ = ORMManufacturer.objects.get_or_create(name=manufacturer)
    logger = getattr(getattr(adapter, "job", None), "logger", None)

    if not consolidated_platforms_enabled(adapter):
        _platform, _ = ORMPlatform.objects.get_or_create(
            name=platform_name,
            defaults={"network_driver": legacy_network_driver(platform_name), "manufacturer": _manufacturer},
        )
        return _platform

    # Already driver-space; resolution is idempotent. "" for a raw OS with no known driver.
    driver = librenms_os_to_network_driver(platform_name)

    if driver:
        _platform = _resolve_platform_by_driver(driver, _manufacturer, logger)
        if _platform is not None:
            return _platform
        _platform = _adopt_legacy_platform(driver, _manufacturer, logger)
        if _platform is not None:
            return _platform

    _platform, created = ORMPlatform.objects.get_or_create(
        name=driver or platform_name,
        defaults={"network_driver": driver, "manufacturer": _manufacturer},
    )
    # Self-heal an operator row named like the driver but missing it. Never overwrite a
    # disagreeing driver -- that is the consolidation job's decision.
    if not created and driver and not (_platform.network_driver or "").strip() and _platform.name == driver:
        _platform.network_driver = driver
        _platform.validated_save()
        if logger:
            logger.info(f'Set network driver "{driver}" on existing Platform "{_platform.name}".')
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

        new_location = ORMLocation(
            name=ids["name"],
            latitude=attrs["latitude"],
            longitude=attrs["longitude"],
            status=Status.objects.get(name=attrs["status"]),
            location_type=adapter.job.location_type,
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
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

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
            return None
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
        # Adapter already resolved this from the raw OS and has_required_values() guarantees it,
        # so use it directly instead of round-tripping the platform name through the OS mappers.
        manufacturer_name = attrs["manufacturer"]
        if not manufacturer_name:
            raise ValueError(f"Manufacturer is required for device {ids['name']}")
        _manufacturer = ORMManufacturer.objects.get_or_create(name=manufacturer_name)[0]
        _platform = ensure_platform(platform_name=attrs["platform"], manufacturer=_manufacturer.name, adapter=adapter)
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
        _secrets_group = getattr(adapter.job, "device_secrets_group", None)

        try:
            new_device = ORMDevice(
                name=ids["name"],
                device_type=_device_type,
                status=Status.objects.get(name=attrs["status"]),
                role=ensure_role(role_name=attrs["role"], content_type=ORMDevice),
                tenant=_tenant,
                secrets_group=_secrets_group,
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
        try:
            new_device.validated_save()
        except ValidationError as err:
            # Consolidated mode reuses Platforms from other apps, so Device.clean()'s
            # platform/device_type manufacturer check can fire on data we didn't create.
            # Skip the device instead of aborting the job.
            adapter.job.logger.error(f"Failed to create device {ids['name']}: {err}")
            return None

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
        if "location" in attrs and self.adapter.job.sync_locations:
            # Get location data from the device attributes
            location_name = attrs["location"]
            parent_location_name = attrs.get("parent_location")

            # Ensure the location exists with proper parent
            location_data = {"name": location_name, "parent": parent_location_name}
            _location = ensure_location(location_data=location_data, location_type=self.adapter.job.location_type)
            device.location = _location
        if "serial_no" in attrs:
            device.serial = attrs["serial_no"]
        _platform_changed = False
        if "platform" in attrs:
            # Get the original OS name for manufacturer lookup
            if self.adapter.job.debug:
                self.adapter.job.logger.debug(f"N_Model attrs: {attrs}")
            if self.adapter.job.debug:
                self.adapter.job.logger.debug(f"N_ModelManufacturer for {self.name} from attrs: {self.manufacturer}")
            _platform = ensure_platform(
                platform_name=attrs["platform"], manufacturer=self.manufacturer, adapter=self.adapter
            )
            _platform_changed = device.platform_id != _platform.pk
            if _platform_changed:
                self.adapter.job.logger.info(
                    f"Moving device {self.name} from Platform "
                    f'"{device.platform.name if device.platform else None}" to "{_platform.name}".'
                )
            device.platform = _platform
        if "os_version" in attrs:
            _software_version = ensure_software_version(
                platform=device.platform,
                manufacturer=self.manufacturer,
                version=attrs["os_version"],
                device_type=device.device_type,
            )
            _software_version.devices.add(device)
        elif _platform_changed and self.os_version:
            # Platform moved but version didn't; otherwise the device keeps pointing at a
            # SoftwareVersion belonging to the old Platform.
            _software_version = ensure_software_version(
                platform=device.platform,
                manufacturer=self.manufacturer,
                version=self.os_version,
                device_type=device.device_type,
            )
            device.software_version = _software_version

        ip_address = attrs.get("ip_address")
        ip_prefix = attrs.get("ip_prefix")
        if ip_address and ip_prefix:
            _ipaddress = ensure_ip_address(ip_address=ip_address, ip_prefix=ip_prefix, adapter=self.adapter)
            _interface = ensure_interface(interface_name="Management", device=device)
            IPAddressToInterface.objects.get_or_create(
                ip_address=_ipaddress, interface=_interface, defaults={"vm_interface": None}
            )
            device.primary_ip4 = _ipaddress

        # Only backfill the Secrets Group, never overwrite one assigned by hand or by another job.
        if not device.secrets_group:
            _secrets_group = getattr(self.adapter.job, "device_secrets_group", None)
            if _secrets_group:
                device.secrets_group = _secrets_group

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
