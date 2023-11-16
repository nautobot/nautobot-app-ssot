# pylint: disable=duplicate-code
# Ignore return statements for updates and deletes, #  pylint:disable=R1710
# Ignore too many args #  pylint:disable=too-many-locals
"""DiffSyncModel subclasses for Nautobot-to-IPFabric data sync."""
from typing import Any, ClassVar, List, Optional
from uuid import UUID
import logging

from diffsync import DiffSyncModel
from django.core.exceptions import ValidationError
from django.db.models import Q
from nautobot.dcim.models import Device as NautobotDevice
from nautobot.dcim.models import DeviceType, Location as NautobotLocation
from nautobot.extras.models import Role, Tag
from nautobot.extras.models.statuses import Status
from nautobot.ipam.models import VLAN
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
        tonb_nbutils.create_location(location_name=ids["name"], location_id=attrs["site_id"])
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete Location in Nautobot."""
        location = NautobotLocation.objects.get(name=self.name)

        self.safe_delete(
            location,
            SAFE_DELETE_LOCATION_STATUS,
        )
        return super().delete()

    def update(self, attrs):
        """Update Location Object in Nautobot."""
        location = NautobotLocation.objects.get(name=self.name)
        if attrs.get("site_id"):
            location.custom_field_data["ipfabric_site_id"] = attrs.get("site_id")
            location.validated_save()
        if attrs.get("status") == "Active":
            safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
            if not location.status == "Active":
                location.status = Status.objects.get(name="Active")
            device_tags = location.tags.filter(pk=safe_delete_tag.pk)
            if device_tags.exists():
                location.tags.remove(safe_delete_tag)
        tonb_nbutils.tag_object(nautobot_object=location, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        return super().update(attrs)


class Device(DiffSyncExtras):
    """Device model."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("location_name", "model", "vendor", "serial_number", "role", "status")
    _children = {"interface": "interfaces"}

    name: str
    location_name: Optional[str]
    model: Optional[str]
    vendor: Optional[str]
    serial_number: Optional[str]
    role: Optional[str]
    status: Optional[str]

    mgmt_address: Optional[str]

    interfaces: List["Interface"] = list()  # pylint: disable=use-list-literal

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device in Nautobot under its parent location."""
        # Get DeviceType
        device_type_filter = DeviceType.objects.filter(model=attrs["model"])
        if device_type_filter.exists():
            device_type_object = device_type_filter.first()
        else:
            device_type_object = tonb_nbutils.create_device_type_object(
                device_type=attrs["model"], vendor_name=attrs["vendor"]
            )
        # Get Role, update if missing cf and create otherwise
        role_name = attrs.get("role", DEFAULT_DEVICE_ROLE)
        device_role_filter = Role.objects.filter(name=role_name)
        if device_role_filter.exists():
            device_role_object = device_role_filter.first()
            device_role_object.cf["ipfabric_type"] = role_name
            device_role_object.validated_save()
        else:
            device_role_object = tonb_nbutils.get_or_create_device_role_object(
                role_name=role_name, role_color=DEFAULT_DEVICE_ROLE_COLOR
            )
        # Get Status
        device_status_filter = Status.objects.filter(name=DEFAULT_DEVICE_STATUS)
        if device_status_filter.exists():
            device_status_object = device_status_filter.first()
        else:
            device_status_object = tonb_nbutils.create_status(DEFAULT_DEVICE_STATUS, DEFAULT_DEVICE_STATUS_COLOR)
        # Get Location
        location_object_filter = NautobotLocation.objects.filter(name=attrs["location_name"])
        if location_object_filter.exists():
            location = location_object_filter.first()
        else:
            location = tonb_nbutils.create_location(attrs["location_name"])

        new_device, _ = NautobotDevice.objects.get_or_create(
            name=ids["name"],
            serial=attrs.get("serial_number", ""),
            status=device_status_object,
            device_type=device_type_object,
            role=device_role_object,
            location=location,
        )
        try:
            # Validated save happens inside of tag_objet
            tonb_nbutils.tag_object(nautobot_object=new_device, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except ValidationError as error:
            message = f"Unable to create device: {ids['name']}. A validation error occured. Enable debug for more information."
            if diffsync.job.debug:
                logger.debug(error)
            logger.error(message)

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete device in Nautobot."""
        try:
            device_object = NautobotDevice.objects.get(name=self.name)
            self.safe_delete(
                device_object,
                SAFE_DELETE_DEVICE_STATUS,
            )
            return super().delete()
        except NautobotDevice.DoesNotExist:
            logger.warning(f"Unable to match device by name, {self.name}")

    def update(self, attrs):
        """Update devices in Nautobot based on Source."""
        try:
            _device = NautobotDevice.objects.get(name=self.name)
            if attrs.get("status") == "Active":
                safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
                if not _device.status == "Active":
                    _device.status = Status.objects.get(name="Active")
                device_tags = _device.tags.filter(pk=safe_delete_tag.pk)
                if device_tags.exists():
                    _device.tags.remove(safe_delete_tag)
            # TODO: If only the "model" is changing, the "vendor" is not available
            if attrs.get("model"):
                device_type_object = tonb_nbutils.create_device_type_object(
                    device_type=attrs["model"], vendor_name=attrs["vendor"]
                )
                _device.type = device_type_object
            if attrs.get("location_name"):
                location = tonb_nbutils.create_location(attrs["location_name"])
                _device.location = location
            if attrs.get("serial_number"):
                _device.serial = attrs.get("serial_number")
            if attrs.get("role"):
                device_role_object = tonb_nbutils.get_or_create_device_role_object(
                    role_name=attrs.get("role", DEFAULT_DEVICE_ROLE), role_color=DEFAULT_DEVICE_ROLE_COLOR
                )
                _device.role = device_role_object
            tonb_nbutils.tag_object(nautobot_object=_device, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            # Call the super().update() method to update the in-memory DiffSyncModel instance
            return super().update(attrs)
        except NautobotDevice.DoesNotExist:
            logger.warning(f"Unable to match device by name, {self.name}")


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
        ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
        device_obj = NautobotDevice.objects.filter(Q(name=ids["device_name"]) & Q(tags__name=ssot_tag.name)).first()

        if not attrs.get("mac_address"):
            attrs["mac_address"] = DEFAULT_INTERFACE_MAC
        interface_obj = tonb_nbutils.create_interface(
            device_obj=device_obj,
            interface_details={**ids, **attrs},
        )
        ip_address = attrs["ip_address"]
        if ip_address:
            if interface_obj.ip_addresses.all().exists():
                interface_obj.ip_addresses.all().delete()
            ip_address_obj = tonb_nbutils.create_ip(
                ip_address=attrs["ip_address"],
                subnet_mask=attrs["subnet_mask"],
                status=attrs["status"],
                object_pk=interface_obj,
            )
            interface_obj.ip_addresses.add(ip_address_obj)
            if attrs.get("ip_is_primary"):
                if ip_address_obj.ip_version == 4:
                    device_obj.primary_ip4 = ip_address_obj
                    device_obj.save()
                if ip_address_obj.ip_version == 6:
                    device_obj.primary_ip6 = ip_address_obj
                    device_obj.save()
        interface_obj.save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete Interface Object."""
        try:
            ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
            device = NautobotDevice.objects.filter(Q(name=self.device_name) & Q(tags__name=ssot_tag.name)).first()
            if not device:
                return
            interface = device.interfaces.get(name=self.name)
            # Access the addr within an interface, change the status if necessary
            if interface.ip_addresses.first():
                self.safe_delete(interface.ip_addresses.first(), SAFE_DELETE_IPADDRESS_STATUS)
            # Then do the parent interface
            # Attached interfaces do not have a status to update.
            self.safe_delete(
                interface,
            )
            return super().delete()
        except NautobotDevice.DoesNotExist:
            logger.warning(f"Unable to match device by name, {self.name}")

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update Interface object in Nautobot."""
        try:
            ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
            device = NautobotDevice.objects.filter(Q(name=self.device_name) & Q(tags__name=ssot_tag.name)).first()
            interface = device.interfaces.get(name=self.name)
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
            if attrs.get("ip_address"):
                if interface.ip_addresses.all().exists():
                    logger.info(f"Replacing IP from interface {interface} on {device.name}")
                    interface.ip_addresses.all().delete()
                ip_address_obj = tonb_nbutils.create_ip(
                    ip_address=attrs.get("ip_address"),
                    subnet_mask=attrs.get("subnet_mask") if attrs.get("subnet_mask") else "255.255.255.255",
                    status="Active",
                    object_pk=interface,
                )
                interface.ip_addresses.add(ip_address_obj)
            if attrs.get("ip_is_primary"):
                interface_obj = interface.ip_addresses.first()
                if interface_obj:
                    if interface_obj.ip_version == 4:
                        device.primary_ip4 = interface_obj
                        device.save()
                    if interface_obj.ip_version == 6:
                        device.primary_ip6 = interface_obj
                        device.save()
            interface.save()
            tonb_nbutils.tag_object(nautobot_object=interface, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            return super().update(attrs)

        except NautobotDevice.DoesNotExist:
            logger.warning(f"Unable to match device by name, {self.name}")


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
        location = NautobotLocation.objects.get(name=ids["location"])
        name = ids["name"] if ids["name"] else f"VLAN{attrs['vid']}"
        description = attrs["description"] if attrs["description"] else None
        if diffsync.job.debug:
            logger.debug("Creating VLAN: %s description: %s", name, description)
        tonb_nbutils.create_vlan(
            vlan_name=name,
            vlan_id=attrs["vid"],
            vlan_status=status,
            location_obj=location,
            description=description,
        )
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete."""
        vlan = VLAN.objects.get(name=self.name, pk=self.vlan_pk)
        self.safe_delete(
            vlan,
            SAFE_DELETE_VLAN_STATUS,
        )
        return super().delete()

    def update(self, attrs):
        """Update VLAN object in Nautobot."""
        vlan = VLAN.objects.get(name=self.name, vid=self.vid, location=NautobotLocation.objects.get(name=self.location))

        if attrs.get("status") == "Active":
            safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
            if not vlan.status == "Active":
                vlan.status = Status.objects.get(name="Active")
            device_tags = vlan.tags.filter(pk=safe_delete_tag.pk)
            if device_tags.exists():
                vlan.tags.remove(safe_delete_tag)
        if attrs.get("description"):
            vlan.description = vlan.description

        tonb_nbutils.tag_object(nautobot_object=vlan, custom_field=LAST_SYNCHRONIZED_CF_NAME)


Location.update_forward_refs()
Device.update_forward_refs()
Interface.update_forward_refs()
Vlan.update_forward_refs()
