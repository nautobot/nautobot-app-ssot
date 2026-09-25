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
    Interface as NautobotInterface,
)
from nautobot.dcim.models import (
    Location as NautobotLocation,
)
from nautobot.extras.models import Tag
from nautobot.ipam.models import VLAN, IPAddress
from nautobot.ipam.models import RouteTarget as NautobotRouteTarget

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
    SAFE_DELETE_VRF_STATUS,
    SYNC_IPF_DEV_TYPE_TO_ROLE,
)

logger = logging.getLogger(__name__)


def resolve_location(adapter, location_name: str, location_id: Optional[str] = None):
    """Return the Nautobot Location a synced object belongs to, creating one only if this run may."""
    if adapter.may_create("locations"):
        return tonb_nbutils.get_or_create_location_object(
            location_name=location_name,
            location_id=location_id,
            logger=adapter.job.logger,
            pending=adapter.pending,
        )
    return tonb_nbutils.get_location_object(location_name, logger=adapter.job.logger)


def resolve_manufacturer(adapter, vendor_name: str):
    """Return the Nautobot Manufacturer for a vendor IP Fabric reports, creating one only if this run may."""
    if adapter.may_create("manufacturers"):
        return tonb_nbutils.get_or_create_manufacturer_object(vendor_name, logger=adapter.job.logger)
    return tonb_nbutils.get_manufacturer_object(vendor_name, logger=adapter.job.logger)


def resolve_device_type(adapter, device_type_name: str, vendor_name: str):
    """Return the Nautobot DeviceType for a model IP Fabric reports.

    An existing DeviceType is used either way. Creating one needs a Manufacturer, so that is resolved
    through its own controls first: a sync told not to add vendors must not add one to add a model.
    """
    existing = tonb_nbutils.get_device_type_object(device_type_name, logger=adapter.job.logger)
    if existing or not adapter.may_create("device_types"):
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
    """Return the Nautobot Role for a device type IP Fabric reports, creating one only if this run may."""
    if adapter.may_create("roles"):
        return tonb_nbutils.get_or_create_device_role_object(
            role_name=role_name,
            role_color=DEFAULT_DEVICE_ROLE_COLOR,
            logger=adapter.job.logger,
        )
    return tonb_nbutils.get_device_role_object(role_name, logger=adapter.job.logger)


def resolve_status(adapter, status_name: str, status_color: str = ColorChoices.COLOR_GREY, **kwargs):
    """Return the Nautobot Status of the given name, creating one only if this run may."""
    return tonb_nbutils.get_or_create_status_object(
        status_name,
        status_color=status_color,
        create=adapter.may_create("statuses"),
        logger=adapter.job.logger,
        **kwargs,
    )


def resolve_virtual_chassis(adapter, name: str):
    """Return the Nautobot VirtualChassis of the given name, creating one only if this run may."""
    if adapter.may_create("virtual_chassis"):
        return tonb_nbutils.get_or_create_virtual_chassis_object(name, logger=adapter.job.logger)
    return tonb_nbutils.get_virtual_chassis_object(name, logger=adapter.job.logger)


