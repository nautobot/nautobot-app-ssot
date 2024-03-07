# pylint: disable=duplicate-code
# Ignore return statements for updates and deletes, #  pylint:disable=R1710
# Ignore too many args #  pylint:disable=too-many-locals
"""DiffSyncModel subclasses for Nautobot-to-IPFabric data sync."""
from typing import Any, ClassVar, List, Optional
from uuid import UUID
import logging

from netutils.ip import netmask_to_cidr

from diffsync import DiffSyncModel
from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from django.db.models import Q
from nautobot.dcim.models import (
    Device as NautobotDevice,
    DeviceType,
    Interface as NautobotInterface,
    Location as NautobotLocation,
    Manufacturer,
    VirtualChassis,
)
from nautobot.extras.models import Role, Tag
from nautobot.extras.models.statuses import Status
from nautobot.ipam.models import VLAN, IPAddress
from nautobot.core.choices import ColorChoices
from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME
import nautobot_ssot.integrations.ipfabric.utilities.nbutils as tonb_nbutils
from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_ROLE_COLOR,
    DEFAULT_DEVICE_STATUS,
    DEFAULT_DEVICE_STATUS_COLOR,
    DEFAULT_INTERFACE_MAC,
    SAFE_DELETE_LOCATION_STATUS,
    SAFE_DELETE_DEVICE_STATUS,
    SAFE_DELETE_IPADDRESS_STATUS,
    SAFE_DELETE_VLAN_STATUS,
)


logger = logging.getLogger(__name__)


