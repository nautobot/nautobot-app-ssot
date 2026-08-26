# pylint: disable=duplicate-code
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
from nautobot.extras.models import CustomField, Role, Tag
from nautobot.extras.models.statuses import Status
from nautobot.extras.signals import change_context_state
from nautobot.ipam.choices import PrefixTypeChoices
from nautobot.ipam.models import VLAN, IPAddress, IPAddressToInterface, Namespace, Prefix, get_default_namespace
from netutils.ip import netmask_to_cidr
from netutils.lib_mapper import NAPALM_LIB_MAPPER

from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

# pylint: disable=too-many-branches


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
) -> Optional[Location]:
    """Creates a specified location in Nautobot.

    Args:
        location_name: Name of the location.
        location_id: ID of the location.
        logger: Logger to use for messaging.

    Returns:
        Location: When a Location Object is retrieved or created.
        None: When there is a failure in getting or creating a Location.
    """
    try:
        location_type = LocationType.objects.get(name="Site")
        if not location_type.content_types.filter(app_label="ipam", model="vlan").exists():
            location_type.content_types.add(ContentType.objects.get_for_model(VLAN))

        location_obj, _ = Location.objects.get_or_create(
            name=location_name,
            location_type=location_type,
            status=Status.objects.get(name="Active"),
        )
    except Location.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Locations returned with name {location_name}")
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new Location named {location_name} with LocationType Site")
    else:
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
        # tag_object performs validated_save()
        try:
            tag_object(nautobot_object=location_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.warning(
                    f"Unable to perform a validated_save() on Location {location_name} with an ID of {location_obj.id}"
                )
        return location_obj
    return None


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


def assign_device_to_virtual_chassis(device, virtual_chassis, position, master=False, priority=None):  # pylint: disable=too-many-arguments
    """Assign an existing device to an existing VirtualChassis. Update attributes if required."""
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
    if updated:
        device.validated_save()
    if master and virtual_chassis.master != device:
        virtual_chassis.master = device
        virtual_chassis.validated_save()
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


@job_scoped_cache
def get_tagged_device(device_name: str) -> Device:
    """Cached lookup for Devices, used in interface operations."""
    ssot_tag = get_or_create_tag_object(tag_name="SSoT Synced from IPFabric")
    return Device.objects.filter(Q(name=device_name) & Q(tags=ssot_tag)).first()


@job_scoped_cache(maxsize=2)
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


def create_ip(  # pylint: disable=too-many-statements
    ip_address: str,
    subnet_mask: str,
    status: str = "Active",
    object_pk: Optional[Interface] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[IPAddress]:
    """Verify ip address exists in Nautobot. If not, creates specified ip.

    Utility behavior is manipulated by `settings` if duplicate ip's are allowed.

    Args:
        ip_address: IP address.
        subnet_mask: Subnet mask used for IP Address.
        status: Status to assign to IP Address.
        object_pk: Interface Object to assigne IPAdress to.
        logger: Logger to use for messaging.

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
        try:
            ip_obj, _ = IPAddress.objects.get_or_create(address=f"{ip_address}/{cidr}", defaults={"status": status_obj})
        except IPAddress.MultipleObjectsReturned:
            if logger:
                logger.error(f"Multiple IPAddresses returned with the address of {ip_address}/{subnet_mask}")
        except (DjangoBaseDBError, ValidationError, Prefix.DoesNotExist):
            try:
                network_obj = ipaddress.ip_network(f"{ip_address}/{cidr}", strict=False)
                if logger:
                    logger.info(f"Automatically creating missing prefix {network_obj} for IP {ip_address}/{cidr}")
                _, _ = Prefix.objects.get_or_create(
                    network=str(network_obj.network_address),
                    prefix_length=network_obj.prefixlen,
                    type=PrefixTypeChoices.TYPE_NETWORK,
                    status=get_status_for_model(Prefix, "Active"),
                    namespace=get_global_namespace(),
                )
            except (DjangoBaseDBError, ValidationError) as err:
                if logger:
                    logger.error(f"Unable to create a new IPAddress of {ip_address}/{subnet_mask}. Error: {err}")
            else:
                try:
                    ip_obj, _ = IPAddress.objects.get_or_create(
                        address=f"{ip_address}/{cidr}", defaults={"status": status_obj}
                    )
                except (DjangoBaseDBError, ValidationError) as err:
                    if logger:
                        logger.error(f"Unable to create a new IPAddress of {ip_address}/{subnet_mask}. Error: {err}")

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


# Not cached, as it is unhashable, but not useful to cache anyway
def create_interface(
    device_obj: Device, interface_details: dict, logger: Optional[logging.Logger] = None
) -> Optional[Interface]:
    """Verify interface exists on specified device. If not, creates interface.

    Args:
        device_obj: Device object to check interface against.
        interface_details: interface details.
        logger: Logger to use for messaging.

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
        interface_obj, _ = device_obj.interfaces.get_or_create(
            name=interface_name, status=status_obj, defaults=defaults
        )
    except Interface.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Interfaces returned with name {interface_name} on Device named {device_obj.name}")
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new Interface named {interface_name} on Device named {device_obj.name}")
    else:
        try:
            tag_object(nautobot_object=interface_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.warning(
                    f"Unable to perform validated_save() on Interface named {interface_name} on Device named {device_obj.name}"
                )
        return interface_obj
    return None


@job_scoped_cache
def create_vlan(  # pylint: disable=too-many-arguments
    vlan_name: str,
    vlan_id: int,
    vlan_status: str,
    location_obj: Location,
    description: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[VLAN]:
    """Creates or obtains VLAN object.

    Args:
        vlan_name (str): VLAN Name
        vlan_id (int): VLAN ID
        vlan_status (str): VLAN Status
        location_obj (Location): Location Django Model
        description (str): VLAN Description
        logger: Logger to use for messaging.

    Returns:
        VLAN: When a VLAN Object is retrieved or created.
        None: When there is a failure in getting or creating a VLAN.
    """
    # Ensure LocationType allows VLANs
    if location_obj and not location_obj.location_type.content_types.filter(app_label="ipam", model="vlan").exists():
        location_obj.location_type.content_types.add(ContentType.objects.get_for_model(VLAN))

    try:
        vlan_obj, _ = VLAN.objects.get_or_create(
            vid=vlan_id,
            location=location_obj,
            defaults={
                "name": vlan_name,
                "status": Status.objects.get(name=vlan_status),
                "description": description,
            },
        )
    except VLAN.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple VLANs returned with name {vlan_name} and ID {vlan_id}")
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(f"Unable to create a new VLAN named {vlan_name} with an ID {vlan_id}. Error: {err}")
    else:
        try:
            tag_object(nautobot_object=vlan_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.warning(
                    f"Unable to perform validated_save() on VLAN named {vlan_name} with an ID of {vlan_obj.id}"
                )
        return vlan_obj
    return None


@job_scoped_cache
def get_tagged_pks(model: Any, tag_id: Any) -> frozenset:
    """Return the primary keys of the model's objects already carrying the given Tag.

    Resolved once per model and Tag for the whole run. Asking whether one object carries a Tag is a
    query, and a sync removing a hundred thousand Interfaces would otherwise ask it that many times.
    Objects tagged during the run are not added here, as each is only ever considered once.
    """
    return frozenset(model.objects.filter(tags__id=tag_id).values_list("pk", flat=True))


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
    ct = ContentType.objects.get_for_model(nautobot_object)
    tag = get_or_create_tag_object(
        tag_name=tag_name,
        tag_color=ColorChoices.COLOR_LIGHT_GREEN,
        description="Object synced at some point from IPFabric to Nautobot",
        app_label=ct.app_label,
        model=ct.model,
    )

    today = datetime.date.today().isoformat()

    def _tag_object(nautobot_object):
        """Apply custom field and tag to object, if applicable."""
        if hasattr(nautobot_object, "tags"):
            nautobot_object.tags.add(tag, *(extra_tags or ()))
        if hasattr(nautobot_object, "cf"):
            # Update custom field date stamp
            nautobot_object.cf["system_of_record"] = "IPFabric"
            nautobot_object.cf[custom_field] = today
        nautobot_object.validated_save()

    _tag_object(nautobot_object)
    # Ensure proper save
