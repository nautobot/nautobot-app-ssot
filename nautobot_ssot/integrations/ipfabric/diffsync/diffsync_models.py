# pylint: disable=duplicate-code
# Ignore return statements for updates and deletes, #  pylint:disable=R1710
# Ignore too many args #  pylint:disable=too-many-locals
# One module holds every synced model #  pylint:disable=too-many-lines
"""DiffSyncModel subclasses for Nautobot-to-IPFabric data sync."""

import logging
from typing import Any, ClassVar, List, Optional
from uuid import UUID

from diffsync import DiffSyncModel
from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from django.db.models import ProtectedError
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import (
    Cable as NautobotCable,
)
from nautobot.dcim.models import (
    Device as NautobotDevice,
)
from nautobot.dcim.models import (
    Location as NautobotLocation,
)
from nautobot.extras.models import Tag
from nautobot.ipam.models import VLAN, IPAddress
from netutils.ip import netmask_to_cidr

import nautobot_ssot.integrations.ipfabric.utilities.cables as tonb_cables
import nautobot_ssot.integrations.ipfabric.utilities.nbutils as tonb_nbutils
from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_CABLE_STATUS,
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_ROLE_COLOR,
    DEFAULT_DEVICE_STATUS,
    DEFAULT_DEVICE_STATUS_COLOR,
    DEFAULT_INTERFACE_MAC,
    LAST_SYNCHRONIZED_CF_NAME,
    SAFE_DELETE_CABLE_STATUS,
    SAFE_DELETE_DEVICE_STATUS,
    SAFE_DELETE_IPADDRESS_STATUS,
    SAFE_DELETE_LOCATION_STATUS,
    SAFE_DELETE_VLAN_STATUS,
    SYNC_IPF_DEV_TYPE_TO_ROLE,
)

logger = logging.getLogger(__name__)


def resolve_location(adapter, location_name: str, location_id: Optional[str] = None):
    """Return the Nautobot Location a synced object belongs to.

    Creates one only while Locations are in scope. Out of scope another system owns them, so a
    Location that is not there yet is expected to arrive from that system; this sync looks for it and
    reports it missing rather than filling the gap itself.
    """
    if adapter.scope.locations:
        return tonb_nbutils.get_or_create_location_object(
            location_name=location_name,
            location_id=location_id,
            logger=adapter.job.logger,
            pending=adapter.pending_writes,
        )
    return tonb_nbutils.get_location_object(location_name, logger=adapter.job.logger)


def resolve_manufacturer(adapter, vendor_name: str):
    """Return the Nautobot Manufacturer for a vendor IP Fabric reports.

    Creates one only while Manufacturers are in scope. Out of scope another system owns the vendor
    list, so this sync looks for the Manufacturer and reports it missing rather than adding to it.
    """
    if adapter.scope.manufacturers:
        return tonb_nbutils.get_or_create_manufacturer_object(vendor_name, logger=adapter.job.logger)
    return tonb_nbutils.get_manufacturer_object(vendor_name, logger=adapter.job.logger)


def resolve_device_type(adapter, device_type_name: str, vendor_name: str):
    """Return the Nautobot DeviceType for a model IP Fabric reports.

    An existing DeviceType is used whatever the scope. Creating one is what the scope governs, and
    creating one needs a Manufacturer, so the Manufacturer is resolved through its own scope first:
    a sync told not to add vendors must not add one in order to add a model.
    """
    existing = tonb_nbutils.get_device_type_object(device_type_name, logger=adapter.job.logger)
    if existing or not adapter.scope.device_types:
        return existing
    manufacturer_object = resolve_manufacturer(adapter, vendor_name)
    if not manufacturer_object:
        adapter.job.logger.warning(
            f"Unable to get or create a DeviceType named {device_type_name}, as no Manufacturer named "
            f"{vendor_name} could be resolved"
        )
        return None
    return tonb_nbutils.get_or_create_device_type_object(
        device_type=device_type_name,
        vendor_name=vendor_name,
        logger=adapter.job.logger,
        manufacturer_obj=manufacturer_object,
    )


def resolve_role(adapter, role_name: str):
    """Return the Nautobot Role for a device type IP Fabric reports.

    Creates one only while Roles are in scope. Out of scope roles are assigned by another process, so
    this sync matches an existing Role and reports a missing one rather than inventing it.
    """
    if adapter.scope.roles:
        return tonb_nbutils.get_or_create_device_role_object(
            role_name=role_name,
            role_color=DEFAULT_DEVICE_ROLE_COLOR,
            logger=adapter.job.logger,
        )
    return tonb_nbutils.get_device_role_object(role_name, logger=adapter.job.logger)