def resolve_platform(adapter, platform_name: str, manufacturer_object):
    """Return the Nautobot Platform for a family IP Fabric reports.

    Creates one only if this run may, and only when a Manufacturer to file it under was resolved.
    Otherwise the Platform is matched on its name alone, since the system that owns it decides its
    Manufacturer.
    """
    if not adapter.may_create("platforms"):
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
        if adapter.pending is not None:
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
                # Created whatever this run may create otherwise. Safe Delete Mode's statuses are
                # the integration's own vocabulary rather than anything IP Fabric reported, and
                # refusing to create one would leave a record neither deleted nor marked, which is
                # the one outcome Safe Delete Mode exists to prevent.
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
                    location.status = resolve_status(self.adapter, active_status, ColorChoices.COLOR_GREEN)
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
            # Only while this run may create Roles: the custom field records what IP Fabric called
            # the role, so writing it claims the Role for this sync. Strict, the Role was matched on
            # its name and belongs to whatever system set that name, which is exactly what strictness
            # refuses to take over -- as does deselecting Roles altogether.
            if adapter.may_create("roles") and device_role_object.cf.get("ipfabric_type") != role_name:
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
        device_status_object = resolve_status(adapter, DEFAULT_DEVICE_STATUS, DEFAULT_DEVICE_STATUS_COLOR)
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
            pending = adapter.pending
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
                    new_device, _ = NautobotDevice.objects.get_or_create(
                        defaults={"platform": platform_object}, **lookup
                    )
                    queue_new = False
                else:
                    try:
                        new_device = NautobotDevice.objects.get(**lookup)
                        queue_new = False
                    except NautobotDevice.DoesNotExist:
                        new_device = NautobotDevice(platform=platform_object, **lookup)
                        queue_new = True
            except NautobotDevice.MultipleObjectsReturned:
                adapter.job.logger.error(
                    f"Multiple Devices returned with name {device_name} at Location {location_name}"
                )
            except (DjangoBaseDBError, ValidationError):
                adapter.job.logger.error(
                    f"Unable to create a new Device named {device_name} at Location {location_name}"
                )
            else:
                if queue_new:
                    tonb_nbutils.queue_new_object(pending, new_device, key=device_name)
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
                        vc = resolve_virtual_chassis(adapter, vc_name)
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
                    _device.status = resolve_status(self.adapter, "Active", ColorChoices.COLOR_GREEN)
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
                    vc = resolve_virtual_chassis(self.adapter, vc_name)
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
        "status",
    )
    _children = {"interface_address": "addresses"}

    name: str
    device_name: str
    description: Optional[str] = None
    enabled: Optional[bool] = None
    mac_address: Optional[str] = None
    mtu: Optional[int] = None
    type: Optional[str] = None
    mgmt_only: Optional[bool] = None
    status: str
    addresses: List["InterfaceAddress"] = []

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create interface in Nautobot under its parent device."""
        device_name = ids["device_name"]
        interface_name = ids["name"]
        # A Device queued earlier in this run is not in the database yet, so it is looked for there
        # first. `get_syncable_device` is cached, so it is asked second rather than taught about the
        # queue.
        device_obj = None
        if adapter.pending is not None:
            device_obj = adapter.pending.find(NautobotDevice, device_name)
        device_obj = device_obj or tonb_nbutils.get_syncable_device(
            device_name, tagged_only=adapter.sync_ipfabric_tagged_only
        )
        if not device_obj:
            adapter.job.logger.warning(
                f"Unable to create an Interface with the name {interface_name} because of a failure "
                f"to get a Device named {device_name}"
            )
            return None
        if not attrs.get("mac_address"):
            attrs["mac_address"] = DEFAULT_INTERFACE_MAC
        # Addresses are written by `InterfaceAddress`, each as its own child of this Interface, so
        # nothing is assigned here.
        interface_obj = tonb_nbutils.create_interface(
            create_statuses=adapter.may_create("statuses"),
            device_obj=device_obj,
            interface_details={**ids, **attrs},
            logger=adapter.job.logger,
            pending=adapter.pending,
        )
        if not interface_obj:
            adapter.job.logger.warning(
                f"Unable to get or create an Interface named {interface_name} on a Device named {device_name}"
            )
            return None
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

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
                # The addresses on it are not touched here. Each is an `InterfaceAddress` child of
                # this Interface, so DiffSync deletes them in their own right, and that model is
                # what knows to leave an address a second Interface also holds.
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
    def update(self, attrs):
        """Update Interface object in Nautobot."""
        device = tonb_nbutils.get_syncable_device(self.device_name, tagged_only=self.adapter.sync_ipfabric_tagged_only)
        if device:
            return_super = True
            # Every Interface of the Device at once, so a Device with many of them changing costs
            # one lookup rather than one each. Nautobot makes `(device, name)` unique, so there is
            # no ambiguous match to report.
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


class InterfaceAddress(DiffSyncExtras):
    """An IP Address configured on a Device Interface.

    Its own model rather than a field of the Interface, because an Interface can carry several: a
    secondary address, an FHRP virtual address, and IPv6 alongside IPv4. As a model each one diffs on
    its own, so an Interface gaining a third address reports that address rather than its whole set,
    and one IP Fabric stops reporting is removed without touching the rest.

    Identified by host rather than by address. Nautobot makes an address unique within its parent
    Prefix and the mask is the attribute that changes, so keying on the mask as well would report a
    corrected mask as one address replacing another.
    """

    _modelname = "interface_address"
    _identifiers = ("device_name", "interface_name", "host")
    _attributes = ("mask_length", "is_primary", "status")

    device_name: str
    interface_name: str
    host: str
    mask_length: int
    is_primary: bool = False
    status: str = "Active"

    @staticmethod
    def find_interface(adapter, device_name: str, interface_name: str):
        """Return the `(Device, Interface)` to hang the address off, reporting whichever is missing.

        The Interface may have been queued earlier in this run rather than written, so the queue is
        asked first, as `Interface.create` asks it for its Device. A queued Interface is keyed on its
        Device's primary key, so the Device is resolved first in that case.

        Otherwise it is read afresh. The by Device lookup a delete uses is cached, so it would see
        neither an Interface this run created nor an address written onto one it did.
        """
        if adapter.pending is not None:
            device = adapter.pending.find(NautobotDevice, device_name) or tonb_nbutils.get_syncable_device(
                device_name, tagged_only=adapter.sync_ipfabric_tagged_only
            )
            if device is not None:
                queued = adapter.pending.find(NautobotInterface, (device.pk, interface_name))
                if queued is not None:
                    return device, queued
        interface = tonb_nbutils.get_tagged_interface(
            device_name,
            interface_name,
            tagged_only=adapter.sync_ipfabric_tagged_only,
            logger=adapter.job.logger,
        )
        if interface is None:
            return None, None
        return interface.device, interface

    @staticmethod
    def primary_field(address_object) -> str:
        """Return the Device field that records an address of this version as primary."""
        return "primary_ip4" if address_object.ip_version == 4 else "primary_ip6"

    @classmethod
    def clear_primary(cls, adapter, device, address_object) -> None:
        """Stop the Device recording the address as its primary one.

        Cleared only where the Device still points at this address. Whichever address becomes
        primary instead is a different model, and DiffSync does not order the two, so a demotion
        that cleared the field outright could undo a promotion already applied. Keyed on identity,
        the two settle in either order: applied after the promotion this is a no-op, and applied
        before it the promotion writes the field again.
        """
        field = cls.primary_field(address_object)
        if getattr(device, f"{field}_id") != address_object.pk:
            return
        if adapter.pending is None:
            setattr(device, field, None)
            try:
                device.validated_save()
            except (DjangoBaseDBError, ValidationError):
                adapter.job.logger.error(
                    f"Unable to stop recording {address_object.address} as the {field} of Device "
                    f"named {device.name}"
                )
            return
        adapter.pending.defer_update(device, {field: None})

    @classmethod
    def assign_primary(cls, adapter, device, address_object) -> None:
        """Record the address as the Device's primary one for its IP version.

        A validated save, so the refusal is reported rather than written. It validates the whole
        Device, so a Device this sync deliberately wrote despite `Device.clean()` — one whose
        Platform names a different Manufacturer to its DeviceType — is refused here for a reason
        that has nothing to do with the address, and keeps whatever primary it had.
        """
        field = cls.primary_field(address_object)
        if adapter.pending is None:
            setattr(device, field, address_object)
            try:
                device.validated_save()
            except (DjangoBaseDBError, ValidationError):
                adapter.job.logger.error(
                    f"Unable to record {address_object.address} as the {field} of Device named {device.name}"
                )
            return
        # Deferred for the same reason `Interface.create` defers it: the address is only queued, and
        # the Device may be too, so its insert would carry a foreign key to a row not yet written.
        adapter.pending.defer_update(device, {field: address_object})

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create the address in Nautobot and assign it to its Interface."""
        device, interface = cls.find_interface(adapter, ids["device_name"], ids["interface_name"])
        if interface is None:
            return None
        address_object = tonb_nbutils.create_ip(
            ip_address=ids["host"],
            mask_length=attrs["mask_length"],
            status=attrs.get("status", "Active"),
            object_pk=interface,
            logger=adapter.job.logger,
            pending=adapter.pending,
        )
        if address_object is None:
            adapter.job.logger.warning(
                f"Unable to write an IPAddress of {ids['host']}/{attrs['mask_length']} for Interface "
                f"named {ids['interface_name']} on Device named {ids['device_name']}"
            )
            return None
        if attrs.get("is_primary"):
            cls.assign_primary(adapter, device, address_object)
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):
        """Correct the mask IP Fabric reports for the address, and whether it is the Device's primary."""
        device, interface = self.find_interface(self.adapter, self.device_name, self.interface_name)
        if interface is None:
            return None
        try:
            address_object = interface.ip_addresses.get(host=self.host)
        except IPAddress.DoesNotExist:
            self.adapter.job.logger.error(
                f"Unable to find an IPAddress of {self.host} on Interface named {self.interface_name} "
                f"on Device named {self.device_name} to update"
            )
            return None
        except IPAddress.MultipleObjectsReturned:
            self.adapter.job.logger.error(
                f"Multiple IPAddresses of {self.host} on Interface named {self.interface_name} on "
                f"Device named {self.device_name}, so none is updated"
            )
            return None
        if "mask_length" in attrs:
            address_object.mask_length = attrs["mask_length"]
            try:
                address_object.validated_save()
            except (DjangoBaseDBError, ValidationError):
                self.adapter.job.logger.error(
                    f"Unable to change the mask of IPAddress {self.host} to /{attrs['mask_length']} on "
                    f"Interface named {self.interface_name} on Device named {self.device_name}"
                )
                return None
        if "is_primary" in attrs:
            # `in attrs` rather than a truth test: an address that stops being primary reports
            # `False`, which is a value to act on rather than an attribute left unset.
            if attrs["is_primary"]:
                self.assign_primary(self.adapter, device, address_object)
            else:
                self.clear_primary(self.adapter, device, address_object)
        return super().update(attrs)

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Remove the address IP Fabric no longer reports for the Interface.

        Deleted only where no other Interface holds it. An address IP Fabric reports on two
        Interfaces is one row in Nautobot, and removing it for one would take it from both.
        """
        _device, interface = self.find_interface(self.adapter, self.device_name, self.interface_name)
        if interface is None:
            return None
        address_object = interface.ip_addresses.filter(host=self.host).first()
        if address_object is None:
            self.adapter.job.logger.warning(
                f"Unable to find an IPAddress of {self.host} on Interface named {self.interface_name} "
                f"on Device named {self.device_name} to delete"
            )
            return None
        if any(other.id != interface.id for other in address_object.interfaces.all()):
            interface.ip_addresses.remove(address_object)
            return super().delete()
        self.safe_delete(address_object, SAFE_DELETE_IPADDRESS_STATUS, self.adapter.safe_delete_tag)
        return super().delete()


class Vlan(DiffSyncExtras):
    """VLAN model."""

    _modelname = "vlan"
    _identifiers = ("vid", "location")
    _shortname = ("vid",)
    _attributes = ("name", "status", "description")

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
        vlan_id = ids["vid"]
        vlan_name = attrs["name"]
        # A Location queued earlier in this run is not in the database yet, so it is looked for
        # there first. Falls through to the database, which is where it is on any other run.
        location = None
        if adapter.pending is not None:
            location = adapter.pending.find(NautobotLocation, location_name)
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
            # The Location's VLAN Group is what makes one VLAN ID mean one VLAN there, which is
            # what this model identifies a VLAN by.
            vlan_group = tonb_nbutils.get_vlan_group_for_location(
                location,
                create=adapter.may_create("vlan_groups"),
                logger=adapter.job.logger,
            )
            vlan = tonb_nbutils.create_vlan(
                vlan_name=vlan_name,
                vlan_id=vlan_id,
                vlan_status=status,
                location_obj=location,
                description=description,
                logger=adapter.job.logger,
                pending=adapter.pending,
                vlan_group=vlan_group,
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
            vlan = VLAN.objects.get(pk=self.vlan_pk)
        except VLAN.DoesNotExist:
            self.adapter.job.logger.error(
                f"Could not find a VLAN with VLAN ID {self.vid} at a Location named {self.location} "
                f"and an ID of {self.vlan_pk}, unable to perform updates"
            )
            return None
        if "name" in attrs:
            vlan.name = attrs["name"]
        if attrs.get("status") == "Active":
            if not vlan.status == "Active":
                vlan.status = resolve_status(self.adapter, "Active", ColorChoices.COLOR_GREEN)
            vlan.tags.remove(self.adapter.safe_delete_tag)
        if attrs.get("description"):
            vlan.description = attrs.get("description")
        try:
            tonb_nbutils.tag_object(nautobot_object=vlan, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError):
            self.adapter.job.logger.warning(
                f"Unable to perform a validated_save() on VLAN {vlan.name} with an ID of {vlan.id}"
            )
            return None
        return super().update(attrs)


class RouteTarget(DiffSyncExtras):
    """Route Target model.

    Carries no attributes, only its identity. IP Fabric reports a route target as the value itself
    and nothing else, so there is never anything to update: a target either exists in Nautobot or it
    does not. Nautobot's own description and tenant are left alone, which lets an operator annotate
    one without the sync overwriting the annotation on the next run.

    Top level and ahead of VRFs, so the targets a VRF names exist by the time it is written.
    """

    _modelname = "route_target"
    _identifiers = ("name",)

    name: str

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create a Route Target in Nautobot."""
        if tonb_nbutils.create_route_target(ids["name"], logger=adapter.job.logger) is None:
            return None
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete a Route Target in Nautobot."""
        route_target = NautobotRouteTarget.objects.filter(name=self.name).first()
        if route_target is None:
            self.adapter.job.logger.error("Unable to find a Route Target named %s to delete", self.name)
            return None
        # No Status to move it to, so a safe delete marks it with the Tag alone.
        self.safe_delete(route_target, None, self.adapter.safe_delete_tag)
        return super().delete()


class Vrf(DiffSyncExtras):
    """VRF model.

    Top level rather than a child of a Location, because IP Fabric reports a VRF as network wide:
    the same routing instance is configured on devices at many sites, and Nautobot holds one VRF for
    it. Which devices carry it is a separate relationship, not an attribute of the VRF.
    """

    _modelname = "vrf"
    _identifiers = ("name",)
    _attributes = ("rd", "status", "import_targets", "export_targets", "conflict")

    name: str
    rd: Optional[str] = None
    status: str
    # Sorted by both adapters, so that two reports of one set do not diff on ordering alone.
    import_targets: List[str] = []
    export_targets: List[str] = []
    conflict: str = ""

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Create a VRF in Nautobot's Global Namespace."""
        name = ids["name"]
        if name in adapter.ambiguous_vrf_names:
            adapter.job.logger.error(
                "Not creating a VRF named %s, as the Global Namespace already holds more than one "
                "VRF of that name and IP Fabric reports nothing that tells them apart",
                name,
            )
            return None
        vrf_obj = tonb_nbutils.create_vrf(
            name=name,
            rd=attrs.get("rd"),
            vrf_status=attrs["status"],
            conflict=attrs.get("conflict", ""),
            logger=adapter.job.logger,
            pending=adapter.pending,
        )
        if vrf_obj is None:
            return None
        tonb_nbutils.set_route_targets(
            vrf_obj,
            attrs.get("import_targets") or (),
            attrs.get("export_targets") or (),
            logger=adapter.job.logger,
            pending=adapter.pending,
        )
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):
        """Update a VRF in Nautobot."""
        vrf_obj = tonb_nbutils.get_vrf(self.name, logger=self.adapter.job.logger)
        if vrf_obj is None:
            self.adapter.job.logger.error("Unable to find a VRF named %s to update", self.name)
            return None
        if "rd" in attrs:
            # Emptied rather than left alone when IP Fabric no longer reports one, so that a route
            # distinguisher removed from the network does not survive in Nautobot indefinitely.
            vrf_obj.rd = attrs["rd"] or None
        if "conflict" in attrs:
            vrf_obj.cf[tonb_nbutils.VRF_CONFLICT_CF_NAME] = attrs["conflict"]
        status = attrs.get("status")
        if status == "Active":
            if vrf_obj.status is None or vrf_obj.status.name != status:
                vrf_obj.status = tonb_nbutils.get_or_create_status_object(
                    status, ColorChoices.COLOR_GREEN, app_label="ipam", model="vrf"
                )
            vrf_obj.tags.remove(self.adapter.safe_delete_tag)
        try:
            # Calls validated_save() on the object.
            tonb_nbutils.tag_object(nautobot_object=vrf_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError) as err:
            self.adapter.job.logger.error("Unable to update the VRF named %s with %s. Error: %s", self.name, attrs, err)
            return None
        if "import_targets" in attrs or "export_targets" in attrs:
            # Read from the model for whichever of the two did not change, since both are written
            # together and `attrs` carries only what differs.
            tonb_nbutils.set_route_targets(
                vrf_obj,
                attrs.get("import_targets", self.import_targets),
                attrs.get("export_targets", self.export_targets),
                logger=self.adapter.job.logger,
            )
        return super().update(attrs)

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete a VRF in Nautobot."""
        vrf_obj = tonb_nbutils.get_vrf(self.name, logger=self.adapter.job.logger)
        if vrf_obj is None:
            self.adapter.job.logger.error("Unable to find a VRF named %s to delete", self.name)
            return None
        self.safe_delete(
            vrf_obj,
            SAFE_DELETE_VRF_STATUS,
            self.adapter.safe_delete_tag,
        )
        return super().delete()


class VrfDeviceAssignment(DiffSyncExtras):
    """The record that a Device carries a VRF.

    A model of its own rather than a list of VRFs on the Device, because that is the shape of the
    data at both ends: IP Fabric reports one row per device per VRF, and Nautobot holds one
    `VRFDeviceAssignment` per pair. Each therefore diffs alone, so a Device that picks up one more
    VRF reports that assignment rather than its whole set.

    Carries no attributes. The assignment's own route distinguisher and name are inherited from the
    VRF when it is written, so there is nothing about a pair that can change without the pair itself
    changing.

    Top level and last, since it needs both the VRF and the Device to have been written.
    """

    _modelname = "vrf_device_assignment"
    _identifiers = ("vrf_name", "device_name")

    vrf_name: str
    device_name: str

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Assign a VRF to a Device in Nautobot."""
        assignment = tonb_nbutils.create_vrf_device_assignment(
            vrf_name=ids["vrf_name"],
            device_name=ids["device_name"],
            tagged_only=adapter.sync_ipfabric_tagged_only,
            logger=adapter.job.logger,
            pending=adapter.pending,
        )
        if assignment is None:
            return None
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Remove a VRF from a Device in Nautobot."""
        assignment = tonb_nbutils.get_vrf_device_assignment(self.vrf_name, self.device_name)
        if assignment is None:
            self.adapter.job.logger.error(
                "Unable to find the VRF named %s on the Device named %s to remove it",
                self.vrf_name,
                self.device_name,
            )
            return None
        # Neither a Status nor a Tag to mark, so Safe Delete Mode leaves the assignment in place.
        self.safe_delete(assignment, None, None)
        return super().delete()


class InterfaceVrf(DiffSyncExtras):
    """The VRF an Interface belongs to.

    A model of its own rather than an attribute of the Interface, because of when it can be
    written rather than where it belongs: Nautobot refuses an Interface a VRF that is not assigned
    to the Interface's Device, and those assignments cannot exist until every Device has been
    written, which is after its Interfaces have been. Kept top level and last, it is written once
    both are there.

    Only Interfaces that are in a VRF carry one of these, on either side. An Interface IP Fabric
    stops reporting a VRF for is therefore a delete, which takes the Interface out of the VRF
    rather than removing anything; the Interface and the VRF both remain.
    """

    _modelname = "interface_vrf"
    _identifiers = ("device_name", "interface_name")
    _attributes = ("vrf_name",)

    device_name: str
    interface_name: str
    vrf_name: str

    @classmethod
    @tonb_nbutils.deferred_change_logging()
    def create(cls, adapter, ids, attrs):
        """Put an Interface in a VRF in Nautobot."""
        if not tonb_nbutils.set_interface_vrf(
            device_name=ids["device_name"],
            interface_name=ids["interface_name"],
            vrf_name=attrs["vrf_name"],
            tagged_only=adapter.sync_ipfabric_tagged_only,
            logger=adapter.job.logger,
            pending=adapter.pending,
        ):
            return None
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    @tonb_nbutils.deferred_change_logging()
    def update(self, attrs):
        """Move an Interface from one VRF to another in Nautobot."""
        if not tonb_nbutils.set_interface_vrf(
            device_name=self.device_name,
            interface_name=self.interface_name,
            vrf_name=attrs["vrf_name"],
            tagged_only=self.adapter.sync_ipfabric_tagged_only,
            logger=self.adapter.job.logger,
            pending=self.adapter.pending,
        ):
            return None
        return super().update(attrs)

    @tonb_nbutils.deferred_change_logging()
    def delete(self) -> Optional["DiffSyncModel"]:
        """Take an Interface out of its VRF in Nautobot.

        Nothing is deleted, so Safe Delete Mode does not apply: the Interface and the VRF both
        remain, and what goes is the reference between them, which is an attribute of the Interface.
        """
        if not tonb_nbutils.set_interface_vrf(
            device_name=self.device_name,
            interface_name=self.interface_name,
            vrf_name=None,
            tagged_only=self.adapter.sync_ipfabric_tagged_only,
            logger=self.adapter.job.logger,
            pending=self.adapter.pending,
        ):
            return None
        return super().delete()


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
        if adapter.pending is not None:
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
            if not tonb_cables.update_cable_status(
                existing_cable,
                attrs["status"],
                logger=job_logger,
                create_statuses=adapter.may_create("statuses"),
            ):
                return None
            return super().create(ids=ids, adapter=adapter, attrs=attrs)

        if not cls.release_interfaces(adapter, link, interface_a, interface_b):
            return None
        if tonb_cables.create_cable(
            interface_a,
            interface_b,
            attrs["status"],
            logger=job_logger,
            create_statuses=adapter.may_create("statuses"),
        ):
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
            if not tonb_cables.update_cable_status(
                cable,
                status,
                logger=self.adapter.job.logger,
                create_statuses=self.adapter.may_create("statuses"),
            ):
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