# pylint: disable=too-many-branches,too-many-statements
class DiffSyncExtras(DiffSyncModel):
    """Additional components to mix and subclass from with `DiffSyncModel`."""

    safe_delete_mode: ClassVar[bool] = True

    def safe_delete(self, nautobot_object: Any, safe_delete_status: Optional[str] = None):
        """Safe delete an object, by adding tags or changing it's default status.

        Args:
            nautobot_object (Any): Any type of Nautobot object
            safe_delete_status (Optional[str], optional): Status name, optional as some objects don't have status field. Defaults to None.
        """
        update = False
        if not self.safe_delete_mode:  # This could just check self, refactor.
            logger.warning(f"{nautobot_object} will be deleted as safe delete mode is not enabled.")
            # This allows private class naming of nautobot objects to be ordered for delete()
            # Example definition in adapter class var: _site = Location
            self.diffsync.objects_to_delete[f"_{nautobot_object.__class__.__name__.lower()}"].append(
                nautobot_object
            )  # pylint: disable=protected-access
            super().delete()
        else:
            if safe_delete_status:
                safe_delete_status = Status.objects.get(name=safe_delete_status.capitalize())
                if hasattr(nautobot_object, "status"):
                    if not nautobot_object.status == safe_delete_status:
                        nautobot_object.status = safe_delete_status
                        logger.warning(f"{nautobot_object} has changed status to {safe_delete_status}.")
                        update = True
                else:
                    # Not everything has a status. This may come in handy once more models are synced.
                    logger.warning(f"{nautobot_object} has no Status attribute.")
            if hasattr(nautobot_object, "tags"):
                ssot_safe_tag, _ = Tag.objects.get_or_create(
                    name="SSoT Safe Delete",
                    defaults={
                        "description": "Safe Delete Mode tag to flag an object, but not delete from Nautobot.",
                        "color": ColorChoices.COLOR_RED,
                    },
                )
                object_tags = nautobot_object.tags.all()
                # No exception raised for empty iterator, safe to do this any
                if not any(obj_tag for obj_tag in object_tags if obj_tag.name == ssot_safe_tag.name):
                    nautobot_object.tags.add(ssot_safe_tag)
                    logger.warning(f"Tagging {nautobot_object} with `SSoT Safe Delete`.")
                    update = True
            if update:
                tonb_nbutils.tag_object(nautobot_object=nautobot_object, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            else:
                logger.warning(f"{nautobot_object} has previously been tagged with `SSoT Safe Delete`. Skipping...")

        return self


class Location(DiffSyncExtras):
    """Location model."""

    _modelname = "location"
    _identifiers = ("name",)
    _attributes = ("site_id", "status")
    _children = {"device": "devices", "vlan": "vlans"}

    name: str
    site_id: Optional[str]
    status: str
    devices: List["Device"] = list()  # pylint: disable=use-list-literal
    vlans: List["Vlan"] = list()  # pylint: disable=use-list-literal

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Location in Nautobot."""
        location = tonb_nbutils.create_location(
            location_name=ids["name"],
            location_id=attrs["site_id"],
            logger=diffsync.job.logger,
        )
        if location:
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        return None

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete Location in Nautobot."""
        try:
            location = NautobotLocation.objects.get(name=self.name)
        except NautobotLocation.MultipleObjectsReturned:
            self.diffsync.job.logger.error(
                f"Multiple Locations found with the name {self.name}, unable to determine which one to delete"
            )
        except NautobotLocation.DoesNotExist:
            self.diffsync.job.logger.error(f"Unable to find a Location with the name {self.name} to delete")
        else:
            self.safe_delete(
                location,
                SAFE_DELETE_LOCATION_STATUS,
            )
            return super().delete()
        return None

    def update(self, attrs):
        """Update Location Object in Nautobot."""
        try:
            location = NautobotLocation.objects.get(name=self.name)
        except NautobotLocation.MultipleObjectsReturned:
            self.diffsync.job.logger.error(
                f"Multiple Locations found with the name {self.name}, unable to determine which one to update"
            )
        except NautobotLocation.DoesNotExist:
            self.diffsync.job.logger.error(f"Unable to find a Location with the name {self.name} to update")
        else:
            site_id = attrs.get("site_id")
            if site_id:
                location.custom_field_data["ipfabric_site_id"] = site_id
            active_status = attrs.get("status")
            if active_status == "Active":
                safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
                if not location.status == active_status:
                    location.status = Status.objects.get(name=active_status)
                device_tags = location.tags.filter(pk=safe_delete_tag.pk)
                if device_tags.exists():
                    location.tags.remove(safe_delete_tag)
            try:
                # Calls validated_save() on the object
                tonb_nbutils.tag_object(nautobot_object=location, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError):
                self.diffsync.job.logger.error(f"Unable to update the existing Location named {self.name} with {attrs}")
            else:
                return super().update(attrs)
        return None


class Device(DiffSyncExtras):
    """Device model."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "location_name",
        "model",
        "vendor",
        "serial_number",
        "role",
        "status",
        "platform",
        "vc_name",
        "vc_priority",
        "vc_position",
        "vc_master",
    )
    _children = {"interface": "interfaces"}

    name: str
    location_name: Optional[str]
    model: Optional[str]
    vendor: Optional[str]
    serial_number: Optional[str]
    role: Optional[str]
    status: Optional[str]
    platform: Optional[str]
    vc_name: Optional[str]
    vc_priority: Optional[int]
    vc_position: Optional[int]
    vc_master: Optional[bool]

    mgmt_address: Optional[str]

    interfaces: List["Interface"] = list()  # pylint: disable=use-list-literal

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device in Nautobot under its parent location."""
        # Get DeviceType
        device_name = ids["name"]
        device_type_name = attrs["model"]
        device_type_filter = DeviceType.objects.filter(model=device_type_name)
        if device_type_filter.exists():
            device_type_object = device_type_filter.first()
        else:
            vendor_name = attrs["vendor"]
            device_type_object = tonb_nbutils.create_device_type_object(
                device_type=device_type_name,
                vendor_name=vendor_name,
                logger=diffsync.job.logger,
            )
            if not device_type_object:
                diffsync.job.logger.warning(
                    f"Unable to create a Device with the name {device_name} because of a failure "
                    f"to get or create a DeviceType named {device_type_name} with a Manufacturer named {vendor_name}"
                )
        # Get Platform
        platform = attrs.get("platform")
        if platform and device_type_object:
            platform_object = tonb_nbutils.create_platform_object(
                platform=platform,
                manufacturer_obj=device_type_object.manufacturer,
                logger=diffsync.job.logger,
            )
            if not platform_object:
                diffsync.job.logger.warning(
                    f"Unable to get or create a Platform named {platform}, "
                    f"Device named {device_name} will not have a Platform assigned"
                )
        elif platform:
            diffsync.job.logger.warning(
                f"Unable to get or create a Platform named {platform} since the DeviceType could not be retrieved, "
                f"Device named {device_name} will not have a Platform assigned"
            )
        else:
            platform_object = None

        # Get Role, update if missing cf and create otherwise
        role_name = attrs.get("role", DEFAULT_DEVICE_ROLE)
        device_role_filter = Role.objects.filter(name=role_name)
        if device_role_filter.exists():
            device_role_object = device_role_filter.first()
            device_role_object.cf["ipfabric_type"] = role_name
            try:
                device_role_object.validated_save()
            except (DjangoBaseDBError, ValidationError):
                diffsync.job.logger.error(
                    f"Unable to perform a validated_save() on Role {role_name} with an ID of {device_role_object.id}"
                )
        else:
            device_role_object = tonb_nbutils.get_or_create_device_role_object(
                role_name=role_name,
                role_color=DEFAULT_DEVICE_ROLE_COLOR,
                logger=diffsync.job.logger,
            )
            if not device_role_object:
                diffsync.job.logger.warning(
                    f"Unable to create a Device with the name {device_name} because of a failure "
                    f"to get or create a Role named {role_name}"
                )
        # Get Status
        device_status_filter = Status.objects.filter(name=DEFAULT_DEVICE_STATUS)
        if device_status_filter.exists():
            device_status_object = device_status_filter.first()
        else:
            device_status_object = tonb_nbutils.create_status(
                DEFAULT_DEVICE_STATUS,
                DEFAULT_DEVICE_STATUS_COLOR,
                logger=diffsync.job.logger,
            )
            if not device_status_object:
                diffsync.job.logger.warning(
                    f"Unable to create a Device with the name {device_name} because of a failure "
                    f"to get or create a Status named {DEFAULT_DEVICE_STATUS}"
                )
        # Get Location
        location_name = attrs["location_name"]
        location_object_filter = NautobotLocation.objects.filter(name=location_name)
        if location_object_filter.exists():
            location_object = location_object_filter.first()
        else:
            location_object = tonb_nbutils.create_location(location_name, logger=diffsync.job.logger)
            if not location_object:
                diffsync.job.logger.warning(
                    f"Unable to create Device with name {device_name} because of a failure "
                    f"to get or create a Location named {location_name}"
                )

        if device_type_object and location_object and device_role_object and device_status_object:
            try:
                new_device, _ = NautobotDevice.objects.get_or_create(
                    name=device_name,
                    serial=attrs.get("serial_number", ""),
                    status=device_status_object,
                    device_type=device_type_object,
                    role=device_role_object,
                    location=location_object,
                    defaults={"platform": platform_object},
                )
            except NautobotDevice.MultipleObjectsReturned:
                diffsync.job.logger.error(
                    f"Multiple Devices returned with name {device_name} at Location {location_name}"
                )
            except (DjangoBaseDBError, ValidationError):
                diffsync.job.logger.error(
                    f"Unable to create a new Device named {device_name} at Location {location_name}"
                )
            else:
                try:
                    # Validated save happens inside of tag_objet
                    tonb_nbutils.tag_object(nautobot_object=new_device, custom_field=LAST_SYNCHRONIZED_CF_NAME)
                except (DjangoBaseDBError, ValidationError) as error:
                    diffsync.job.logger.error(
                        f"Unable to perform a validated_save() on Device {device_name} with an ID of {new_device.id}"
                    )
                    message = f"Unable to create device: {device_name}. A validation error occured. Enable debug for more information."
                    if diffsync.job.debug:
                        logger.debug(error)
                    logger.error(message)

                vc_name = attrs.get("vc_name")
                if vc_name:
                    vc_master = attrs.get("vc_master", False)
                    vc_position = attrs.get("vc_position")
                    vc_priority = attrs.get("vc_priority")
                    try:
                        cls._get_or_create_virtual_chassis(
                            vc_name, new_device, diffsync.job.logger, vc_master, vc_position, vc_priority
                        )
                    except (DjangoBaseDBError, ValidationError):
                        diffsync.job.logger.error(
                            f"Unable to update Device {device_name} with an ID of {new_device.id} with VirtualChassis data"
                        )
                    else:
                        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        return None

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete device in Nautobot."""
        try:
            device_object = NautobotDevice.objects.get(name=self.name)
        except NautobotDevice.MultipleObjectsReturned:
            self.diffsync.job.logger.error(
                f"Multiple Devices found with the name {self.name}, unable to determine which one to delete"
            )
        except NautobotDevice.DoesNotExist:
            self.diffsync.job.logger.error(f"Unable to find a Device with the name {self.name} to delete")
        else:
            self.safe_delete(
                device_object,
                SAFE_DELETE_DEVICE_STATUS,
            )
            return super().delete()
        return None

    def update(self, attrs):
        """Update devices in Nautobot based on Source."""
        try:
            _device = NautobotDevice.objects.get(name=self.name)
        except NautobotDevice.MultipleObjectsReturned:
            self.diffsync.job.logger.error(
                f"Multiple Devices found with the name {self.name}, unable to determine which one to update"
            )
        except NautobotDevice.DoesNotExist:
            self.diffsync.job.logger.error(f"Unable to find a Device with the name {self.name} to update")
        else:
            return_super = True
            if attrs.get("status") == "Active":
                safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
                if not _device.status == "Active":
                    _device.status = Status.objects.get(name="Active")
                device_tags = _device.tags.filter(pk=safe_delete_tag.pk)
                if device_tags.exists():
                    _device.tags.remove(safe_delete_tag)

            vendor_name = attrs.get("vendor") or self.vendor
            device_type_name = attrs.get("model")
            if device_type_name:
                device_type_object = tonb_nbutils.create_device_type_object(
                    device_type=device_type_name,
                    vendor_name=vendor_name,
                    logger=self.diffsync.job.logger,
                )
                if device_type_object:
                    _device.type = device_type_object
                else:
                    self.diffsync.job.logger.warning(
                        f"Unable to update Device {self.name} with a DeviceType of {device_type_name}"
                    )
                    return_super = False
            platform_name = attrs.get("platform")
            if platform_name:
                try:
                    manufacturer_object = Manufacturer.objects.get(name=vendor_name)
                except Manufacturer.MultipleObjectsReturned:
                    self.diffsync.job.logger.error(
                        f"Multiple Manufacturers found with the name {vendor_name}, "
                        f"unable to get or create a Platform named {platform_name} for Device named {self.name}"
                    )
                    return_super = False
                except Manufacturer.DoesNotExist:
                    self.diffsync.job.logger.error(
                        f"Could not find a Manufacturer with the name {vendor_name}, "
                        f"unable to get or create a Platform named {platform_name} for Device named {self.name}"
                    )
                    return_super = False
                else:
                    platform_object = tonb_nbutils.create_platform_object(
                        platform=platform_name,
                        manufacturer_obj=manufacturer_object,
                        logger=self.diffsync.job.logger,
                    )
                    if platform_object:
                        _device.platform = platform_object
                    else:
                        self.diffsync.job.logger.warning(
                            f"Unable to update Device {self.name} with a Platform of {platform_name}"
                        )
                        return_super = False

            location_name = attrs.get("location_name")
            if location_name:
                location = tonb_nbutils.create_location(location_name, logger=self.diffsync.job.logger)
                if location:
                    _device.location = location
                else:
                    self.diffsync.job.logger.warning(
                        f"Unable to update Device {self.name} with a Location named {location_name}"
                    )
                    return_super = False
            if attrs.get("serial_number"):
                _device.serial = attrs.get("serial_number")
            role_name = attrs.get("role")
            if role_name:
                device_role_object = tonb_nbutils.get_or_create_device_role_object(
                    role_name=role_name,
                    role_color=DEFAULT_DEVICE_ROLE_COLOR,
                    logger=self.diffsync.job.logger,
                )
                if device_role_object:
                    _device.role = device_role_object
                else:
                    self.diffsync.job.logger.warning(
                        f"Unable to update Device {self.name} with a Role named {role_name}"
                    )
                    return_super = False
            # tonb_nbutils.tag_object calls validated_save()
            try:
                tonb_nbutils.tag_object(nautobot_object=_device, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError):
                self.diffsync.job.logger.error(f"Unable to update the existing Device named {self.name} with {attrs}")
                return_super = False

            vc_name = attrs.get("vc_name")
            vc_master = attrs.get("vc_master", False)
            vc_position = attrs.get("vc_position")
            vc_priority = attrs.get("vc_priority")
            if vc_name or vc_master or vc_position or vc_priority:
                if not vc_name:
                    vc_name = self.vc_name
                try:
                    self._get_or_create_virtual_chassis(
                        vc_name, _device, self.diffsync.job.logger, vc_master, vc_position, vc_priority
                    )
                except (DjangoBaseDBError, ValidationError):
                    self.diffsync.job.logger.error(f"Unable to update VirtualChassis {vc_name} for Device {self.name}")
                    return_super = False
            if return_super:
                return super().update(attrs)
        return None

    @staticmethod
    def _get_or_create_virtual_chassis(  # pylint: disable=too-many-arguments
        name: str,
        device: NautobotDevice,
        job_logger: logging.Logger,
        master: bool = False,
        position: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> VirtualChassis:
        virtual_chassis, _ = VirtualChassis.objects.get_or_create(name=name)
        device.virtual_chassis = virtual_chassis
        if position:
            device.vc_position = position
        if priority and device.vc_position:  # An update might already have vc_position assigned
            device.vc_priority = priority
        elif priority:
            job_logger.warning(
                f"Device {device.name} assigned to VirtualChassis {name} has a "
                f"priority of {priority}, but this cannot be set without a vc_position"
            )
        try:
            device.validated_save()
        except (DjangoBaseDBError, ValidationError) as error:
            job_logger.error(f"Unable to perform validated_save() on Device named {device.name}")
            raise error

        if master:
            virtual_chassis.master = device
            try:
                virtual_chassis.validated_save()
            except (DjangoBaseDBError, ValidationError) as error:
                job_logger.error(
                    f"Unable to perform validated_save() on VirtualChassis {name}, "
                    "the VirtualChassis will not have a Device designated as master"
                )
                raise error

        return virtual_chassis


class Interface(DiffSyncExtras):
    """Interface model."""

    _modelname = "interface"
    _identifiers = (
        "name",
        "device_name",
    )
    _shortname = ("name",)
    _attributes = (
        "description",
        "enabled",
        "mac_address",
        "mtu",
        "type",
        "mgmt_only",
        "ip_address",
        "subnet_mask",
        "ip_is_primary",
        "status",
    )

    name: str
    device_name: str
    description: Optional[str]
    enabled: Optional[bool]
    mac_address: Optional[str]
    mtu: Optional[int]
    type: Optional[str]
    mgmt_only: Optional[bool]
    ip_address: Optional[str]
    subnet_mask: Optional[str]
    ip_is_primary: Optional[bool]
    status: str

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create interface in Nautobot under its parent device."""
        device_name = ids["device_name"]
        interface_name = ids["name"]
        ip_address = attrs["ip_address"]
        subnet_mask = attrs["subnet_mask"]  # TODO: switch to cidr notation since both APIs use that format
        ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
        device_obj = NautobotDevice.objects.filter(Q(name=device_name) & Q(tags__name=ssot_tag.name)).first()

        if device_obj:
            return_super = True
            if not attrs.get("mac_address"):
                attrs["mac_address"] = DEFAULT_INTERFACE_MAC
            interface_obj = tonb_nbutils.create_interface(
                device_obj=device_obj,
                interface_details={**ids, **attrs},
                logger=diffsync.job.logger,
            )
            if interface_obj and ip_address:
                if interface_obj.ip_addresses.exists():
                    interface_obj.ip_addresses.all().delete()
                ip_address_obj = tonb_nbutils.create_ip(
                    ip_address=ip_address,
                    subnet_mask=subnet_mask,
                    status=attrs["status"],
                    object_pk=interface_obj,
                    logger=diffsync.job.logger,
                )
                if ip_address_obj:
                    interface_obj.ip_addresses.add(ip_address_obj)
                    if attrs.get("ip_is_primary"):
                        if ip_address_obj.ip_version == 4:
                            device_obj.primary_ip4 = ip_address_obj
                            device_obj.save()
                        if ip_address_obj.ip_version == 6:
                            device_obj.primary_ip6 = ip_address_obj
                            device_obj.save()
                else:
                    diffsync.job.logger.warning(
                        f"Unable to assign an IPAddress to an Interface named {interface_name} on a Device named {device_name} "
                        f"because of a failure to get or create an IPAddress of {ip_address}/{subnet_mask}"
                    )
                    return_super = False
                try:
                    interface_obj.validated_save()
                except (DjangoBaseDBError, ValidationError):
                    diffsync.job.logger.error(
                        f"Unable to perform a validated_save() on an Interface named {interface_name} on a Device named {device_name}"
                    )
                    return_super = False
            elif ip_address:
                diffsync.job.logger.warning(
                    f"Unable to create an IPAddress {ip_address}/{subnet_mask} because of a failure "
                    f"to get or create an Interface named {interface_name} on a Device named {device_name}"
                )
                return_super = False
            elif not interface_obj:
                diffsync.job.logger.warning(
                    f"Unable to get or create an Interface named {interface_name} on a Device named {device_name}"
                )
                return_super = False
            if return_super:
                return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        else:
            diffsync.job.logger.warning(
                f"Unable to create an Interface with the name {interface_name} because of a failure "
                f"to get a Device named {device_name}"
            )
        return None

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete Interface Object."""
        ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
        device = NautobotDevice.objects.filter(Q(name=self.device_name) & Q(tags__name=ssot_tag.name)).first()
        if device:
            return_super = True
            try:
                interface = device.interfaces.get(name=self.name)
            except NautobotInterface.MultipleObjectsReturned:
                self.diffsync.job.logger.error(
                    f"Multiple Interfaces found with the name {self.name}, on Device named {self.device_name} "
                    f"with an ID of {device.id}, unable to determine which one to delete"
                )
            except NautobotInterface.DoesNotExist:
                self.diffsync.job.logger.error(
                    f"Unable to find an Interface with the name {self.name} on Device named {self.device_name} "
                    f"with an ID of {device.id} to delete"
                )
                return_super = False
            else:
                # Access the addr within an interface, change the status if necessary
                if interface.ip_addresses.first():
                    self.safe_delete(interface.ip_addresses.first(), SAFE_DELETE_IPADDRESS_STATUS)
                # Then do the parent interface
                # Attached interfaces do not have a status to update.
                self.safe_delete(interface)
            if return_super:
                return super().delete()
        else:
            self.diffsync.job.logger.warning(
                f"Unable to retrieve Device named {self.device_name}, so Interface named {self.name} "
                "will not be deleted."
            )
            logger.warning(f"Unable to match device by name, {self.name}")

        return None

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update Interface object in Nautobot."""
        ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
        device = NautobotDevice.objects.filter(Q(name=self.device_name) & Q(tags__name=ssot_tag.name)).first()
        if device:  # pylint: disable=too-many-nested-blocks
            return_super = True
            try:
                interface = device.interfaces.get(name=self.name)
            except NautobotInterface.MultipleObjectsReturned:
                self.diffsync.job.logger.error(
                    f"Multiple Interfaces found with the name {self.name} on Device named {device.name} "
                    f"with an ID of {device.id}, unable to determine which one to update"
                )
            except NautobotInterface.DoesNotExist:
                self.diffsync.logger.error(
                    f"Unable to find an Interface with the name {self.name} on Device named {device.name} "
                    f"with an ID of {device.id} to update"
                )
                return_super = False
            else:
                if attrs.get("description"):
                    interface.description = attrs["description"]
                if attrs.get("enabled"):
                    interface.enabled = attrs["enabled"]
                if attrs.get("mac_address"):
                    interface.mac_address = attrs["mac_address"]
                if attrs.get("mtu"):
                    interface.mtu = attrs["mtu"]
                if attrs.get("mode"):
                    interface.mode = attrs["mode"]
                if attrs.get("lag"):
                    interface.lag = attrs["lag"]
                if attrs.get("type"):
                    interface.type = attrs["type"]
                if attrs.get("mgmt_only"):
                    interface.mgmt_only = attrs["mgmt_only"]
                ip_address = attrs.get("ip_address")
                subnet_mask = attrs.get("subnet_mask", "255.255.255.255")
                if ip_address:
                    if interface.ip_addresses.all().exists():
                        logger.info(f"Replacing IP from interface {self.name} on {device.name}")
                        interface.ip_addresses.all().delete()
                    ip_address_obj = tonb_nbutils.create_ip(
                        ip_address=ip_address,
                        subnet_mask=subnet_mask,
                        status="Active",
                        object_pk=interface,
                        logger=self.diffsync.job.logger,
                    )
                    if ip_address_obj:
                        interface.ip_addresses.add(ip_address_obj)
                    else:
                        self.diffsync.job.logger.warning(
                            f"Unable to update Interface {self.name} on Device {device.name} "
                            f"with an IPAddress of {ip_address}/{subnet_mask}"
                        )
                        return_super = False
                elif attrs.get("subnet_mask"):
                    try:
                        ip_address_obj = interface.ip_addresses.get(host=self.ip_address)
                    except IPAddress.MultipleObjectsReturned:
                        self.diffsync.job.logger.error(
                            f"Multiple IPAddresses found with an address of {self.ip_address} on Interface named {self.name} "
                            f"on Device named {device.name} with an ID of {device.id}, unable to determine which one "
                            f"to update with a mask of {subnet_mask}"
                        )
                        return_super = False
                    except IPAddress.DoesNotExist:
                        self.diffsync.job.logger.error(
                            f"Unable to find an IPAddress with an address of {self.ip_address} on Interface named {self.name} "
                            f"on Device named {device.name} with an ID of {device.id} to update with a mask of {subnet_mask}"
                        )
                        return_super = False
                    else:
                        ip_address_obj.mask_length = netmask_to_cidr(subnet_mask)
                        try:
                            ip_address_obj.validated_save()
                        except (DjangoBaseDBError, ValidationError):
                            self.diffsync.job.logger.error(
                                f"Unable to update the subnet_mask with a value of {subnet_mask} on Interface named {self.name} "
                                f"on Device named {device.name} with an ID of {device.id}"
                            )
                            return_super = False
                if attrs.get("ip_is_primary"):
                    interface_obj = interface.ip_addresses.first()
                    if interface_obj:
                        try:
                            if interface_obj.ip_version == 4:
                                device.primary_ip4 = interface_obj
                                device.save()
                            if interface_obj.ip_version == 6:
                                device.primary_ip6 = interface_obj
                                device.save()
                        except (DjangoBaseDBError, ValidationError):
                            self.diffsync.job.logger.error(
                                f"Unable to update Primay IP for Device named {device.name} "
                                f"with an ID of {device.id}"
                            )
                            return_super = False
                    else:
                        self.diffsync.job.logger.error(
                            f"Unable to update Primary IP for Device named {device.name} "
                            "because no interfaces could be found on the Device"
                        )
                        return_super = False
                try:
                    tonb_nbutils.tag_object(nautobot_object=interface, custom_field=LAST_SYNCHRONIZED_CF_NAME)
                except (DjangoBaseDBError, ValidationError):
                    self.diffsync.job.logger.error(
                        f"Unable to perform validated_save() on Interface named {self.name} "
                        f"on Device named {device.name} with an ID of {device.id}"
                    )
                    return_super = False
            if return_super:
                return super().update(attrs)

        else:
            logger.warning(f"Unable to match device by name, {self.name}")
            self.diffsync.job.logger.warning(
                f"Unable to retrieve a Device named {self.device_name}, so unable to update "
                f"its interface named {self.name}"
            )
        return None


class Vlan(DiffSyncExtras):
    """VLAN model."""

    _modelname = "vlan"
    _identifiers = ("name", "location")
    _shortname = ("name",)
    _attributes = ("vid", "status", "description")

    name: str
    vid: int
    status: str
    location: str
    description: Optional[str]
    vlan_pk: Optional[UUID]

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLANs in Nautobot under the site."""
        status = attrs["status"].lower().capitalize()
        location_name = ids["location"]
        vlan_id = attrs["vid"]
        vlan_name = ids["name"] if ids["name"] else f"VLAN{vlan_id}"
        try:
            location = NautobotLocation.objects.get(name=ids["location"])
        except NautobotLocation.MultipleObjectsReturned:
            diffsync.job.logger.error(
                f"Multiple Locations returned with the name {location_name}, "
                f"unable to create a VLAN named {vlan_name} and VLAN ID {vlan_id}"
            )
        except NautobotLocation.DoesNotExist:
            diffsync.job.logger.error(
                f"Unable to retrieve a Location with the name {location_name}, "
                f"unable to create a VLAN named {vlan_name} and VLAN ID {vlan_id}"
            )
        else:
            description = attrs.get("description")
            if diffsync.job.debug:
                logger.debug("Creating VLAN: %s description: %s", vlan_name, description)
            vlan = tonb_nbutils.create_vlan(
                vlan_name=vlan_name,
                vlan_id=vlan_id,
                vlan_status=status,
                location_obj=location,
                description=description,
                logger=diffsync.job.logger,
            )
            if vlan:
                return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
            diffsync.job.logger.error.debug(
                f"Unable to get or create a VLAN named {vlan_name} with VLAN ID {vlan_id} at location named {location_name}"
            )
        return None

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete."""
        try:
            vlan = VLAN.objects.get(name=self.name, pk=self.vlan_pk)
        except VLAN.DoesNotExist:
            self.diffsync.job.logger.error(
                f"Unable to find a VLAN found with the name {self.name} and an ID of {self.vlan_pk}"
            )
        else:
            self.safe_delete(
                vlan,
                SAFE_DELETE_VLAN_STATUS,
            )
            return super().delete()
        return None

    def update(self, attrs):
        """Update VLAN object in Nautobot."""
        try:
            location_obj = NautobotLocation.objects.get(name=self.location)
        except NautobotLocation.MultipleObjectsReturned:
            self.diffsync.job.logger.error(
                f"Multiple Locations found with the name {self.location}, unable to "
                f"Retrieve the VLAN named {self.name} to perform updates"
            )
        except NautobotLocation.DoesNotExist:
            self.diffsync.job.logger.error(
                f"Could not find a Location with the name {self.location}, unable to "
                f"Retrieve the VLAN named {self.name} to perform updates"
            )
        else:
            return_super = True
            try:
                vlan = VLAN.objects.get(name=self.name, vid=self.vid, location=location_obj)
            except VLAN.MultipleObjectsReturned:
                self.diffsync.job.logger.error(
                    f"Multiple VLANs found with a name {self.name} and VLAN ID {self.vid} "
                    f"at a Location named {self.location}, unable to perform updates"
                )
                return_super = False
            except VLAN.DoesNotExist:
                self.diffsync.job.logger.error(
                    f"Could not find a VLAN named {self.name} and VLAN ID {self.vid} "
                    f"at a Location named {self.location}, unable to perform updates"
                )
                return_super = False
            else:
                if attrs.get("status") == "Active":
                    safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
                    if not vlan.status == "Active":
                        vlan.status = Status.objects.get(name="Active")
                    device_tags = vlan.tags.filter(pk=safe_delete_tag.pk)
                    if device_tags.exists():
                        vlan.tags.remove(safe_delete_tag)
                if attrs.get("description"):
                    vlan.description = vlan.description
            try:
                tonb_nbutils.tag_object(nautobot_object=vlan, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError):
                self.diffsync.job.logger.warning(
                    f"Unable to perform a validated_save() on VLAN {self.name} with an ID of {vlan.id}"
                )
                return_super = False
            if return_super:
                return super().update(attrs)
        return None


Location.update_forward_refs()
Device.update_forward_refs()
Interface.update_forward_refs()
Vlan.update_forward_refs()