def resolve_platform(adapter, platform_name: str, manufacturer_object):
    """Return the Nautobot Platform for a family IP Fabric reports.

    Creates one only while Platforms are in scope, and only when a Manufacturer to file it under was
    resolved. Out of scope the Platform is matched on its name alone, since the system that owns it
    decides its Manufacturer.
    """
    if not adapter.scope.platforms:
        return tonb_nbutils.get_platform_object(platform_name, logger=adapter.job.logger)
    if not manufacturer_object:
        return None
    return tonb_nbutils.get_or_create_platform_object(
        platform=platform_name,
        manufacturer_obj=manufacturer_object,
        logger=adapter.job.logger,
    )


# pylint: disable=too-many-branches,too-many-statements
class DiffSyncExtras(DiffSyncModel):
    """Additional components to mix and subclass from with `DiffSyncModel`."""

    safe_delete_mode: ClassVar[bool] = True

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Record the object in the store, writing any batch that has grown large enough first.

        Every model reaches here through `super().create()` once its own work is done, which is the
        one point at which writing a queued batch is safe: flushed any earlier, the batch would miss
        whatever the model went on to set.
        """
        if adapter.pending_writes is not None:
            adapter.flush_pending_writes_if_full()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def safe_delete(
        self,
        nautobot_object: Any,
        safe_delete_status: Optional[str] = None,
        safe_delete_tag: Optional[Tag] = None,
    ):
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
            self.adapter.objects_to_delete[f"_{nautobot_object.__class__.__name__.lower()}"].append(nautobot_object)  # pylint: disable=protected-access
            super().delete()
        else:
            if safe_delete_status:
                safe_delete_status = tonb_nbutils.get_or_create_status_object(
                    safe_delete_status.capitalize(), ColorChoices.COLOR_RED
                )
                if hasattr(nautobot_object, "status"):
                    if not nautobot_object.status == safe_delete_status:
                        nautobot_object.status = safe_delete_status
                        logger.warning(f"{nautobot_object} has changed status to {safe_delete_status}.")
                        update = True
                else:
                    # Not everything has a status. This may come in handy once more models are synced.
                    logger.warning(f"{nautobot_object} has no Status attribute.")
            tags_to_add = ()
            if hasattr(nautobot_object, "tags") and safe_delete_tag:
                already_tagged = tonb_nbutils.get_tagged_pks(type(nautobot_object), safe_delete_tag.id)
                if nautobot_object.pk not in already_tagged:
                    # Applied below alongside the synced from tag, as one call to `tags.add`.
                    tags_to_add = (safe_delete_tag,)
                    logger.warning(f"Tagging {nautobot_object} with `SSoT Safe Delete`.")
                    update = True
                else:
                    logger.warning(f"{nautobot_object} has previously been tagged with `SSoT Safe Delete`. Skipping...")
            if update:
                tonb_nbutils.tag_object(
                    nautobot_object=nautobot_object,
                    custom_field=LAST_SYNCHRONIZED_CF_NAME,
                    extra_tags=tags_to_add,
                )
        return self


class Location(DiffSyncExtras):
    """Location model."""

    _modelname = "location"
    _identifiers = ("name",)
    _attributes = ("site_id", "status")
    _children = {"device": "devices", "vlan": "vlans"}

    name: str
    site_id: Optional[str] = None
    status: str
    devices: List["Device"] = []
    vlans: List["Vlan"] = []

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create Location in Nautobot, or find it when Locations are out of scope.

        Out of scope the model is returned whether or not the Location was found, because DiffSync
        stops descending when a create yields nothing and the Devices at this Location are still
        worth attempting. Each reports its own outcome, so a Location another app has not created yet
        shows up as the Devices that could not be placed rather than as silence.
        """
        location = resolve_location(adapter, ids["name"], attrs["site_id"])
        if not location:
            if adapter.scope.locations:
                return None
            adapter.job.logger.warning(
                f"No Location named {ids['name']} exists and Locations are out of scope, so it will not be "
                "created here. Devices at it will be attempted and will fail until another sync creates it."
            )
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete Location in Nautobot."""
        try:
            location = NautobotLocation.objects.get(name=self.name)
        except NautobotLocation.MultipleObjectsReturned:
            self.adapter.job.logger.error(
                f"Multiple Locations found with the name {self.name}, unable to determine which one to delete"
            )
        except NautobotLocation.DoesNotExist:
            self.adapter.job.logger.error(f"Unable to find a Location with the name {self.name} to delete")
        else:
            self.safe_delete(
                location,
                SAFE_DELETE_LOCATION_STATUS,
                self.adapter.safe_delete_tag,
            )
            return super().delete()
        return None

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):
        """Update Location Object in Nautobot."""
        try:
            location = NautobotLocation.objects.get(name=self.name)
        except NautobotLocation.MultipleObjectsReturned:
            self.adapter.job.logger.error(
                f"Multiple Locations found with the name {self.name}, unable to determine which one to update"
            )
        except NautobotLocation.DoesNotExist:
            self.adapter.job.logger.error(f"Unable to find a Location with the name {self.name} to update")
        else:
            site_id = attrs.get("site_id")
            if site_id:
                location.custom_field_data["ipfabric_site_id"] = site_id
            active_status = attrs.get("status")
            if active_status == "Active":
                if location.status != active_status:
                    location.status = tonb_nbutils.get_or_create_status_object(active_status, ColorChoices.COLOR_GREEN)
                location.tags.remove(self.adapter.safe_delete_tag)
            try:
                # Calls validated_save() on the object
                tonb_nbutils.tag_object(nautobot_object=location, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError):
                self.adapter.job.logger.error(f"Unable to update the existing Location named {self.name} with {attrs}")
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
    location_name: Optional[str] = None
    model: Optional[str] = None
    vendor: Optional[str] = None
    serial_number: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    platform: Optional[str] = None
    vc_name: Optional[str] = None
    vc_priority: Optional[int] = None
    vc_position: Optional[int] = None
    vc_master: Optional[bool] = None

    mgmt_address: Optional[str] = None

    interfaces: List["Interface"] = []

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create Device in Nautobot under its parent location."""
        # Get DeviceType
        device_name = ids["name"]
        device_type_name = attrs["model"]
        vendor_name = attrs["vendor"]
        device_type_object = resolve_device_type(adapter, device_type_name, vendor_name)
        if not device_type_object:
            adapter.job.logger.warning(
                f"Unable to create a Device with the name {device_name} because of a failure "
                f"to get or create a DeviceType named {device_type_name} with a Manufacturer named {vendor_name}"
            )
        # Get Platform
        platform = attrs.get("platform")
        if platform and device_type_object:
            platform_object = resolve_platform(adapter, platform, device_type_object.manufacturer)
            if not platform_object:
                adapter.job.logger.warning(
                    f"Unable to get or create a Platform named {platform}, "
                    f"Device named {device_name} will not have a Platform assigned"
                )
        elif platform:
            adapter.job.logger.warning(
                f"Unable to get or create a Platform named {platform} since the DeviceType could not be retrieved, "
                f"Device named {device_name} will not have a Platform assigned"
            )
        else:
            platform_object = None

        # Get Role, update if missing cf and create otherwise
        role_name = attrs.get("role") or DEFAULT_DEVICE_ROLE
        device_role_object = resolve_role(adapter, role_name)
        if device_role_object:
            # Only while Roles are in scope: the custom field records what IP Fabric called the role,
            # and stamping it on a Role another system owns is exactly what deselecting them refuses.
            if adapter.scope.roles and device_role_object.cf.get("ipfabric_type") != role_name:
                device_role_object.cf["ipfabric_type"] = role_name
                try:
                    device_role_object.validated_save()
                except (DjangoBaseDBError, ValidationError):
                    adapter.job.logger.error(
                        f"Unable to perform a validated_save() on Role {role_name} with an ID of {device_role_object.id}"
                    )
        else:
            adapter.job.logger.warning(
                f"Unable to create a Device with the name {device_name} because of a failure "
                f"to get or create a Role named {role_name}"
            )
        # Get Status
        device_status_object = tonb_nbutils.get_or_create_status_object(
            DEFAULT_DEVICE_STATUS,
            DEFAULT_DEVICE_STATUS_COLOR,
            logger=adapter.job.logger,
        )
        if not device_status_object:
            adapter.job.logger.warning(
                f"Unable to create a Device with the name {device_name} because of a failure "
                f"to get or create a Status named {DEFAULT_DEVICE_STATUS}"
            )
        # Get Location
        location_name = attrs["location_name"]
        location_object = resolve_location(adapter, location_name)
        if not location_object:
            adapter.job.logger.warning(
                f"Unable to create Device with name {device_name} because of a failure "
                f"to get or create a Location named {location_name}"
            )

        if device_type_object and location_object and device_role_object and device_status_object:
            pending = adapter.pending_writes
            lookup = {
                "name": device_name,
                "serial": attrs.get("serial_number", ""),
                "status": device_status_object,
                "device_type": device_type_object,
                "role": device_role_object,
                "location": location_object,
            }
            try:
                if pending is None:
                    # Deliberately a get-or-create, which inserts without `full_clean()`. A Platform
                    # owned by another system may name a different Manufacturer to the DeviceType,
                    # which `Device.clean()` rejects but this integration accepts; validating before
                    # the insert would stop such a Device being written at all.
                    new_device, created = NautobotDevice.objects.get_or_create(
                        defaults={"platform": platform_object}, **lookup
                    )
                    is_new = created
                else:
                    try:
                        new_device = NautobotDevice.objects.get(**lookup)
                        is_new = False
                    except NautobotDevice.DoesNotExist:
                        new_device = NautobotDevice(platform=platform_object, **lookup)
                        is_new = True
            except NautobotDevice.MultipleObjectsReturned:
                adapter.job.logger.error(
                    f"Multiple Devices returned with name {device_name} at Location {location_name}"
                )
            except (DjangoBaseDBError, ValidationError):
                adapter.job.logger.error(
                    f"Unable to create a new Device named {device_name} at Location {location_name}"
                )
            else:
                if is_new and pending is not None:
                    tonb_nbutils.stamp_synced(new_device, LAST_SYNCHRONIZED_CF_NAME)
                    pending.add(new_device, key=device_name)
                    tonb_nbutils.queue_synced_tag(pending, new_device)
                else:
                    try:
                        # Validated save happens inside of tag_objet
                        tonb_nbutils.tag_object(nautobot_object=new_device, custom_field=LAST_SYNCHRONIZED_CF_NAME)
                    except (DjangoBaseDBError, ValidationError) as error:
                        adapter.job.logger.error(
                            f"Unable to perform a validated_save() on Device {device_name} with an ID of {new_device.id}"
                        )
                        message = f"Unable to create device: {device_name}. A validation error occured. Enable debug for more information."
                        if adapter.job.debug:
                            logger.debug(error)
                        logger.error(message)

                vc_name = attrs.get("vc_name")
                if vc_name:
                    try:
                        vc = tonb_nbutils.get_or_create_virtual_chassis_object(vc_name, logger=adapter.job.logger)
                        if vc:
                            tonb_nbutils.assign_device_to_virtual_chassis(
                                new_device,
                                vc,
                                master=attrs.get("vc_master", False),
                                position=attrs.get("vc_position"),
                                priority=attrs.get("vc_priority"),
                                pending=pending,
                            )
                    except (DjangoBaseDBError, ValidationError):
                        adapter.job.logger.error(f"Unable to update Device {device_name} with VirtualChassis data")
                return super().create(ids=ids, adapter=adapter, attrs=attrs)
        return None

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete device in Nautobot."""
        try:
            device_object = NautobotDevice.objects.get(name=self.name)
        except NautobotDevice.MultipleObjectsReturned:
            self.adapter.job.logger.error(
                f"Multiple Devices found with the name {self.name}, unable to determine which one to delete"
            )
        except NautobotDevice.DoesNotExist:
            self.adapter.job.logger.error(f"Unable to find a Device with the name {self.name} to delete")
        else:
            self.safe_delete(
                device_object,
                SAFE_DELETE_DEVICE_STATUS,
                self.adapter.safe_delete_tag,
            )
            return super().delete()
        return None

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):
        """Update devices in Nautobot based on Source."""
        try:
            _device = NautobotDevice.objects.get(name=self.name)
        except NautobotDevice.MultipleObjectsReturned:
            self.adapter.job.logger.error(
                f"Multiple Devices found with the name {self.name}, unable to determine which one to update"
            )
        except NautobotDevice.DoesNotExist:
            self.adapter.job.logger.error(f"Unable to find a Device with the name {self.name} to update")
        else:
            return_super = True
            if attrs.get("status") == "Active":
                if not _device.status.name == "Active":
                    _device.status = tonb_nbutils.get_or_create_status_object("Active", ColorChoices.COLOR_GREEN)
                _device.tags.remove(self.adapter.safe_delete_tag)

            vendor_name = attrs.get("vendor") or self.vendor
            device_type_name = attrs.get("model")
            if device_type_name:
                device_type_object = resolve_device_type(self.adapter, device_type_name, vendor_name)
                if device_type_object:
                    _device.type = device_type_object
                else:
                    self.adapter.job.logger.warning(
                        f"Unable to update Device {self.name} with a DeviceType of {device_type_name}"
                    )
                    return_super = False
            platform_name = attrs.get("platform")
            if platform_name:
                # Resolved rather than fetched directly, so that a Platform is not created under a
                # Manufacturer this sync is not permitted to add.
                manufacturer_object = resolve_manufacturer(self.adapter, vendor_name)
                platform_object = resolve_platform(self.adapter, platform_name, manufacturer_object)
                if platform_object:
                    _device.platform = platform_object
                else:
                    self.adapter.job.logger.warning(
                        f"Unable to update Device {self.name} with a Platform of {platform_name}"
                    )
                    return_super = False

            location_name = attrs.get("location_name")
            if location_name:
                location = resolve_location(self.adapter, location_name)
                if location:
                    _device.location = location
                else:
                    self.adapter.job.logger.warning(
                        f"Unable to update Device {self.name} with a Location named {location_name}"
                    )
                    return_super = False
            if attrs.get("serial_number"):
                _device.serial = attrs.get("serial_number")
            if SYNC_IPF_DEV_TYPE_TO_ROLE and (role_name := attrs.get("role")):
                device_role_object = resolve_role(self.adapter, role_name)
                if device_role_object:
                    _device.role = device_role_object
                else:
                    self.adapter.job.logger.warning(
                        f"Unable to update Device {self.name} with a Role named {role_name}"
                    )
                    return_super = False
            # tonb_nbutils.tag_object calls validated_save()
            try:
                tonb_nbutils.tag_object(nautobot_object=_device, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError) as err:
                self.adapter.job.logger.error(
                    f"Unable to update the existing Device named {self.name} with {attrs}. Error: {err}"
                )
                return_super = False

            vc_name = attrs.get("vc_name") or self.vc_name
            vc_attrs_present = any(k in attrs for k in ("vc_name", "vc_master", "vc_position", "vc_priority"))
            if vc_attrs_present and vc_name:
                try:
                    vc = tonb_nbutils.get_or_create_virtual_chassis_object(vc_name, logger=self.adapter.job.logger)
                    if vc:
                        tonb_nbutils.assign_device_to_virtual_chassis(
                            _device,
                            vc,
                            master=attrs.get("vc_master", False),
                            position=attrs.get("vc_position"),
                            priority=attrs.get("vc_priority"),
                        )
                except (DjangoBaseDBError, ValidationError):
                    self.adapter.job.logger.error(f"Unable to update VirtualChassis {vc_name} for Device {self.name}")
                    return_super = False
            if return_super:
                return super().update(attrs)
        return None


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
    description: Optional[str] = None
    enabled: Optional[bool] = None
    mac_address: Optional[str] = None
    mtu: Optional[int] = None
    type: Optional[str] = None
    mgmt_only: Optional[bool] = None
    ip_address: Optional[str] = None
    subnet_mask: Optional[str] = None
    ip_is_primary: Optional[bool] = None
    status: str

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create interface in Nautobot under its parent device."""
        device_name = ids["device_name"]
        interface_name = ids["name"]
        ip_address = attrs["ip_address"]
        subnet_mask = attrs["subnet_mask"]  # TODO: switch to cidr notation since both APIs use that format
        # A Device queued earlier in this run is not in the database yet, so it is looked for there
        # first. `get_syncable_device` is cached, so it is asked second rather than taught about the
        # queue.
        device_obj = None
        if adapter.pending_writes is not None:
            device_obj = adapter.pending_writes.find(NautobotDevice, device_name)
        device_obj = device_obj or tonb_nbutils.get_syncable_device(
            device_name, tagged_only=adapter.sync_ipfabric_tagged_only
        )
        if device_obj:
            return_super = True
            if not attrs.get("mac_address"):
                attrs["mac_address"] = DEFAULT_INTERFACE_MAC
            pending = adapter.pending_writes
            interface_obj = tonb_nbutils.create_interface(
                device_obj=device_obj,
                interface_details={**ids, **attrs},
                logger=adapter.job.logger,
                pending=pending,
            )
            if interface_obj and ip_address:
                if pending is None:
                    # A queued Interface has no addresses to clear, and clearing them would read a
                    # row that does not exist yet.
                    interface_obj.ip_addresses.set([])
                ip_address_obj = tonb_nbutils.create_ip(
                    ip_address=ip_address,
                    subnet_mask=subnet_mask,
                    status=attrs["status"],
                    object_pk=interface_obj,
                    logger=adapter.job.logger,
                    pending=pending,
                )
                if ip_address_obj:
                    # `create_ip` has already assigned it to the Interface, through a validated
                    # save of the assignment rather than the plain insert `add()` would do.
                    if attrs.get("ip_is_primary"):
                        field = "primary_ip4" if ip_address_obj.ip_version == 4 else "primary_ip6"
                        if pending is None:
                            setattr(device_obj, field, ip_address_obj)
                            device_obj.save()
                        else:
                            # Not set on the Device here: the address is only queued, and the Device
                            # may be too, in which case its own insert would carry a foreign key to
                            # a row that does not exist yet. Assigned once everything is written.
                            pending.defer_update(device_obj, {field: ip_address_obj})
                else:
                    adapter.job.logger.warning(
                        f"Unable to assign an IPAddress to an Interface named {interface_name} on a Device named {device_name} "
                        f"because of a failure to get or create an IPAddress of {ip_address}/{subnet_mask}"
                    )
                    return_super = False
                # The Interface is not saved again here. `create_interface` saved it, and nothing
                # since has changed a field on it: assigning an address touches only the through
                # table, and `Interface.clean()` does not validate the addresses assigned to it.
            elif ip_address:
                adapter.job.logger.warning(
                    f"Unable to create an IPAddress {ip_address}/{subnet_mask} because of a failure "
                    f"to get or create an Interface named {interface_name} on a Device named {device_name}"
                )
                return_super = False
            elif not interface_obj:
                adapter.job.logger.warning(
                    f"Unable to get or create an Interface named {interface_name} on a Device named {device_name}"
                )
                return_super = False
            if return_super:
                return super().create(ids=ids, adapter=adapter, attrs=attrs)
        else:
            adapter.job.logger.warning(
                f"Unable to create an Interface with the name {interface_name} because of a failure "
                f"to get a Device named {device_name}"
            )
        return None

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete Interface Object."""
        device = tonb_nbutils.get_syncable_device(self.device_name, tagged_only=self.adapter.sync_ipfabric_tagged_only)
        if device:
            return_super = True
            # Every Interface of the Device at once, so removing many of them costs one lookup
            # rather than one each. Nautobot makes `(device, name)` unique, so there is no
            # ambiguous match to report.
            interface = tonb_nbutils.get_device_interfaces_by_name(device).get(self.name)
            if interface is None:
                self.adapter.job.logger.error(
                    f"Unable to find an Interface with the name {self.name} on Device named {self.device_name} "
                    f"with an ID of {device.id} to delete"
                )
                return_super = False
            else:
                # Access the addr within an interface, change the status if necessary
                for ip_address in interface.ip_addresses.all():
                    # An address can be on several Interfaces, and only one with no other Interface
                    # is safe to delete. Read from the prefetched Interfaces rather than excluding
                    # this one in the database, which would cost a query per address and make the
                    # `ip_addresses__interfaces` prefetch above pointless.
                    if not any(other.id != interface.id for other in ip_address.interfaces.all()):
                        self.safe_delete(ip_address, SAFE_DELETE_IPADDRESS_STATUS, self.adapter.safe_delete_tag)
                # Then do the parent interface
                # Attached interfaces do not have a status to update.
                self.safe_delete(interface, None, self.adapter.safe_delete_tag)
            if return_super:
                return super().delete()
        else:
            self.adapter.job.logger.warning(
                f"Unable to retrieve Device named {self.device_name}, so Interface named {self.name} "
                "will not be deleted."
            )
            logger.warning(f"Unable to match device by name, {self.name}")

        return None

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update Interface object in Nautobot."""
        device = tonb_nbutils.get_syncable_device(self.device_name, tagged_only=self.adapter.sync_ipfabric_tagged_only)
        if device:  # pylint: disable=too-many-nested-blocks
            return_super = True
            # Every Interface of the Device at once, so a Device with many of them changing costs
            # one lookup rather than one each. Nautobot makes `(device, name)` unique, so there is
            # no ambiguous match to report. Each Interface is updated at most once per run, so the
            # addresses this reads are still the ones on it.
            interface = tonb_nbutils.get_device_interfaces_by_name(device).get(self.name)
            if interface is None:
                self.adapter.job.logger.error(
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
                    if interface.ip_addresses.all():
                        logger.info(f"Replacing IP from interface {self.name} on {device.name}")
                        interface.ip_addresses.set([])
                    ip_address_obj = tonb_nbutils.create_ip(
                        ip_address=ip_address,
                        subnet_mask=subnet_mask,
                        status="Active",
                        object_pk=interface,
                        logger=self.adapter.job.logger,
                    )
                    if not ip_address_obj:
                        self.adapter.job.logger.warning(
                            f"Unable to update Interface {self.name} on Device {device.name} "
                            f"with an IPAddress of {ip_address}/{subnet_mask}"
                        )
                        return_super = False
                elif attrs.get("subnet_mask"):
                    try:
                        ip_address_obj = interface.ip_addresses.get(host=self.ip_address)
                    except IPAddress.MultipleObjectsReturned:
                        self.adapter.job.logger.error(
                            f"Multiple IPAddresses found with an address of {self.ip_address} on Interface named {self.name} "
                            f"on Device named {device.name} with an ID of {device.id}, unable to determine which one "
                            f"to update with a mask of {subnet_mask}"
                        )
                        return_super = False
                    except IPAddress.DoesNotExist:
                        self.adapter.job.logger.error(
                            f"Unable to find an IPAddress with an address of {self.ip_address} on Interface named {self.name} "
                            f"on Device named {device.name} with an ID of {device.id} to update with a mask of {subnet_mask}"
                        )
                        return_super = False
                    else:
                        ip_address_obj.mask_length = netmask_to_cidr(subnet_mask)
                        try:
                            ip_address_obj.validated_save()
                        except (DjangoBaseDBError, ValidationError):
                            self.adapter.job.logger.error(
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
                            elif interface_obj.ip_version == 6:
                                device.primary_ip6 = interface_obj
                                device.save()
                        except (DjangoBaseDBError, ValidationError):
                            self.adapter.job.logger.error(
                                f"Unable to update Primay IP for Device named {device.name} "
                                f"with an ID of {device.id}"
                            )
                            return_super = False
                    else:
                        self.adapter.job.logger.error(
                            f"Unable to update Primary IP for Device named {device.name} "
                            "because no interfaces could be found on the Device"
                        )
                        return_super = False
                try:
                    tonb_nbutils.tag_object(nautobot_object=interface, custom_field=LAST_SYNCHRONIZED_CF_NAME)
                except (DjangoBaseDBError, ValidationError):
                    self.adapter.job.logger.error(
                        f"Unable to perform validated_save() on Interface named {self.name} "
                        f"on Device named {device.name} with an ID of {device.id}"
                    )
                    return_super = False
            if return_super:
                return super().update(attrs)

        else:
            logger.warning(f"Unable to match device by name, {self.name}")
            self.adapter.job.logger.warning(
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
    description: Optional[str] = None
    vlan_pk: Optional[UUID] = None

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create VLANs in Nautobot under the site."""
        status = attrs["status"].lower().capitalize()
        location_name = ids["location"]
        vlan_id = attrs["vid"]
        vlan_name = ids["name"]
        # A Location queued earlier in this run is not in the database yet, so it is looked for
        # there first. Falls through to the database, which is where it is on any other run.
        location = None
        if adapter.pending_writes is not None:
            location = adapter.pending_writes.find(NautobotLocation, location_name)
        try:
            location = location or NautobotLocation.objects.get(name=ids["location"])
        except NautobotLocation.MultipleObjectsReturned:
            adapter.job.logger.error(
                f"Multiple Locations returned with the name {location_name}, "
                f"unable to create a VLAN named {vlan_name} and VLAN ID {vlan_id}"
            )
        except NautobotLocation.DoesNotExist:
            adapter.job.logger.error(
                f"Unable to retrieve a Location with the name {location_name}, "
                f"unable to create a VLAN named {vlan_name} and VLAN ID {vlan_id}"
            )
        else:
            description = attrs.get("description")
            if adapter.job.debug:
                adapter.job.logger.debug("Creating VLAN: %s description: %s", vlan_name, description)
            vlan = tonb_nbutils.create_vlan(
                vlan_name=vlan_name,
                vlan_id=vlan_id,
                vlan_status=status,
                location_obj=location,
                description=description,
                logger=adapter.job.logger,
                pending=adapter.pending_writes,
            )
            if vlan:
                return super().create(ids=ids, adapter=adapter, attrs=attrs)
            if adapter.job.debug:
                adapter.job.logger.debug(
                    f"Unable to get or create a VLAN named {vlan_name} with VLAN ID {vlan_id} at location named {location_name}"
                )
        return None

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete."""
        try:
            vlan = VLAN.objects.get(name=self.name, pk=self.vlan_pk)
        except VLAN.DoesNotExist:
            self.adapter.job.logger.error(
                f"Unable to find a VLAN found with the name {self.name} and an ID of {self.vlan_pk}"
            )
        else:
            self.safe_delete(
                vlan,
                SAFE_DELETE_VLAN_STATUS,
                self.adapter.safe_delete_tag,
            )
            return super().delete()
        return None

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):
        """Update VLAN object in Nautobot."""
        try:
            location_obj = NautobotLocation.objects.get(name=self.location)
        except NautobotLocation.MultipleObjectsReturned:
            self.adapter.job.logger.error(
                f"Multiple Locations found with the name {self.location}, unable to "
                f"Retrieve the VLAN named {self.name} to perform updates"
            )
            return None
        except NautobotLocation.DoesNotExist:
            self.adapter.job.logger.error(
                f"Could not find a Location with the name {self.location}, unable to "
                f"Retrieve the VLAN named {self.name} to perform updates"
            )
            return None
        try:
            vlan = VLAN.objects.get(name=self.name, vid=self.vid, location=location_obj)
        except VLAN.MultipleObjectsReturned:
            self.adapter.job.logger.error(
                f"Multiple VLANs found with a name {self.name} and VLAN ID {self.vid} "
                f"at a Location named {self.location}, unable to perform updates"
            )
            return None
        except VLAN.DoesNotExist:
            self.adapter.job.logger.error(
                f"Could not find a VLAN named {self.name} and VLAN ID {self.vid} "
                f"at a Location named {self.location}, unable to perform updates"
            )
            return None
        if attrs.get("status") == "Active":
            if not vlan.status == "Active":
                vlan.status = tonb_nbutils.get_or_create_status_object("Active", ColorChoices.COLOR_GREEN)
            vlan.tags.remove(self.adapter.safe_delete_tag)
        if attrs.get("description"):
            vlan.description = attrs.get("description")
        try:
            tonb_nbutils.tag_object(nautobot_object=vlan, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError):
            self.adapter.job.logger.warning(
                f"Unable to perform a validated_save() on VLAN {self.name} with an ID of {vlan.id}"
            )
            return None
        return super().update(attrs)


class Cable(DiffSyncExtras):
    """Cable model.

    Neither system has a stable identifier for a link, so a Cable is identified by its two endpoints
    ordered by `cables.canonical_endpoints`.
    """

    _modelname = "cable"
    _identifiers = (
        "termination_a_device",
        "termination_a_name",
        "termination_b_device",
        "termination_b_name",
    )
    _attributes = ("status",)

    termination_a_device: str
    termination_a_name: str
    termination_b_device: str
    termination_b_name: str
    status: str
    cable_pk: Optional[UUID] = None

    @staticmethod
    def describe(ids) -> str:
        """Render a link's endpoints for log messages."""
        return (
            f"{ids['termination_a_device']}:{ids['termination_a_name']} <-> "
            f"{ids['termination_b_device']}:{ids['termination_b_name']}"
        )

    @staticmethod
    def resolve_interfaces(adapter, ids):
        """Return the two Nautobot Interfaces a link terminates on, or (None, None) if either is missing.

        Cables keep the per-object write path, so this reads its Interfaces back from the database.
        The Devices and Interfaces a link terminates on are created earlier in the same sync, and in
        bulk mode that means queued rather than written, so anything still queued is written first.
        """
        if adapter.pending_writes is not None:
            adapter.flush_pending_writes()
        job_logger = adapter.job.logger
        tagged_only = adapter.sync_ipfabric_tagged_only
        interface_a = tonb_nbutils.get_tagged_interface(
            ids["termination_a_device"], ids["termination_a_name"], logger=job_logger, tagged_only=tagged_only
        )
        interface_b = tonb_nbutils.get_tagged_interface(
            ids["termination_b_device"], ids["termination_b_name"], logger=job_logger, tagged_only=tagged_only
        )
        if not interface_a or not interface_b:
            return None, None
        return interface_a, interface_b

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create a Cable in Nautobot between the two Interfaces it terminates on."""
        job_logger = adapter.job.logger
        link = cls.describe(ids)
        interface_a, interface_b = cls.resolve_interfaces(adapter, ids)
        if not interface_a:
            job_logger.warning(f"Unable to create a Cable for {link} because an Interface could not be retrieved")
            return None

        existing_cable = interface_a.cable
        if existing_cable and tonb_cables.cable_connects(existing_cable, interface_a, interface_b):
            # Already recorded, so correct it in place rather than replacing it.
            if not tonb_cables.update_cable_status(existing_cable, attrs["status"], logger=job_logger):
                return None
            return super().create(ids=ids, adapter=adapter, attrs=attrs)

        if not cls.release_interfaces(adapter, link, interface_a, interface_b):
            return None
        if tonb_cables.create_cable(interface_a, interface_b, attrs["status"], logger=job_logger):
            return super().create(ids=ids, adapter=adapter, attrs=attrs)
        return None

    @classmethod
    def release_interfaces(cls, adapter, link, *interfaces) -> bool:
        """Remove any Cable occupying an Interface this link needs, returning False on a conflict.

        Nautobot permits one Cable per Interface, so a link that has moved cannot be recorded until
        the Cable holding its Interface is gone. Safe delete mode removes nothing, so there the
        conflict is reported and left for an operator instead.
        """
        for interface in interfaces:
            cable = interface.cable
            if cable is None:
                continue
            if cls.safe_delete_mode:
                adapter.job.logger.warning(
                    f"Not creating a Cable for {link} because {interface.device.name}:{interface.name} is already "
                    f"cabled and Safe Delete Mode will not remove the existing Cable with an ID of {cable.id}"
                )
                return False
            adapter.job.logger.info(
                f"Removing the Cable with an ID of {cable.id} from {interface.device.name}:{interface.name} "
                f"so that {link} can be recorded"
            )
            try:
                cable.delete()
            except (ProtectedError, DjangoBaseDBError) as err:
                adapter.job.logger.error(
                    f"Unable to remove the Cable with an ID of {cable.id} from "
                    f"{interface.device.name}:{interface.name}, so {link} will not be created. Error: {err}"
                )
                return False
        return True

    def retrieve_cable(self):
        """Return the Nautobot Cable this model represents, or None when it is no longer present."""
        if self.cable_pk:
            # Recorded by the Nautobot adapter while loading, so the endpoints need not be walked again.
            return NautobotCable.objects.filter(pk=self.cable_pk).select_related("status").first()
        interface_a, interface_b = self.resolve_interfaces(self.adapter, self.get_identifiers())
        if not interface_a:
            return None
        cable = interface_a.cable
        if cable and tonb_cables.cable_connects(cable, interface_a, interface_b):
            return cable
        return None

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):
        """Update a Cable's Status in Nautobot."""
        link = self.describe(self.get_identifiers())
        cable = self.retrieve_cable()
        if cable is None:
            self.adapter.job.logger.error(f"Unable to find a Cable for {link} to update")
            return None
        status = attrs.get("status")
        if status:
            if not tonb_cables.update_cable_status(cable, status, logger=self.adapter.job.logger):
                return None
            if status == DEFAULT_CABLE_STATUS:
                cable.tags.remove(self.adapter.safe_delete_tag)
        return super().update(attrs)

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete a Cable in Nautobot."""
        link = self.describe(self.get_identifiers())
        cable = self.retrieve_cable()
        if cable is None:
            self.adapter.job.logger.info(f"No Cable for {link} remains in Nautobot, so there is nothing to delete")
            return super().delete()
        if self.safe_delete_mode:
            self.safe_delete(cable, SAFE_DELETE_CABLE_STATUS, self.adapter.safe_delete_tag)
        else:
            # Removed here rather than queued for the adapter's `sync_complete()` like the other
            # models: nothing depends on a Cable, and a queued one would still be holding an
            # Interface that a relocated link needs earlier in the same sync.
            try:
                cable.delete()
            except (ProtectedError, DjangoBaseDBError) as err:
                self.adapter.job.logger.error(f"Unable to delete the Cable for {link}. Error: {err}")
                return None
        return super().delete()


Location.model_rebuild()
Device.model_rebuild()
Interface.model_rebuild()
Vlan.model_rebuild()
Cable.model_rebuild()
