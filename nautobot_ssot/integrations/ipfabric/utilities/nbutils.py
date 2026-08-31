# pylint: disable=duplicate-code
# One module holds every ORM helper this integration needs  #  pylint: disable=too-many-lines
"""Utility functions for Nautobot ORM."""

import datetime
import ipaddress
import logging
from contextlib import contextmanager
from typing import Any, Optional

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from django.db.models import Q
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    VirtualChassis,
)
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.context_managers import deferred_change_logging_for_bulk_operation
from nautobot.extras.models import CustomField, Role, Tag, TaggedItem
from nautobot.extras.models.statuses import Status
from nautobot.extras.signals import change_context_state
from nautobot.ipam.choices import PrefixTypeChoices
from nautobot.ipam.models import (
    VLAN,
    IPAddress,
    IPAddressToInterface,
    Namespace,
    Prefix,
    VLANLocationAssignment,
    get_default_namespace,
)
from netutils.ip import netmask_to_cidr
from netutils.lib_mapper import NAPALM_LIB_MAPPER

from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

# pylint: disable=too-many-branches

# Lookups that read back the objects bulk mode writes, so a flush leaves their results stale. Grouped
# so that `flush_pending_writes` can empty them, rather than each one having to know about the mode.
BULK_WRITTEN_LOOKUPS = "bulk_written_lookups"


@contextmanager
def deferred_change_logging():
    """Collapse the several writes one object takes into a single change log entry.

    Writing an object twice normally means looking up its change log entry and rewriting it, and
    serializing the object again to do so. Deferring within a scope makes Nautobot record one entry
    per object at the end of it instead.

    The scope is one object, not the whole run. Nautobot keys deferred changes per object, so a
    per-object scope saves everything a run wide one would, without holding every changed instance
    in memory or keeping one transaction open for the length of the sync.

    Does nothing when change logging is not enabled, which is the case when an adapter is driven
    directly rather than by a job, or when an enclosing scope is already deferring.

    Doubles as a decorator, which is how the model operations apply it.
    """
    change_context = change_context_state.get()
    if change_context is None or change_context.defer_object_changes:
        # Nesting would flush and discard the enclosing scope's pending changes on the way out.
        yield
        return
    with deferred_change_logging_for_bulk_operation():
        yield


@job_scoped_cache
def get_or_create_location_object(
    location_name: str,
    location_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    pending: Optional[Any] = None,
) -> Optional[Location]:
    """Creates a specified location in Nautobot.

    Args:
        location_name: Name of the location.
        location_id: ID of the location.
        logger: Logger to use for messaging.
        pending: When given, a new Location is queued for a batched write rather than saved. The
            returned Location already has its primary key, so a caller may go on to reference it.

    Returns:
        Location: When a Location Object is retrieved or created.
        None: When there is a failure in getting or creating a Location.
    """
    # A Location this run has already queued is not in the database yet, so it has to be found here
    # or a second one would be built and both written.
    if pending is not None:
        queued = pending.find(Location, location_name)
        if queued is not None:
            return queued

    try:
        location_type = LocationType.objects.get(name="Site")
        if not location_type.content_types.filter(app_label="ipam", model="vlan").exists():
            location_type.content_types.add(ContentType.objects.get_for_model(VLAN))
        try:
            location_obj = Location.objects.get(name=location_name, location_type=location_type)
            is_new = False
        except Location.DoesNotExist:
            location_obj = Location(
                name=location_name,
                location_type=location_type,
                status=Status.objects.get(name="Active"),
            )
            is_new = True
    except Location.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Locations returned with name {location_name}")
        return None
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new Location named {location_name} with LocationType Site")
        return None

    if location_id:
        # Ensure custom field is available
        try:
            custom_field_obj, _ = CustomField.objects.get_or_create(
                type=CustomFieldTypeChoices.TYPE_TEXT,
                key="ipfabric_site_id",
                defaults={"label": "IPFabric Location ID"},
            )
        except CustomField.MultipleObjectsReturned:
            if logger:
                logger.error("Multiple CustomFields returned with key ipfabric_site_id")
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.error("Unable to create a new CustomField named ipfabric_site_id with type of TYPE_TEXT")
        else:
            custom_field_obj.content_types.add(ContentType.objects.get_for_model(Location))
            location_obj.cf["ipfabric_site_id"] = location_id

    if is_new and pending is not None:
        stamp_synced(location_obj, LAST_SYNCHRONIZED_CF_NAME)
        pending.add(location_obj, key=location_name)
        queue_synced_tag(pending, location_obj)
        return location_obj

    # tag_object performs validated_save(), which is the only save a new Location takes.
    try:
        tag_object(nautobot_object=location_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.warning(
                f"Unable to perform a validated_save() on Location {location_name} with an ID of {location_obj.id}"
            )
    return location_obj


@job_scoped_cache
def get_location_object(
    location_name: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[Location]:
    """Return an existing Location by name, without creating one.

    Used when Locations are out of the sync's scope: another system owns them, so a Location that is
    not there yet is expected to arrive from that system rather than from this sync. Matched on name
    alone, since the owning system decides the LocationType.

    Cached like its get-or-create neighbour, since every Device at a site asks the same question. A
    stale answer is not a risk here: a sync that may not write Locations cannot invalidate its own
    cache, and caching the miss is what stops one absent site costing a query per Device.

    Args:
        location_name: Name of the location.
        logger: Logger to use for messaging.

    Returns:
        Location: When exactly one Location has that name.
        None: When no Location has that name, or more than one does.
    """
    try:
        return Location.objects.get(name=location_name)
    except Location.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Locations returned with name {location_name}")
    except Location.DoesNotExist:
        if logger:
            logger.debug("No Location named %s exists yet", location_name)
    return None


@job_scoped_cache
def get_or_create_manufacturer_object(
    vendor_name: str, logger: Optional[logging.Logger] = None
) -> Optional[Manufacturer]:
    """Create specified manufacturer in Nautobot.

    Args:
        vendor_name: Vendor Name.
        logger: Logger to use for messaging.

    Returns:
        Manufacturer: When a Manufacturer Object is retrieved or created.
        None: When there is a failure in getting or creating a Manufacturer.
    """
    try:
        manufacturer_obj, _ = Manufacturer.objects.get_or_create(name=vendor_name)
    except Manufacturer.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Manufacturers returned with name {vendor_name}")
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new Manufacturer named {vendor_name}")
    else:
        try:
            tag_object(nautobot_object=manufacturer_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.warning(
                    f"Unable to perform a validated_save() on Manufacturer {vendor_name} with an ID of {manufacturer_obj.id}"
                )
        return manufacturer_obj
    return None


@job_scoped_cache
def get_manufacturer_object(
    vendor_name: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[Manufacturer]:
    """Return an existing Manufacturer by name, without creating one.

    Used when Manufacturers are out of the sync's scope. See `get_location_object` for why the miss
    is cached along with the hit.

    Args:
        vendor_name: Vendor name.
        logger: Logger to use for messaging.

    Returns:
        Manufacturer: When exactly one Manufacturer has that name.
        None: When none has that name, or more than one does.
    """
    try:
        return Manufacturer.objects.get(name=vendor_name)
    except Manufacturer.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Manufacturers returned with name {vendor_name}")
    except Manufacturer.DoesNotExist:
        if logger:
            logger.debug("No Manufacturer named %s exists yet", vendor_name)
    return None


@job_scoped_cache
def get_device_type_object(
    device_type: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[DeviceType]:
    """Return an existing DeviceType by model, without creating one.

    Matched on the model alone, since out of scope the owning system decides the Manufacturer.

    Args:
        device_type: Device model gathered from DiffSync model.
        logger: Logger to use for messaging.

    Returns:
        DeviceType: When exactly one DeviceType has that model.
        None: When none has that model, or more than one does.
    """
    try:
        return DeviceType.objects.get(model=device_type)
    except DeviceType.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple DeviceTypes returned with model {device_type}")
    except DeviceType.DoesNotExist:
        if logger:
            logger.debug("No DeviceType with model %s exists yet", device_type)
    return None


@job_scoped_cache
def get_or_create_device_type_object(
    device_type: str,
    vendor_name: str,
    logger: Optional[logging.Logger] = None,
    manufacturer_obj: Optional[Manufacturer] = None,
) -> Optional[DeviceType]:
    """Create a specified device type in Nautobot.

    Args:
        device_type: Device model gathered from DiffSync model.
        vendor_name: Vendor Name.
        logger: Logger to use for messaging.
        manufacturer_obj: Manufacturer to file the DeviceType under. Supplied by callers that have
            already resolved it, so that a Manufacturer is not created for a sync whose scope
            excludes them. Looked up or created from `vendor_name` when not given.

    Returns:
        DeviceType: When a DeviceType Object is retrieved or created.
        None: When there is a failure in getting or creating a DeviceType.
    """
    if manufacturer_obj is None:
        manufacturer_obj = get_or_create_manufacturer_object(vendor_name, logger=logger)
    if manufacturer_obj:
        try:
            device_type_obj, _ = DeviceType.objects.get_or_create(
                manufacturer=manufacturer_obj,
                model=device_type,
            )
        except DeviceType.MultipleObjectsReturned:
            if logger:
                logger.error(
                    f"Multiple DeviceTypes returned with name {device_type} and Manufacturer name {vendor_name}"
                )
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.error(
                    f"Unable to create a new DeviceType named {device_type} with Manufacturer named {vendor_name}"
                )
        else:
            try:
                tag_object(nautobot_object=device_type_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError):
                if logger:
                    logger.warning(
                        f"Unable to perform a validated_save() on DeviceType {device_type} with an ID of {device_type_obj.id}"
                    )
            return device_type_obj
    elif logger:
        logger.warning(
            f"Unable to get or create a Manufacturer named {vendor_name}, and therefore cannot create a DeviceType {device_type}"
        )
    return None


@job_scoped_cache
def get_or_create_platform_object(
    platform: str,
    manufacturer_obj: Manufacturer,
    logger: Optional[logging.Logger] = None,
) -> Optional[Platform]:
    """Ensure Platform exists in Nautobot.

    Args:
        platform: The name of the platform.
        manufacturer: The Nautobot Manufacturer object to assign to the Platform.
        logger: Logger to use for messaging.

    Returns:
        Platform: When a Platform Object is retrieved or created.
        None: When there is a failure in getting or creating a Platform.
    """
    if not manufacturer_obj:
        if logger:
            logger.error(f"Unable to create Platform {platform} because Manufacturer is None")
        return None

    if platform == "ios-xe":
        network_driver = "cisco_ios"
        napalm_driver = "cisco_ios"
    else:
        network_driver = f"{manufacturer_obj.name.lower()}_{platform.lower()}"
        napalm_driver = NAPALM_LIB_MAPPER.get(platform, "")

    defaults = {
        "network_driver": network_driver,
        "napalm_driver": napalm_driver,
        "manufacturer": manufacturer_obj,
    }
    try:
        platform_obj = Platform.objects.get(name=platform)
        if platform_obj.manufacturer == manufacturer_obj:
            return platform_obj

        if logger:
            logger.warning(
                f"Platform {platform} already exists but belongs to Manufacturer {platform_obj.manufacturer}, "
                f"not {manufacturer_obj}. Skipping assignment to avoid validation errors."
            )
        return None

    except Platform.DoesNotExist:
        try:
            platform_obj = Platform.objects.create(name=platform, **defaults)
            return platform_obj
        except (DjangoBaseDBError, ValidationError) as err:
            if logger:
                logger.error(f"Unable to create a new Platform named {platform}. Error: {err}")
    except Platform.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Platforms returned with the name {platform}")
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to retrieve Platform named {platform}")
    return None


@job_scoped_cache
def get_or_create_device_role_object(
    role_name: str,
    role_color: str = ColorChoices.COLOR_GREY,
    logger: Optional[logging.Logger] = None,
) -> Optional[Role]:
    """Create specified device role in Nautobot.

    Args:
        role_name: Role name.
        role_color: Role color.
        logger: Logger to use for messaging.

    Returns:
        Role: When a Role Object is retrieved or created.
        None: When there is a failure in getting or creating a Role.
    """
    # adds custom field to map custom role names to ipfabric type names
    try:
        return Role.objects.get(_custom_field_data__ipfabric_type=role_name)
    except Role.DoesNotExist:
        try:
            role_obj = Role.objects.create(name=role_name, color=role_color)
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.error(f"Unable to create a new Role named {role_name}")
        else:
            role_obj.content_types.add(ContentType.objects.get_for_model(Device))
            role_obj.cf["ipfabric_type"] = role_name
            # tag_object performs validated_save()
            try:
                tag_object(nautobot_object=role_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError):
                if logger:
                    logger.warning(
                        f"Unable to perform validated_save() on Role {role_name} with an ID of {role_obj.id}"
                    )
            return role_obj
    except Role.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Roles returned with the name {role_name}")
    return None


@job_scoped_cache
def get_device_role_object(
    role_name: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[Role]:
    """Return an existing Role, without creating one.

    Matched on the `ipfabric_type` custom field first, as `get_or_create_device_role_object` does, so
    that a Role this integration created is still found. Falls back to the name, because out of scope
    the Role is expected to come from a system that does not set that custom field.

    Args:
        role_name: Role name.
        logger: Logger to use for messaging.

    Returns:
        Role: When exactly one Role matches.
        None: When none matches, or more than one does.
    """
    for lookup in ({"_custom_field_data__ipfabric_type": role_name}, {"name": role_name}):
        try:
            return Role.objects.get(**lookup)
        except Role.MultipleObjectsReturned:
            if logger:
                logger.error(f"Multiple Roles returned with the name {role_name}")
            return None
        except Role.DoesNotExist:
            continue
    if logger:
        logger.debug("No Role named %s exists yet", role_name)
    return None


@job_scoped_cache
def get_platform_object(
    platform: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[Platform]:
    """Return an existing Platform by name, without creating one.

    Matched on the name alone, since out of scope the owning system decides the Manufacturer.

    Args:
        platform: The name of the platform.
        logger: Logger to use for messaging.

    Returns:
        Platform: When exactly one Platform has that name.
        None: When none has that name, or more than one does.
    """
    try:
        return Platform.objects.get(name=platform)
    except Platform.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Platforms returned with name {platform}")
    except Platform.DoesNotExist:
        if logger:
            logger.debug("No Platform named %s exists yet", platform)
    return None


@job_scoped_cache
def get_or_create_status_object(  # pylint: disable=too-many-arguments
    status_name: str,
    status_color: str = ColorChoices.COLOR_GREY,
    description: str = "",
    app_label: str = "dcim",
    model: str = "device",
    logger: Optional[logging.Logger] = None,
) -> Optional[Status]:
    """Verify status object exists in Nautobot. If not, creates specified status. Defaults to dcim | device.

    Args:
        status_name: Status name.
        status_color: Status color.
        description: Description
        app_label: App Label ("DCIM")
        model: Django Model ("DEVICE")
        logger: Logger to use for messaging.

    Returns:
        Status: When a Status Object is retrieved or created.
        None: When there is a failure in getting or creating a Status.
    """
    try:
        return Status.objects.get(name=status_name)
    except Status.DoesNotExist:
        content_type = ContentType.objects.get(app_label=app_label, model=model)
        try:
            status_obj = Status.objects.create(
                name=status_name,
                color=status_color,
                description=description,
            )
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.error(f"Unable to create a new Status named {status_name}")
        else:
            status_obj.content_types.add(content_type)
            return status_obj
    except Status.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Statuses returned with the name {status_name}")
    return None


@job_scoped_cache
def get_or_create_tag_object(  # pylint: disable=too-many-arguments
    tag_name: str,
    tag_color: str = ColorChoices.COLOR_GREY,
    description: str = "",
    app_label: str = "dcim",
    model: str = "device",
    logger: Optional[logging.Logger] = None,
) -> Optional[Tag]:
    """Verify Tag object exists in Nautobot. If not, creates specified Tag. Defaults to dcim | device.

    Args:
        tag_name: Tag name.
        tag_color: Tag color.
        description: Description
        app_label: App Label ("DCIM")
        model: Django Model ("DEVICE")
        logger: Logger to use for messaging.

    Returns:
        Tag: When a Tag Object is retrieved or created.
        None: When there is a failure in getting or creating a Tag.
    """
    content_type = ContentType.objects.get(app_label=app_label, model=model)
    try:
        tag_obj, _ = Tag.objects.get_or_create(
            name__iexact=tag_name,
            defaults={
                "name": tag_name,
                "color": tag_color,
                "description": description,
            },
        )
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new Tag named {tag_name}")
        return None
    except Tag.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Tags returned with the name {tag_name}")
        return None
    tag_obj.content_types.add(content_type)
    return tag_obj


@job_scoped_cache
def get_or_create_virtual_chassis_object(name: str, logger=None) -> Optional[VirtualChassis]:
    """Get or create a VirtualChassis by name."""
    try:
        vc, _ = VirtualChassis.objects.get_or_create(name=name)
        return vc
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(f"Unable to get or create VirtualChassis named {name}. Error: {err}")
    return None


def assign_device_to_virtual_chassis(device, virtual_chassis, position, master=False, priority=None, pending=None):  # pylint: disable=too-many-arguments
    """Assign an existing device to an existing VirtualChassis. Update attributes if required.

    With `pending`, the Device is queued rather than saved, so its membership fields go in with the
    insert instead of needing a save of their own. The VirtualChassis master points back at the
    Device, so that one is deferred until the Device's row exists.
    """
    updated = False
    if device.virtual_chassis != virtual_chassis:
        device.virtual_chassis = virtual_chassis
        updated = True
    if position and device.vc_position != position:
        device.vc_position = position
        updated = True
    if priority and device.vc_priority != priority:
        device.vc_priority = priority
        updated = True
    if updated and pending is None:
        device.validated_save()
    if master and virtual_chassis.master != device:
        if pending is None:
            virtual_chassis.master = device
            virtual_chassis.validated_save()
        else:
            pending.defer_update(virtual_chassis, {"master": device})
    return virtual_chassis


@job_scoped_cache
def get_status_for_model(model: Any, status_name: str) -> Status:
    """Return the Status of the given name that applies to the given model.

    Cached because an IP Address carrying sync repeats this lookup for every address it writes.
    Raises rather than creating, so a caller can tell a missing Status from an ambiguous one.
    """
    return Status.objects.get_for_model(model).get(name=status_name)


@job_scoped_cache
def get_global_namespace() -> Namespace:
    """Return the Global Namespace, which every Prefix this integration creates belongs to.

    Cached rather than called directly because a first import creates a Prefix for every subnet it
    meets, and each of those would otherwise resolve the Namespace again.
    """
    return get_default_namespace()


@job_scoped_cache(group=BULK_WRITTEN_LOOKUPS)
def get_tagged_device(device_name: str) -> Device:
    """Cached lookup for Devices, used in interface operations."""
    ssot_tag = get_or_create_tag_object(tag_name="SSoT Synced from IPFabric")
    return Device.objects.filter(Q(name=device_name) & Q(tags=ssot_tag)).first()


@job_scoped_cache(group=BULK_WRITTEN_LOOKUPS, maxsize=2)
def get_device_interfaces_by_name(device: Device) -> dict:
    """Return a Device's Interfaces keyed by name, with the relations a delete reads prefetched.

    Deletions reach a model grouped by Device, so holding the last couple of Devices turns a lookup
    per Interface into one per Device. Bounded, because an estate wide teardown would otherwise
    retain every Interface of every Device it passed through.

    Keying by name loses nothing: Nautobot constrains `(device, name)` to be unique, so a Device
    cannot have two Interfaces of the same name.

    Not for callers that go on to mutate an Interface's relations, which would not see their own
    writes; `get_tagged_interface` is the uncached lookup for those.
    """
    return {interface.name: interface for interface in device.interfaces.prefetch_related("ip_addresses__interfaces")}


# Not cached, so that callers which mutate an Interface's relations see them afresh
def get_tagged_interface(
    device_name: str, interface_name: str, logger: Optional[logging.Logger] = None
) -> Optional[Interface]:
    """Retrieve an Interface belonging to a Device tagged as synced from IP Fabric.

    Args:
        device_name: Name of the Device the Interface belongs to.
        interface_name: Name of the Interface.
        logger: Logger to use for messaging.

    Returns:
        Interface: When the Interface is found.
        None: When either the Device or the Interface cannot be found.
    """
    device = get_tagged_device(device_name)
    if not device:
        if logger:
            logger.warning(
                f"Unable to find a Device named {device_name} tagged as synced from IPFabric, "
                f"so its Interface named {interface_name} cannot be retrieved"
            )
        return None
    try:
        return device.interfaces.get(name=interface_name)
    except Interface.MultipleObjectsReturned:
        if logger:
            logger.error(
                f"Multiple Interfaces returned with the name {interface_name} on Device named {device_name}, "
                "unable to determine which one to retrieve"
            )
    except Interface.DoesNotExist:
        if logger:
            logger.warning(f"Unable to find an Interface named {interface_name} on Device named {device_name}")
    return None


def create_ip(  # pylint: disable=too-many-statements,too-many-arguments
    ip_address: str,
    subnet_mask: str,
    status: str = "Active",
    object_pk: Optional[Interface] = None,
    logger: Optional[logging.Logger] = None,
    pending: Optional[Any] = None,
) -> Optional[IPAddress]:
    """Verify ip address exists in Nautobot. If not, creates specified ip.

    Utility behavior is manipulated by `settings` if duplicate ip's are allowed.

    Args:
        ip_address: IP address.
        subnet_mask: Subnet mask used for IP Address.
        status: Status to assign to IP Address.
        object_pk: Interface Object to assigne IPAdress to.
        logger: Logger to use for messaging.
        pending: When given, a new IPAddress and its Interface assignment are queued for a batched
            write rather than saved.

    Returns:
        IPAddress: When a IPAddress Object is retrieved or created.
        None: When there is a failure in getting or creating a IPAddress.
    """
    try:
        status_obj = get_status_for_model(IPAddress, status)
    except Status.MultipleObjectsReturned:
        if logger:
            logger.error(
                f"Multiple Statuses returned with name {status}, "
                f"and therefore cannot create an IPAddress of {ip_address}/{subnet_mask}"
            )
    except Status.DoesNotExist:
        if logger:
            logger.error(
                f"Unable to find a Status with the name {status}, "
                f"and therefore cannot create an IPAddress of {ip_address}/{subnet_mask}"
            )
    else:
        cidr = netmask_to_cidr(subnet_mask)
        ip_obj = None
        if pending is not None:
            return queue_ip(
                address=f"{ip_address}/{cidr}",
                status_obj=status_obj,
                interface=object_pk,
                pending=pending,
                logger=logger,
            )
        address = f"{ip_address}/{cidr}"
        try:
            ip_obj = IPAddress.objects.filter(address=address).first()
        except IPAddress.MultipleObjectsReturned:
            if logger:
                logger.error(f"Multiple IPAddresses returned with the address of {ip_address}/{subnet_mask}")
            ip_obj = None
        else:
            if ip_obj is None:
                ip_obj = resolve_new_ip(address, status_obj, logger=logger)
                if ip_obj is not None:
                    try:
                        ip_obj.validated_save()
                    except (DjangoBaseDBError, ValidationError) as err:
                        if logger:
                            logger.error(
                                f"Unable to create a new IPAddress of {ip_address}/{subnet_mask}. Error: {err}"
                            )
                        ip_obj = None

        if ip_obj:
            if object_pk:
                assign_ip = IPAddressToInterface(ip_address=ip_obj, interface_id=object_pk.pk)
                try:
                    assign_ip.validated_save()
                except (DjangoBaseDBError, ValidationError):
                    if logger:
                        logger.error(
                            f"Unable to assign IPAddress {ip_obj.address} with ID {ip_obj.id}"
                            f"to interface {object_pk.name} with ID {object_pk.id}"
                        )
                # The Interface is deliberately not tagged here. Both callers tag it themselves
                # once they are done with it, and `tag_object` runs a full `validated_save()`, so
                # tagging it twice doubles the write cost of every Interface that carries an address.

            try:
                # Tag IP Addr
                tag_object(nautobot_object=ip_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError):
                if logger:
                    logger.warning(
                        f"Unable to perform validated_save() on IPAddress {ip_obj.address} with an ID of {ip_obj.id}"
                    )

            return ip_obj
    return None


def _cleaned_ip(address: str, status_obj: Status) -> Optional[IPAddress]:
    """Return an unsaved IPAddress with everything `save()` would have worked out, or None.

    `clean()` is what resolves the Prefix the address belongs under, and a batched insert calls
    neither it nor `save()`. Returns None when Nautobot will not accept the address, most often
    because no parent Prefix exists yet. Built afresh each time, since a failed `clean()` may have
    left the instance half adjusted.
    """
    ip_obj = IPAddress(address=address, status=status_obj)
    try:
        ip_obj.clean()
    except ValidationError:
        return None
    return ip_obj


def resolve_new_ip(address: str, status_obj: Status, logger: Optional[logging.Logger] = None) -> Optional[IPAddress]:
    """Return an unsaved IPAddress ready to be written, creating its parent Prefix if there is none.

    The parent is set here rather than left to Nautobot to work out on save. Nautobot's own
    determination refuses a parent longer than the address's mask, so an address IP Fabric reports
    with a /24 mask is rejected when the only Prefix covering it is a /25 — even though that /25 is
    the parent Nautobot then says it expected. Setting it explicitly takes the same answer
    `clean()` would give and avoids that.

    A Prefix is only created when nothing covers the address. Creating a wider one when a narrower
    one already exists does not help, since Nautobot parents an address to the most specific Prefix
    that contains it.
    """
    ip_obj = _cleaned_ip(address, status_obj)
    if ip_obj is not None:
        return ip_obj
    # Nothing covers the address. IP Fabric reports addresses without their subnets, so this is the
    # normal state for the first address a sync sees from one.
    if not create_parent_prefix(address, logger=logger):
        return None
    return _cleaned_ip(address, status_obj)


def create_parent_prefix(address: str, logger: Optional[logging.Logger] = None) -> bool:
    """Create the Prefix an address belongs under, for when Nautobot holds none.

    IP Fabric reports addresses without the subnets they sit in, so the first address a sync sees
    from a subnet has no parent Prefix and Nautobot will not take it. Both write paths need this, and
    keeping it in one place is what stops them disagreeing about it.

    Args:
        address: The address in CIDR notation, whose network the Prefix is taken from.
        logger: Logger to use for messaging.

    Returns:
        bool: Whether a Prefix now exists for the address.
    """
    try:
        network_obj = ipaddress.ip_network(address, strict=False)
        if logger:
            logger.info(f"Automatically creating missing prefix {network_obj} for IP {address}")
        Prefix.objects.get_or_create(
            network=str(network_obj.network_address),
            prefix_length=network_obj.prefixlen,
            type=PrefixTypeChoices.TYPE_NETWORK,
            status=get_status_for_model(Prefix, "Active"),
            namespace=get_global_namespace(),
        )
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(f"Unable to create a missing Prefix for {address}. Error: {err}")
        return False
    return True


def queue_ip(
    address: str,
    status_obj: Status,
    interface: Optional[Interface],
    pending: Any,
    logger: Optional[logging.Logger] = None,
) -> Optional[IPAddress]:
    """Queue an IPAddress, and its assignment to an Interface, for a batched write.

    An address Nautobot already holds is reused rather than queued, so a re-sync does not try to
    insert it again.

    `IPAddress.save()` calls `clean()` to work out which Prefix the address belongs under, and a
    batched insert calls neither, so `clean()` is run here. It is also what rejects an address the
    sync should not be writing, which is worth keeping even in bulk mode: the alternative is a row
    with no parent Prefix, which leaves the address orphaned in IPAM.
    """
    existing = IPAddress.objects.filter(address=address).first()
    if existing is None:
        ip_obj = resolve_new_ip(address, status_obj, logger=logger)
        if ip_obj is None:
            if logger:
                logger.error(f"Unable to queue an IPAddress of {address} for a bulk write")
            return None
        stamp_synced(ip_obj, LAST_SYNCHRONIZED_CF_NAME)
        pending.add(ip_obj)
        queue_synced_tag(pending, ip_obj)
    else:
        ip_obj = existing

    if interface is not None:
        pending.add_through(IPAddressToInterface(ip_address=ip_obj, interface_id=interface.pk))
    return ip_obj


# Not cached, as it is unhashable, but not useful to cache anyway
def create_interface(
    device_obj: Device,
    interface_details: dict,
    logger: Optional[logging.Logger] = None,
    pending: Optional[Any] = None,
) -> Optional[Interface]:
    """Verify interface exists on specified device. If not, creates interface.

    Args:
        device_obj: Device object to check interface against.
        interface_details: interface details.
        logger: Logger to use for messaging.
        pending: When given, a new Interface is queued for a batched write rather than saved. The
            returned Interface already has its primary key, so a caller may go on to reference it.

    Returns:
        Interface: When a Interface Object is retrieved or created.
        None: When there is a failure in getting or creating a Interface.
    """
    interface_name = interface_details.pop("name")
    status = interface_details.pop("status", "Active")
    status_obj = get_or_create_status_object(status, app_label="dcim", model="interface", logger=logger)
    if not status_obj:
        if logger:
            logger.error(
                f"Unable to set Status of {status} for Interface named {interface_name} on Device named {device_obj.name}"
            )
        return None
    interface_fields = (
        "description",
        "enabled",
        "mac_address",
        "mtu",
        "type",
        "mgmt_only",
    )
    defaults = {k: v for k, v in interface_details.items() if k in interface_fields and v}
    try:
        interface_obj = device_obj.interfaces.filter(name=interface_name, status=status_obj).first()
        if interface_obj is None:
            interface_obj = Interface(device=device_obj, name=interface_name, status=status_obj, **defaults)
            # Stamped before the one save a new Interface takes. Applying the Tag afterwards writes
            # the Tag's own row rather than the Interface again, so this costs a single validated
            # save where a get or create followed by `tag_object` cost two.
            stamp_synced(interface_obj, LAST_SYNCHRONIZED_CF_NAME)
            if pending is not None:
                pending.add(interface_obj, key=(device_obj.pk, interface_name))
                queue_synced_tag(pending, interface_obj)
                return interface_obj
            interface_obj.validated_save()
            interface_obj.tags.add(synced_tag_for(interface_obj))
            return interface_obj
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new Interface named {interface_name} on Device named {device_obj.name}")
        return None

    # An Interface Nautobot already holds is re-stamped in place. Kept separate from the creation
    # above so that a failure here leaves the existing Interface returned, as it was before.
    try:
        tag_object(nautobot_object=interface_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.warning(
                f"Unable to perform validated_save() on Interface named {interface_name} on Device named {device_obj.name}"
            )
    return interface_obj


@job_scoped_cache
def create_vlan(  # pylint: disable=too-many-arguments
    vlan_name: str,
    vlan_id: int,
    vlan_status: str,
    location_obj: Location,
    description: str,
    logger: Optional[logging.Logger] = None,
    pending: Optional[Any] = None,
) -> Optional[VLAN]:
    """Creates or obtains VLAN object.

    Args:
        vlan_name (str): VLAN Name
        vlan_id (int): VLAN ID
        vlan_status (str): VLAN Status
        location_obj (Location): Location Django Model
        description (str): VLAN Description
        logger: Logger to use for messaging.
        pending: When given, a new VLAN and its location assignment are queued for a batched write
            rather than saved.

    Returns:
        VLAN: When a VLAN Object is retrieved or created.
        None: When there is a failure in getting or creating a VLAN.
    """
    # Ensure LocationType allows VLANs
    if location_obj and not location_obj.location_type.content_types.filter(app_label="ipam", model="vlan").exists():
        location_obj.location_type.content_types.add(ContentType.objects.get_for_model(VLAN))

    try:
        try:
            vlan_obj = VLAN.objects.get(vid=vlan_id, locations=location_obj)
            is_new = False
        except VLAN.DoesNotExist:
            # `location` is consumed by `VLAN.save()`, which is what makes the assignment. In bulk
            # mode that save never runs, so the assignment row is queued below instead.
            vlan_obj = VLAN(
                vid=vlan_id,
                name=vlan_name,
                status=Status.objects.get(name=vlan_status),
                description=description,
                location=location_obj,
            )
            is_new = True
    except VLAN.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple VLANs returned with name {vlan_name} and ID {vlan_id}")
        return None
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(f"Unable to create a new VLAN named {vlan_name} with an ID {vlan_id}. Error: {err}")
        return None

    if is_new and pending is not None:
        stamp_synced(vlan_obj, LAST_SYNCHRONIZED_CF_NAME)
        pending.add(vlan_obj)
        if location_obj is not None:
            pending.add_through(VLANLocationAssignment(vlan=vlan_obj, location_id=location_obj.pk))
        queue_synced_tag(pending, vlan_obj)
        return vlan_obj

    # tag_object performs validated_save(), which is the only save a new VLAN takes.
    try:
        tag_object(nautobot_object=vlan_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.warning(f"Unable to perform validated_save() on VLAN named {vlan_name} with an ID of {vlan_obj.id}")
    return vlan_obj


@job_scoped_cache
def get_tagged_pks(model: Any, tag_id: Any) -> frozenset:
    """Return the primary keys of the model's objects already carrying the given Tag.

    Resolved once per model and Tag for the whole run. Asking whether one object carries a Tag is a
    query, and a sync removing a hundred thousand Interfaces would otherwise ask it that many times.
    Objects tagged during the run are not added here, as each is only ever considered once.
    """
    return frozenset(model.objects.filter(tags__id=tag_id).values_list("pk", flat=True))


def synced_tag_for(nautobot_object: Any, tag_name: str = "SSoT Synced from IPFabric") -> Tag:
    """Return the Tag marking an object as synced from IP Fabric, for that object's content type."""
    content_type = ContentType.objects.get_for_model(nautobot_object)
    return get_or_create_tag_object(
        tag_name=tag_name,
        tag_color=ColorChoices.COLOR_LIGHT_GREEN,
        description="Object synced at some point from IPFabric to Nautobot",
        app_label=content_type.app_label,
        model=content_type.model,
    )


def queue_synced_tag(pending: Any, nautobot_object: Any, tag_name: str = "SSoT Synced from IPFabric"):
    """Queue the row tagging an object as synced, for an object being written in bulk.

    `tags.add` needs a saved object and issues its own statements, so a queued object gets the join
    row directly instead. Written after the object it points at, which the collector guarantees.
    """
    pending.add_through(
        TaggedItem(
            content_type=ContentType.objects.get_for_model(nautobot_object),
            object_id=nautobot_object.pk,
            tag=synced_tag_for(nautobot_object, tag_name=tag_name),
        )
    )


def stamp_synced(nautobot_object: Any, custom_field: str):
    """Record this integration as the object's source of record, without saving it.

    Separate from `tag_object` so that a newly built object can be stamped before the one save it
    takes, rather than saved again afterwards purely to carry the stamp.
    """
    if hasattr(nautobot_object, "cf"):
        nautobot_object.cf["system_of_record"] = "IPFabric"
        nautobot_object.cf[custom_field] = datetime.date.today().isoformat()


def tag_object(
    nautobot_object: Any,
    custom_field: str,
    tag_name: Optional[str] = "SSoT Synced from IPFabric",
    extra_tags: Optional[tuple] = None,
):
    """Apply the given tag and custom field to the identified object.

    Args:
        nautobot_object (Any): Nautobot ORM Object
        custom_field (str): Name of custom field to update
        tag_name (Optional[str], optional): Tag name. Defaults to "SSoT Synced From IPFabric".
        extra_tags (Optional[tuple], optional): Further Tags to apply in the same operation, so that
            a caller wanting two Tags does not pay for two round trips to the tag table.
    """
    tag = synced_tag_for(nautobot_object, tag_name=tag_name)

    def _tag_object(nautobot_object):
        """Apply custom field and tag to object, if applicable."""
        # `tags.add` reads the tag table to find what is missing even when nothing is, so an object
        # already carrying the tag is answered from the per-model set instead. Objects tagged during
        # the run are absent from that set, which costs a redundant add rather than a wrong answer.
        if hasattr(nautobot_object, "tags") and (
            extra_tags or nautobot_object.pk not in get_tagged_pks(type(nautobot_object), tag.id)
        ):
            nautobot_object.tags.add(tag, *(extra_tags or ()))
        stamp_synced(nautobot_object, custom_field)
        nautobot_object.validated_save()

    _tag_object(nautobot_object)
    # Ensure proper save
