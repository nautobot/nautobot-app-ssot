# pylint: disable=duplicate-code
# One module holds every ORM helper this integration needs  #  pylint: disable=too-many-lines
"""Utility functions for Nautobot ORM."""

import datetime
import ipaddress
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Optional

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import (
    Device,
    DeviceType,
    DeviceTypeToSoftwareImageFile,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    SoftwareImageFile,
    SoftwareVersion,
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
    VRF,
    IPAddress,
    IPAddressToInterface,
    Namespace,
    Prefix,
    PrefixLocationAssignment,
    RouteTarget,
    VLANGroup,
    VLANLocationAssignment,
    VRFDeviceAssignment,
    get_default_namespace,
)
from nautobot.tenancy.models import Tenant
from netutils.lib_mapper import NAPALM_LIB_MAPPER
from netutils.mac import is_valid_mac, mac_to_format

from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_INTERFACE_TYPE,
    DEFAULT_SYNCED_TAG_NAME,
    INTERFACE_STATE_FIELDS,
    LAST_SYNCHRONIZED_CF_NAME,
    SYNCED_TAG_NAME,
)
from nautobot_ssot.integrations.ipfabric.utilities.utils import host_route_length, job_scoped_cache

if TYPE_CHECKING:
    # Typing only: `writers` builds on this module, so importing it here at runtime would be circular.
    from nautobot_ssot.integrations.ipfabric.writers import Writer

# pylint: disable=too-many-branches

# Lookups that read back the objects bulk mode writes, so a flush leaves their results stale. Grouped
# so that `flush_pending_writes` can empty them, rather than each one having to know about the mode.
BULK_WRITTEN_LOOKUPS = "bulk_written_lookups"

# Custom field recording what IP Fabric reported inconsistently for a VRF, so that a VRF left
# without a route distinguisher is distinguishable from one whose devices agreed it has none.
VRF_CONFLICT_CF_NAME = "ipfabric_vrf_conflict"

# Likewise for a Prefix's VLAN: the site and VLAN pairs IP Fabric reported for a network when they
# did not agree on one, so that a Prefix left without a VLAN can be told from one that has none.
PREFIX_VLAN_CONFLICT_CF_NAME = "ipfabric_prefix_vlan_conflict"

# The MAC address IP Fabric discovered a host's IP Address at, which Nautobot has no field for.
HOST_MAC_CF_NAME = "ipfabric_host_mac"


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

    Every model operation runs inside it; see `DiffSyncExtras.__pydantic_init_subclass__`.
    """
    change_context = change_context_state.get()
    if change_context is None or change_context.defer_object_changes:
        # Nesting would flush and discard the enclosing scope's pending changes on the way out.
        yield
        return
    with deferred_change_logging_for_bulk_operation():
        yield


@contextmanager
def change_logging_not_deferred():
    """Log the changes made in this scope as they happen, even inside a scope that defers them.

    For deletes. Nautobot records a delete from `pre_delete` but, while deferring, only serializes
    it when the deferring scope ends, by which point Django has cleared the deleted object's primary
    key. Serializing it then reads the object's tags, which taggit refuses on an object with no
    primary key, so on Nautobot 3.2 a delete of anything taggable under deferral ends the job with
    "... objects need to have a primary key value before you can access their tags".

    Logged immediately, the delete is serialized in `pre_delete` while the object still exists,
    which is what Nautobot does outside a deferring scope. The enclosing scope's pending changes
    are set aside meanwhile and restored after, so what it collected is neither flushed early nor
    lost.
    """
    change_context = change_context_state.get()
    if change_context is None or not change_context.defer_object_changes:
        yield
        return
    pending = change_context.deferred_object_changes
    change_context.defer_object_changes = False
    change_context.deferred_object_changes = {}
    try:
        yield
    finally:
        change_context.deferred_object_changes = pending
        change_context.defer_object_changes = True


class BelongsToAnotherTenant(Exception):
    """Raised for an object this run would adopt that already belongs to a different Tenant."""

    def __init__(self, nautobot_object: Any):
        """Hold the object, so the caller can name it in its report."""
        super().__init__(f"{nautobot_object} belongs to the Tenant {nautobot_object.tenant}")
        self.nautobot_object = nautobot_object


def claim_for_tenant(nautobot_object: Any, tenant: Optional[Tenant]) -> bool:
    """Give an existing object the run's Tenant if it has none, and return whether it changed.

    Nothing changes when the run has no Tenant or the object already has this one. An object of
    another Tenant is not this run's to touch, so that raises `BelongsToAnotherTenant` instead.
    """
    if tenant is None or nautobot_object.tenant_id == tenant.pk:
        return False
    if nautobot_object.tenant_id is None:
        nautobot_object.tenant = tenant
        return True
    raise BelongsToAnotherTenant(nautobot_object)


@job_scoped_cache
def get_or_create_location_object(
    location_name: str,
    location_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
    tenant: Optional[Tenant] = None,
) -> Optional[Location]:
    """Creates a specified location in Nautobot.

    Args:
        location_name: Name of the location.
        location_id: ID of the location.
        tenant: The run's Tenant, given to a Location this creates. A Location that already exists
            is left with whatever Tenant it has, since a site may be shared.
        logger: Logger to use for messaging.
        writer: What writes a new Location. A queued one already has its primary key, so a caller may
            go on to reference it.

    Returns:
        Location: When a Location Object is retrieved or created.
        None: When there is a failure in getting or creating a Location.
    """
    # A Location this run has already queued is not in the database yet, so it has to be found here
    # or a second one would be built and both written.
    queued = writer.find(Location, location_name)
    if queued is not None:
        return queued

    try:
        location_type = LocationType.objects.get(name="Site")
        allow_vlans_at_location_type(location_type.pk)
        try:
            location_obj = Location.objects.get(name=location_name, location_type=location_type)
            is_new = False
        except Location.DoesNotExist:
            location_obj = Location(
                name=location_name,
                location_type=location_type,
                status=get_status_by_name("Active"),
                tenant=tenant,
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

    try:
        if is_new:
            return writer.create(location_obj, key=location_name)
        # The site ID above is custom field data, so it rides the same statement as the stamp.
        restamp_synced(location_obj, LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.warning(
                f"Unable to perform a validated_save() on Location {location_name} with an ID of {location_obj.id}"
            )
        if is_new:
            # That save was the new Location's only one, so there is no row to return a Location for.
            # Handing one back regardless would have every Device at the site reference a Location
            # that does not exist, which the database refuses at `COMMIT` and which takes the rest of
            # the transaction with it. A Location that was already there keeps its row and is
            # returned, since failing to re-stamp it is not a reason to withhold it.
            return None
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
def get_or_create_software_version(
    platform_obj: Platform, version: str, logger: Optional[logging.Logger] = None
) -> Optional[SoftwareVersion]:
    """Return the Software Version of a Platform, creating and marking it as synced if there is none.

    An existing version is reused unchanged, whoever created it. Cached because every Device running
    a release asks the same question. Written directly rather than queued, since a queued Device
    needs the version's row to point at.

    Returns:
        SoftwareVersion: When the version is found or created.
        None: When Nautobot refuses it.
    """
    existing = SoftwareVersion.objects.filter(platform=platform_obj, version=version).first()
    if existing is not None:
        return existing
    software_version = SoftwareVersion(
        platform=platform_obj,
        version=version,
        status=get_status_for_model(SoftwareVersion, "Active"),
    )
    stamp_synced(software_version, LAST_SYNCHRONIZED_CF_NAME)
    try:
        software_version.validated_save()
        software_version.tags.add(synced_tag_for(software_version))
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(
                "Unable to create a Software Version %s for the Platform %s. Error: %s", version, platform_obj, err
            )
        return None
    return software_version


@job_scoped_cache
def get_or_create_software_image(
    software_version: SoftwareVersion,
    image_file_name: str,
    device_type: DeviceType,
    logger: Optional[logging.Logger] = None,
) -> Optional[SoftwareImageFile]:
    """Return a Software Version's image file, creating it if there is none, mapped to a Device Type.

    Nautobot refuses an image on a Device unless the image is mapped to the Device's type, so the
    mapping is made here for every Device Type found running it. An existing image is matched
    ignoring case, since the name this sync reports is lowercased.

    Returns:
        SoftwareImageFile: When the image is found or created and mapped.
        None: When Nautobot refuses either.
    """
    image = SoftwareImageFile.objects.filter(
        software_version=software_version, image_file_name__iexact=image_file_name
    ).first()
    try:
        if image is None:
            image = SoftwareImageFile(
                software_version=software_version,
                image_file_name=image_file_name,
                status=get_status_for_model(SoftwareImageFile, "Active"),
            )
            stamp_synced(image, LAST_SYNCHRONIZED_CF_NAME)
            image.validated_save()
            image.tags.add(synced_tag_for(image))
        DeviceTypeToSoftwareImageFile.objects.get_or_create(device_type=device_type, software_image_file=image)
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(
                "Unable to record the Software Image File %s of %s for the Device Type %s. Error: %s",
                image_file_name,
                software_version,
                device_type,
                err,
            )
        return None
    return image


def assign_software_image(device: Device, image: SoftwareImageFile, *, writer: "Writer") -> None:
    """Make an image the one a Device runs, replacing any other the Device names.

    A queued Device has no row to attach the image to yet, so the join row is queued after it.
    """
    if writer.holds(device):
        writer.assign(Device.software_image_files.through(device=device, softwareimagefile=image))
        return
    device.software_image_files.set([image])


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
    create: bool = True,
    logger: Optional[logging.Logger] = None,
) -> Optional[Status]:
    """Verify status object exists in Nautobot. If not, creates specified status. Defaults to dcim | device.

    `create` is part of the cache key, so a run that matches and a run that creates do not share an
    answer.

    Args:
        status_name: Status name.
        status_color: Status color, for a Status that is created.
        description: Description, for a Status that is created.
        app_label: App Label ("DCIM"), for a Status that is created.
        model: Django Model ("DEVICE"), for a Status that is created.
        create: Whether a Status of this name may be created when none exists.
        logger: Logger to use for messaging.

    Returns:
        Status: When a Status Object is retrieved or created.
        None: When there is a failure in getting or creating a Status.
    """
    try:
        return Status.objects.get(name=status_name)
    except Status.DoesNotExist:
        if not create:
            if logger:
                logger.debug("No Status named %s exists yet", status_name)
            return None
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
def get_virtual_chassis_object(name: str, logger=None) -> Optional[VirtualChassis]:
    """Return an existing VirtualChassis by name, without creating one."""
    try:
        return VirtualChassis.objects.get(name=name)
    except VirtualChassis.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple VirtualChassis returned with the name {name}")
    except VirtualChassis.DoesNotExist:
        if logger:
            logger.debug("No VirtualChassis named %s exists yet", name)
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


def assign_device_to_virtual_chassis(  # pylint: disable=too-many-arguments
    device, virtual_chassis, position, master=False, priority=None, *, writer: "Writer"
):
    """Assign an existing device to an existing VirtualChassis. Update attributes if required.

    A Device the writer has queued carries its membership fields into its insert, and one already in
    Nautobot is saved. The VirtualChassis master points back at the Device, so that is set once the
    Device's row exists.
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
    if updated:
        writer.save(device)
    if master and virtual_chassis.master != device:
        writer.set_later(virtual_chassis, {"master": device})
    return virtual_chassis


@job_scoped_cache
def get_status_for_model(model: Any, status_name: str) -> Status:
    """Return the Status of the given name that applies to the given model.

    Cached because an IP Address carrying sync repeats this lookup for every address it writes.
    Raises rather than creating, so a caller can tell a missing Status from an ambiguous one.
    """
    return Status.objects.get_for_model(model).get(name=status_name)


@job_scoped_cache
def get_status_by_name(status_name: str) -> Status:
    """Return the Status of the given name, wherever it is enabled.

    Cached because a sync resolves the same handful of Status names for every object it writes.
    Raises as the bare lookup does, so a caller can tell a missing Status from an ambiguous one.

    Distinct from `get_status_for_model`, which restricts to the Statuses enabled for one model and
    so refuses a Status that exists but has not been enabled there.
    """
    return Status.objects.get(name=status_name)


@job_scoped_cache
def allow_at_location_type(location_type_id: Any, model: Any) -> None:
    """Ensure a LocationType permits a model, asked once per LocationType rather than once per object.

    A Location cannot hold a VLAN or a Prefix unless its LocationType lists the content type, and a
    sync writing one at a site Nautobot has never held one at has to add it. The answer is the same
    for every object at every Location of that type, so it is worth asking once.
    """
    permitted = LocationType.objects.filter(
        pk=location_type_id,
        content_types__app_label=model._meta.app_label,  # pylint: disable=protected-access
        content_types__model=model._meta.model_name,  # pylint: disable=protected-access
    ).exists()
    if not permitted:
        LocationType.objects.get(pk=location_type_id).content_types.add(ContentType.objects.get_for_model(model))


def allow_vlans_at_location_type(location_type_id: Any) -> None:
    """Ensure a LocationType permits VLANs; see `allow_at_location_type`."""
    allow_at_location_type(location_type_id, VLAN)


# The Namespace chosen on the job for this run, if any. Thread local, like the job scoped caches,
# and set by the job at the start of every run so that one run's choice never reaches the next.
_run_namespace = threading.local()


def use_namespace(namespace: Optional[Namespace]) -> None:
    """Set the Namespace this run's addresses, Prefixes and VRFs belong to, or None for Global."""
    _run_namespace.chosen = namespace


def namespace_chosen() -> bool:
    """Return whether the job named a Namespace for this run, rather than leaving it to Global."""
    return getattr(_run_namespace, "chosen", None) is not None


@job_scoped_cache
def get_global_namespace() -> Namespace:
    """Return the Global Namespace.

    Cached rather than called directly because a first import creates a Prefix for every subnet it
    meets, and each of those would otherwise resolve the Namespace again.
    """
    return get_default_namespace()


def get_run_namespace() -> Namespace:
    """Return the Namespace this run reads and writes addresses, Prefixes and VRFs in.

    Not cached itself: a chosen Namespace is already an object, and Global comes from the cached
    `get_global_namespace`.
    """
    chosen = getattr(_run_namespace, "chosen", None)
    return chosen if chosen is not None else get_global_namespace()


def run_namespace_filter() -> dict:
    """Return queryset filter arguments limiting IP Addresses to the chosen Namespace.

    Empty when no Namespace was chosen, so that addresses are then matched from any Namespace.
    """
    return {"parent__namespace": get_run_namespace()} if namespace_chosen() else {}


@dataclass(frozen=True)
class DeviceScope:
    """The Devices one run of the sync covers, for reading them and for writing to them alike.

    The Nautobot adapter reads its Devices through `devices`, and every write to an Interface, an
    address, a VLAN, a VRF or a Cable finds its Device through `get_syncable_device`, which asks the
    same question. A run that read a Device it could not write to would report the same changes on
    every run and never apply them; one that wrote to a Device it did not read would change what it
    never compared.

    Attributes:
        tagged_only: Whether only Devices carrying the synced Tag are covered, as **Sync Tagged Only**.
        tenant: The run's Tenant, when only its Devices are covered.
        location_pks: The Locations covered, or None for every Location.
    """

    tagged_only: bool = False
    tenant: Optional[Tenant] = None
    location_pks: Optional[frozenset] = None

    def devices(self):
        """Return the Devices this scope covers."""
        devices = Device.objects.all()
        if self.location_pks is not None:
            devices = devices.filter(location__in=self.location_pks)
        if self.tagged_only:
            devices = devices.filter(tags=get_or_create_tag_object(tag_name=SYNCED_TAG_NAME))
        if self.tenant is not None:
            devices = devices.filter(tenant=self.tenant)
        return devices


@job_scoped_cache(group=BULK_WRITTEN_LOOKUPS)
def get_syncable_device(device_name: str, *, scope: DeviceScope) -> Optional[Device]:
    """Return the Device an Interface or Cable operation is for, or None when it is out of scope.

    `scope` is required, so no write path can match a Device the Nautobot adapter did not read.
    """
    return scope.devices().filter(name=device_name).first()


@job_scoped_cache(group=BULK_WRITTEN_LOOKUPS, maxsize=2)
def get_device_interfaces_by_name(device: Device) -> dict:
    """Return a Device's Interfaces keyed by name.

    Deletions and updates reach a model grouped by Device, so holding the last couple of Devices
    turns a lookup per Interface into one per Device. Bounded, because an estate wide teardown would
    otherwise retain every Interface of every Device it passed through.

    Keying by name loses nothing: Nautobot constrains `(device, name)` to be unique, so a Device
    cannot have two Interfaces of the same name.

    The addresses on each Interface are deliberately not prefetched. No caller reads them: an address
    is its own model, so removing one goes through `InterfaceAddress`, which resolves the Interface
    afresh. Prefetching them would be two joins nothing looks at.

    Not for callers that go on to mutate an Interface's relations, which would not see their own
    writes; `get_tagged_interface` is the uncached lookup for those.
    """
    return {interface.name: interface for interface in device.interfaces.all()}


# Not cached, so that callers which mutate an Interface's relations see them afresh
def get_tagged_interface(
    device_name: str,
    interface_name: str,
    *,
    scope: DeviceScope,
    logger: Optional[logging.Logger] = None,
) -> Optional[Interface]:
    """Retrieve an Interface belonging to a Device this run covers.

    Args:
        device_name: Name of the Device the Interface belongs to.
        interface_name: Name of the Interface.
        logger: Logger to use for messaging.
        scope: The Devices this run covers; see `DeviceScope`.

    Returns:
        Interface: When the Interface is found.
        None: When either the Device or the Interface cannot be found.
    """
    device = get_syncable_device(device_name, scope=scope)
    if not device:
        if logger:
            logger.warning(
                f"Unable to find a Device named {device_name} in the scope of this sync, "
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
    mask_length: int,
    status: str = "Active",
    object_pk: Optional[Interface] = None,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
    tenant: Optional[Tenant] = None,
) -> Optional[IPAddress]:
    """Verify ip address exists in Nautobot. If not, creates specified ip.

    Utility behavior is manipulated by `settings` if duplicate ip's are allowed.

    Args:
        ip_address: IP address, without a mask.
        mask_length: Prefix length the address is configured with. A length rather than a netmask,
            so that the same call serves an IPv6 address as an IPv4 one.
        status: Status to assign to IP Address.
        object_pk: Interface Object to assigne IPAdress to.
        logger: Logger to use for messaging.
        writer: What writes a new IPAddress and its Interface assignment.
        tenant: The run's Tenant, given to a new address and to an existing one that has none.

    Returns:
        IPAddress: When a IPAddress Object is retrieved or created.
        None: When there is a failure in getting or creating a IPAddress.
    """
    if not mask_length:
        # Refused rather than given a host route, which would put the address under the wrong parent
        # Prefix and leave nothing to distinguish it from an address genuinely configured as one.
        if logger:
            logger.warning(f"Unable to create an IPAddress of {ip_address} because no subnet mask was reported for it")
        return None
    try:
        status_obj = get_status_for_model(IPAddress, status)
    except Status.MultipleObjectsReturned:
        if logger:
            logger.error(
                f"Multiple Statuses returned with name {status}, "
                f"and therefore cannot create an IPAddress of {ip_address}/{mask_length}"
            )
    except Status.DoesNotExist:
        if logger:
            logger.error(
                f"Unable to find a Status with the name {status}, "
                f"and therefore cannot create an IPAddress of {ip_address}/{mask_length}"
            )
    else:
        if writer.batched:
            # Its own path rather than the writer's methods alone, since an address this run already
            # queued has to be found by what Nautobot makes unique; see `queue_ip`.
            return queue_ip(
                address=f"{ip_address}/{mask_length}",
                status_obj=status_obj,
                interface=object_pk,
                writer=writer,
                logger=logger,
                tenant=tenant,
            )
        ip_obj = resolve_ip(f"{ip_address}/{mask_length}", status_obj, logger=logger, tenant=tenant)
        if ip_obj is None:
            return None

        if not ip_obj.present_in_database:
            ip_obj.tenant = tenant
            # Stamped before the one save a new address takes, so the Tag row that follows is the
            # only further write.
            stamp_synced(ip_obj, LAST_SYNCHRONIZED_CF_NAME)
            try:
                ip_obj.validated_save()
                ip_obj.tags.add(synced_tag_for(ip_obj))
            except (DjangoBaseDBError, ValidationError) as err:
                if logger:
                    logger.error(f"Unable to create a new IPAddress of {ip_address}/{mask_length}. Error: {err}")
                return None
        else:
            # The mask IP Fabric reports rides the tagging save rather than taking one of its own.
            claimed = claim_for_tenant(ip_obj, tenant)
            mask_changed = ip_obj.mask_length != mask_length
            ip_obj.mask_length = mask_length
            try:
                if mask_changed or claimed:
                    tag_object(nautobot_object=ip_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
                else:
                    # The usual case on a re-sync, and the one worth keeping cheap: IP Fabric
                    # reports the address exactly as Nautobot already holds it, so the stamp is the
                    # only thing left to write.
                    restamp_synced(ip_obj, LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError) as err:
                if logger and mask_changed:
                    logger.error(
                        f"Unable to change the mask of IPAddress {ip_address} to the /{mask_length} "
                        f"IP Fabric reports for it. Error: {err}"
                    )
                elif logger:
                    logger.warning(
                        f"Unable to perform validated_save() on IPAddress {ip_obj.address} with an ID of {ip_obj.id}"
                    )
                ip_obj.refresh_from_db()

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
            # The Interface is deliberately not tagged here. Both callers tag it themselves once
            # they are done with it, and `tag_object` runs a full `validated_save()`, so tagging it
            # twice doubles the write cost of every Interface that carries an address.
        return ip_obj
    return None


def _cleaned_ip(address: str, status_obj: Status) -> Optional[IPAddress]:
    """Return an unsaved IPAddress with everything `save()` would have worked out, or None.

    `clean()` is what resolves the Prefix the address belongs under, and a batched insert calls
    neither it nor `save()`. Returns None when Nautobot will not accept the address, most often
    because no parent Prefix exists yet. Built afresh each time, since a failed `clean()` may have
    left the instance half adjusted.
    """
    ip_obj = IPAddress(address=address, status=status_obj, namespace=get_run_namespace())
    try:
        ip_obj.clean()
    except ValidationError:
        return None
    return ip_obj


def resolve_new_ip(
    address: str, status_obj: Status, logger: Optional[logging.Logger] = None, tenant: Optional[Tenant] = None
) -> Optional[IPAddress]:
    """Return an unsaved IPAddress ready to be written, creating its parent Prefix if there is none.

    The parent is set here rather than left to Nautobot to work out on save. Nautobot's own
    determination refuses a parent longer than the address's mask, so an address IP Fabric reports
    with a /24 mask is rejected when the only Prefix covering it is a /25, even though that /25 is
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
    if not create_parent_prefix(address, logger=logger, tenant=tenant):
        return None
    return _cleaned_ip(address, status_obj)


def create_parent_prefix(
    address: str, logger: Optional[logging.Logger] = None, tenant: Optional[Tenant] = None
) -> bool:
    """Create the Prefix an address belongs under, for when Nautobot holds none.

    IP Fabric reports addresses without the subnets they sit in, so the first address a sync sees
    from a subnet has no parent Prefix and Nautobot will not take it. Both write paths need this, and
    keeping it in one place is what stops them disagreeing about it.

    Args:
        address: The address in CIDR notation, whose network the Prefix is taken from.
        logger: Logger to use for messaging.
        tenant: The run's Tenant, given to the Prefix this creates.

    Returns:
        bool: Whether a Prefix now exists for the address.
    """
    if covering_prefix_exists(address):
        # Checked rather than inferred from a failure to build the address. Nautobot 3.2 also reports
        # a duplicate address from `clean()`, and reading that as a missing Prefix created a second,
        # wider one that could never become the parent: Nautobot parents an address to the most
        # specific Prefix containing it.
        return True
    try:
        network_obj = ipaddress.ip_network(address, strict=False)
        if logger:
            logger.info(f"Automatically creating missing prefix {network_obj} for IP {address}")
        Prefix.objects.get_or_create(
            network=str(network_obj.network_address),
            prefix_length=network_obj.prefixlen,
            type=PrefixTypeChoices.TYPE_NETWORK,
            status=get_status_for_model(Prefix, "Active"),
            namespace=get_run_namespace(),
            defaults={"tenant": tenant},
        )
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(f"Unable to create a missing Prefix for {address}. Error: {err}")
        return False
    return True


def covering_prefix_exists(address: str) -> bool:
    """Return whether a Prefix in the run's Namespace contains the host of an address.

    Asked about the host rather than the address's own network, since that is the question that
    decides whether Nautobot can parent the address at all: any Prefix containing the host will do,
    however its length compares with the address's mask.
    """
    host = address.split("/")[0]
    # The route covering only this address, which is `/128` for IPv6 rather than `/32`. Asked with a
    # `/32` an IPv6 host names a subnet millions of addresses wide, so no Prefix holding it contains
    # that, and the check reports none where one exists.
    covering = f"{host}/{host_route_length(host)}"
    return Prefix.objects.filter(namespace=get_run_namespace()).net_contains_or_equals(covering).exists()


def get_prefix(prefix: str) -> Optional[Prefix]:
    """Return the Prefix of the given network in the run's Namespace, or None if there is none.

    Matched on the network and its length together, which is what Nautobot makes a Prefix unique
    on within a Namespace. The network alone names every Prefix that starts at that address.
    """
    network = ipaddress.ip_network(prefix)
    return Prefix.objects.filter(
        namespace=get_run_namespace(),
        network=str(network.network_address),
        prefix_length=network.prefixlen,
    ).first()


def create_prefix(
    prefix: str, create: bool = True, logger: Optional[logging.Logger] = None, tenant: Optional[Tenant] = None
) -> Optional[Prefix]:
    """Create a Prefix in the run's Namespace, or adopt the one Nautobot already holds.

    A Prefix is unique on its network within a Namespace, so one another process or an earlier
    address created is the same object this sync would have made. It is adopted and marked as
    synced rather than duplicated, as a Route Target is, which is what lets a first run converge
    against an existing estate. Its type and status are left as they are.

    Written directly rather than queued, even in Bulk Write Mode: the addresses queued under it
    have their parent worked out by `clean()` as they are queued, which reads Prefixes back from the
    database.

    Args:
        prefix: The network in CIDR notation.
        create: Whether a Prefix may be created when Nautobot holds none, which a run strict about
            Prefixes does not allow. One already there is adopted either way.
        tenant: The run's Tenant, given to a new Prefix and to an existing one that has none.
        logger: Logger to use for messaging.

    Returns:
        Prefix: When the Prefix is created or adopted.
        None: When Nautobot holds none and none may be created, or Nautobot refuses it.
    """
    existing = get_prefix(prefix)
    if existing is not None:
        claim_for_tenant(existing, tenant)
        try:
            tag_object(nautobot_object=existing, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError) as err:
            if logger:
                logger.error("Unable to mark the Prefix %s as synced. Error: %s", prefix, err)
        return existing
    if not create:
        return None
    network = ipaddress.ip_network(prefix)
    prefix_obj = Prefix(
        network=str(network.network_address),
        prefix_length=network.prefixlen,
        namespace=get_run_namespace(),
        type=PrefixTypeChoices.TYPE_NETWORK,
        status=get_status_for_model(Prefix, "Active"),
        tenant=tenant,
    )
    stamp_synced(prefix_obj, LAST_SYNCHRONIZED_CF_NAME)
    try:
        prefix_obj.validated_save()
        prefix_obj.tags.add(synced_tag_for(prefix_obj))
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error("Unable to create a Prefix of %s. Error: %s", prefix, err)
        return None
    return prefix_obj


def resolve_prefix_location(location_name: str, *, writer: "Writer") -> Optional[Location]:
    """Return the Location a Prefix is seen at, from this run's queue or from Nautobot."""
    return writer.find(Location, location_name) or get_location_object(location_name)


def add_prefix_location(
    prefix: str,
    location_name: str,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
) -> bool:
    """Record that a Prefix is seen at a Location.

    The Location's type is made to permit Prefixes first, as it is for VLANs, since a Location
    cannot hold a Prefix its type does not list and Nautobot does not check that on the way in.

    Args:
        prefix: The network in CIDR notation.
        location_name: Name of the Location.
        logger: Logger to use for messaging.
        writer: What writes the assignment, and where a Location queued earlier in the run is found.

    Returns:
        bool: Whether the assignment was written or queued.
    """
    prefix_obj = get_prefix(prefix)
    if prefix_obj is None:
        if logger:
            logger.error("Unable to find a Prefix of %s to record at the Location named %s", prefix, location_name)
        return False
    location_obj = resolve_prefix_location(location_name, writer=writer)
    if location_obj is None:
        # Not reported here: one missing site would be named once for every Prefix seen at it. The
        # caller counts these and reports them once.
        return False
    allow_at_location_type(location_obj.location_type_id, Prefix)
    if writer.batched:
        # Saved immediately through `locations.add` instead, which leaves a row Nautobot already
        # holds alone where saving the row itself would refuse it.
        writer.assign(PrefixLocationAssignment(prefix=prefix_obj, location=location_obj))
        return True
    try:
        prefix_obj.locations.add(location_obj)
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(
                "Unable to record the Prefix %s at the Location named %s. Error: %s", prefix, location_name, err
            )
        return False
    return True


def get_vlan_at_location_name(vid: int, location_name: str) -> Optional[VLAN]:
    """Return the VLAN with the given ID at the Location of the given name, if Nautobot holds one."""
    return VLAN.objects.filter(vid=vid, locations__name=location_name).first()


def first_locations_of_vlans(pairs: Iterable) -> dict:
    """Return the first Location, by name, of the VLAN Nautobot holds for each (Location name, VLAN ID).

    The Location a Prefix's VLAN is named by on both sides of the diff. A VLAN at several Locations
    is then the same VLAN whichever of them IP Fabric reported it at. A pair Nautobot holds no VLAN
    for is left out.
    """
    pairs = set(pairs)
    if not pairs:
        return {}
    vlans = (
        VLAN.objects.filter(vid__in={vid for _, vid in pairs}, locations__name__in={site for site, _ in pairs})
        .prefetch_related("locations")
        .distinct()
    )
    first = {}
    for vlan_record in vlans:
        names = sorted(location.name for location in vlan_record.locations.all())
        for name in names:
            first.setdefault((name, vlan_record.vid), names[0])
    return {pair: first[pair] for pair in pairs if pair in first}


def set_prefix_vlan(
    prefix: str, vlan_obj: Optional[VLAN], conflict: str, logger: Optional[logging.Logger] = None
) -> bool:
    """Point a Prefix at a VLAN, or at none, and record what IP Fabric reported inconsistently for it.

    Args:
        prefix: The network in CIDR notation.
        vlan_obj: The VLAN, or None to leave the Prefix without one.
        conflict: The site and VLAN pairs IP Fabric disagreed between, or an empty string.
        logger: Logger to use for messaging.

    Returns:
        bool: Whether the Prefix was written.
    """
    prefix_obj = get_prefix(prefix)
    if prefix_obj is None:
        if logger:
            logger.error("Unable to find a Prefix of %s to record its VLAN on", prefix)
        return False
    prefix_obj.vlan = vlan_obj
    prefix_obj.cf[PREFIX_VLAN_CONFLICT_CF_NAME] = conflict
    try:
        # Calls validated_save() on the object.
        tag_object(nautobot_object=prefix_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error("Unable to record the VLAN of the Prefix %s. Error: %s", prefix, err)
        return False
    return True


def normalise_mac(mac: Optional[str]) -> str:
    """Return a MAC address in Nautobot's colon separated upper case form, or "" when it is not one.

    IP Fabric reports a host's MAC in Cisco's dotted form, `aac1.ab6f.dbe2`, and the Interface MACs
    this integration writes are formatted the same way as this.
    """
    if not mac or not is_valid_mac(mac):
        return ""
    return mac_to_format(mac, "MAC_COLON_TWO").upper()


def get_host_address(host: str) -> Optional[IPAddress]:
    """Return the IP Address of a host IP Fabric discovered, matched as an interface address is."""
    return IPAddress.objects.filter(host=host, **run_namespace_filter()).first()


def set_host_details(ip_obj: IPAddress, dns_name: str, mac: str, logger: Optional[logging.Logger] = None) -> bool:
    """Record a host's DNS name and MAC address on its IP Address, and save whatever else changed with them.

    Args:
        ip_obj: The host's IP Address, which the caller may have changed in other ways too.
        dns_name: The DNS name IP Fabric discovered, or an empty string.
        mac: The MAC address IP Fabric discovered, in the form `normalise_mac` returns, or an empty string.
        logger: Logger to use for messaging.

    Returns:
        bool: Whether the IP Address was saved.
    """
    ip_obj.dns_name = dns_name
    ip_obj.cf[HOST_MAC_CF_NAME] = mac
    try:
        # Calls validated_save() on the object.
        tag_object(nautobot_object=ip_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error("Unable to record the host details of the IP Address %s. Error: %s", ip_obj.host, err)
        return False
    return True


def remove_prefix_location(prefix: str, location_name: str, logger: Optional[logging.Logger] = None) -> bool:
    """Stop recording a Prefix at a Location. Neither the Prefix nor the Location is removed."""
    prefix_obj = get_prefix(prefix)
    location_obj = get_location_object(location_name)
    if prefix_obj is None or location_obj is None:
        if logger:
            logger.error(
                "Unable to find the Prefix %s at the Location named %s to stop recording it there",
                prefix,
                location_name,
            )
        return False
    prefix_obj.locations.remove(location_obj)
    return True


def mask_length_of(address: str) -> int:
    """Return the mask length from an address in CIDR notation."""
    return int(address.split("/")[1])


def resolve_ip(
    address: str, status_obj: Status, logger: Optional[logging.Logger] = None, tenant: Optional[Tenant] = None
) -> Optional[IPAddress]:
    """Return the IPAddress to use for `address`, whether Nautobot already holds one or not.

    One that `present_in_database` reports as saved is Nautobot's own, to be reused. A new one comes
    back unsaved, for the caller to write or to queue.

    Nautobot makes an address unique within its parent Prefix, and the mask IP Fabric reports for an
    address need not be the mask Nautobot holds it under, so matching on the address misses the very
    row that uniqueness covers. The host within the Namespace is matched as well, which is what
    decides the parent and therefore what decides the collision.

    Asked before anything is built, rather than after. Nautobot 3.2 reports a duplicate from
    `clean()`, so building first cannot tell an address that needs a Prefix from one that already
    exists.

    Both candidates are keyed on the same host, so they are read in one query and chosen between in
    Python. Asked as two, the pair runs in full for every address of a first import, where both miss.
    """
    host = address.split("/")[0]
    candidates = list(IPAddress.objects.filter(host=host, **run_namespace_filter()).select_related("parent"))
    # An exact match on the mask as well, which is what `filter(address=...)` is shorthand for. Taken
    # ahead of the Namespace match, and from any Namespace unless the job named one.
    for existing in candidates:
        if existing.mask_length == mask_length_of(address):
            return existing
    namespace = get_run_namespace()
    for existing in candidates:
        if existing.parent.namespace_id == namespace.pk:
            return existing
    return resolve_new_ip(address, status_obj, logger=logger, tenant=tenant)


def queue_ip(  # pylint: disable=too-many-arguments
    address: str,
    status_obj: Status,
    interface: Optional[Interface],
    writer: "Writer",
    logger: Optional[logging.Logger] = None,
    tenant: Optional[Tenant] = None,
) -> Optional[IPAddress]:
    """Queue an IPAddress, and its assignment to an Interface, for a batched write.

    An address already written, or already queued by this run, is reused rather than queued again.
    Nautobot makes an address unique within its parent Prefix, so queueing a second one for an
    address IP Fabric reports on two Interfaces would have the database refuse it. See `resolve_ip`
    for why the match is not on the address alone.

    An address Nautobot holds under a different mask has that mask corrected. IP Fabric reports the
    subnet an address sits in, and that mask is the attribute the sync keeps, so leaving it alone
    would have the difference reported on every run without ever settling.

    `IPAddress.save()` calls `clean()` to work out which Prefix the address belongs under, and a
    batched insert calls neither, so `clean()` is run here. It is also what rejects an address the
    sync should not be writing, which is worth keeping even in bulk mode: the alternative is a row
    with no parent Prefix, which leaves the address orphaned in IPAM.
    """
    ip_obj = resolve_ip(address, status_obj, logger=logger, tenant=tenant)
    if ip_obj is None:
        if logger:
            logger.error(f"Unable to queue an IPAddress of {address} for a bulk write")
        return None
    if not ip_obj.present_in_database:
        # Keyed on what the uniqueness constraint covers rather than on the address, so that an
        # address this run has already queued is reused even where IP Fabric reported the two with
        # different masks.
        key = (ip_obj.parent_id, str(ip_obj.host))
        queued = writer.find(IPAddress, key)
        if queued is not None:
            ip_obj = queued
        else:
            ip_obj.tenant = tenant
            writer.create(ip_obj, key=key)
    else:
        if claim_for_tenant(ip_obj, tenant):
            writer.set_later(ip_obj, {"tenant": tenant})
        if ip_obj.mask_length != mask_length_of(address):
            writer.set_later(ip_obj, {"mask_length": mask_length_of(address)})

    if interface is not None:
        writer.assign(IPAddressToInterface(ip_address=ip_obj, interface_id=interface.pk))
    return ip_obj


# Not cached, as it is unhashable, but not useful to cache anyway
def resolve_parent_interface(device_obj, parent_name: str, *, writer: "Writer") -> Optional[Interface]:
    """Return the Interface a subinterface hangs off, from this run's queue or from Nautobot.

    The queue first, because a port this run has only queued has no row to be read back yet. It
    already carries its primary key, so a subinterface written in the same batch may point at it.
    """
    queued = writer.find(Interface, (device_obj.pk, parent_name))
    if queued is not None:
        return queued
    if writer.holds(device_obj):
        # The Device is queued and holds no rows, so nothing of its can be read back.
        return None
    return device_obj.interfaces.filter(name=parent_name).first()


def related_interfaces_of(  # pylint: disable=too-many-arguments
    device_obj: Device,
    interface_details: dict,
    interface_name: str,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
) -> dict:
    """Return the Interface fields naming another Interface on the same Device, resolved.

    `parent_interface` is the port a subinterface is configured on and `lag` is the port channel an
    Interface is a member of. Both name an Interface of the same Device, so both are looked for the
    same way, and one this run cannot find is reported rather than guessed at.
    """
    resolved = {}
    for field in ("parent_interface", "lag"):
        named = interface_details.get(field)
        if not named:
            continue
        related = resolve_parent_interface(device_obj, named, writer=writer)
        if related is None:
            if logger:
                logger.warning(
                    "Not relating Interface %s on Device %s to %s, as no such Interface is there.",
                    interface_name,
                    device_obj.name,
                    named,
                )
        else:
            resolved[field] = related
    return resolved


def create_interface(  # pylint: disable=too-many-arguments
    device_obj: Device,
    interface_details: dict,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
    create_statuses: bool = True,
) -> Optional[Interface]:
    """Verify interface exists on specified device. If not, creates interface.

    Args:
        device_obj: Device object to check interface against.
        interface_details: interface details.
        logger: Logger to use for messaging.
        writer: What writes a new Interface. A queued one already has its primary key, so a caller may
            go on to reference it.
        create_statuses: Whether the Interface's Status may be created when none of that name exists.

    Returns:
        Interface: When a Interface Object is retrieved or created.
        None: When there is a failure in getting or creating a Interface.
    """
    interface_name = interface_details.pop("name")
    status = interface_details.pop("status", "Active")
    status_obj = get_or_create_status_object(
        status, app_label="dcim", model="interface", create=create_statuses, logger=logger
    )
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
    if isinstance(interface_details.get("enabled"), bool):
        # Kept out of the filter above, which drops a falsy value as an absence. `False` is a value
        # here: an Interface IP Fabric reports as shut is meant to be disabled.
        defaults["enabled"] = interface_details["enabled"]
    if not defaults.get("type"):
        # Nautobot requires a type, so a new Interface whose media type nothing resolved takes the
        # configured default. The only place that default is still applied: an Interface already in
        # Nautobot has a type worth keeping, and this one has nothing to keep.
        defaults["type"] = DEFAULT_INTERFACE_TYPE
    defaults.update(related_interfaces_of(device_obj, interface_details, interface_name, logger=logger, writer=writer))
    reported_state = {
        custom_field: interface_details.get(attribute) for attribute, custom_field in INTERFACE_STATE_FIELDS.items()
    }
    unable_to_create = f"Unable to create a new Interface named {interface_name} on Device named {device_obj.name}"
    try:
        if writer.holds(device_obj):
            # The Device is queued and has no rows of its own yet, so it can hold no Interface.
            interface_obj = None
        else:
            interface_obj = device_obj.interfaces.filter(name=interface_name, status=status_obj).first()
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(unable_to_create)
        return None

    if interface_obj is not None:
        # An Interface Nautobot already holds is re-stamped in place. Nothing above changes a field on
        # it, so the stamp is the whole of the write, and a failure still returns the Interface.
        try:
            restamp_synced(interface_obj, LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.warning(
                    f"Unable to perform validated_save() on Interface named {interface_name} on Device named {device_obj.name}"
                )
        return interface_obj

    interface_obj = Interface(device=device_obj, name=interface_name, status=status_obj, **defaults)
    interface_obj.cf.update(reported_state)
    try:
        writer.create(interface_obj, key=(device_obj.pk, interface_name))
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(unable_to_create)
        return None
    return interface_obj


@job_scoped_cache
def get_vlan_group_for_location(location_obj: Location, create: bool, logger: Optional[logging.Logger] = None):
    """Return the VLAN Group a Location's VLANs belong in, or None to leave them ungrouped.

    Nautobot makes a VLAN unique by `(vlan_group, vid)` and by `(vlan_group, name)`, and enforces
    neither where the group is null. Putting a Location's VLANs in a group of their own is what makes
    one VLAN ID mean one VLAN there, which is what this integration identifies a VLAN by.

    The group is named after the Location. A `VLANGroup` name is unique across Nautobot, so one of
    that name already pointing at another Location belongs to somebody else: it is reported and the
    VLANs are left ungrouped rather than filed under a group that is not theirs.
    """
    existing = VLANGroup.objects.filter(name=location_obj.name).first()
    if existing is not None:
        if existing.location_id == location_obj.pk:
            return existing
        if logger:
            logger.warning(
                "A VLAN Group named %s already belongs to another Location, so the VLANs at %s are "
                "synced without a group and their VLAN IDs are not constrained.",
                location_obj.name,
                location_obj.name,
            )
        return None
    if not create:
        if logger:
            logger.warning(
                "No VLAN Group named %s, so the VLANs there are synced without one and their VLAN "
                "IDs are not constrained.",
                location_obj.name,
            )
        return None
    # A Location holds a VLAN Group only where its LocationType says so, as it does for VLANs.
    if not location_obj.location_type.content_types.filter(app_label="ipam", model="vlangroup").exists():
        location_obj.location_type.content_types.add(ContentType.objects.get_for_model(VLANGroup))
    group = VLANGroup(name=location_obj.name, location=location_obj)
    stamp_synced(group, LAST_SYNCHRONIZED_CF_NAME)
    try:
        group.validated_save()
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error("Unable to create a VLAN Group named %s. Error: %s", location_obj.name, err)
        return None
    group.tags.add(synced_tag_for(group))
    return group


def vlan_group_can_hold(location_name: str, vlan_name: str, vlan_id: int, create: bool) -> bool:
    """Whether this VLAN can be filed under its Location's VLAN Group.

    Read only, and asked by the IP Fabric side before it reports a VLAN as grouped, so that a VLAN
    the group cannot hold is reported as ungrouped by both sides rather than diffed every run
    against a group that will never take it.

    Three ways it cannot: no group of that name exists and this run may not create one; a group of
    that name belongs to another Location; or the group already holds a different VLAN under this
    name, a group making the name unique within it as well as the VLAN ID.
    """
    existing = VLANGroup.objects.filter(name=location_name).first()
    if existing is None:
        # Nothing is filed yet, so there is nothing for this VLAN to collide with.
        return create
    if existing.location is None or existing.location.name != location_name:
        return False
    return not vlan_group_refuses_name(existing, vlan_name, vlan_id)


def vlan_group_refuses_name(group, vlan_name: str, vlan_id: int) -> bool:
    """Whether the group already holds a different VLAN under this name.

    A group makes `(vlan_group, name)` unique as well as `(vlan_group, vid)`, so two VLANs of one
    name at a Location cannot both be filed under it. Asked before writing so the collision is
    reported against the VLAN it belongs to, rather than surfacing as a database refusal.
    """
    return group is not None and VLAN.objects.filter(vlan_group=group, name=vlan_name).exclude(vid=vlan_id).exists()


@job_scoped_cache
def create_vlan(  # pylint: disable=too-many-arguments,too-many-locals,too-many-return-statements
    vlan_name: str,
    vlan_id: int,
    vlan_status: str,
    location_obj: Location,
    description: str,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
    vlan_group: Optional[Any] = None,
    tenant: Optional[Tenant] = None,
) -> Optional[VLAN]:
    """Creates or obtains VLAN object.

    Args:
        vlan_name (str): VLAN Name
        vlan_id (int): VLAN ID
        vlan_status (str): VLAN Status
        location_obj (Location): Location Django Model
        description (str): VLAN Description
        logger: Logger to use for messaging.
        writer: What writes a new VLAN and its location assignment.
        vlan_group: The VLAN Group the Location's VLANs belong in, or None to leave them ungrouped.
        tenant: The run's Tenant, given to a new VLAN and to an existing one that has none.

    Returns:
        VLAN: When a VLAN Object is retrieved or created.
        None: When there is a failure in getting or creating a VLAN.
    """
    if location_obj:
        # Taken from the Location's own column rather than through the relation, which would fetch
        # the LocationType only to read its primary key back.
        allow_vlans_at_location_type(location_obj.location_type_id)

    if vlan_group_refuses_name(vlan_group, vlan_name, vlan_id):
        if logger:
            logger.warning(
                "VLAN %s at %s is synced without a VLAN Group: the group there already holds a "
                "different VLAN named %s, and a group makes that name unique within it. Its VLAN ID "
                "is not constrained until the duplicate name is resolved.",
                vlan_id,
                location_obj.name if location_obj else "no Location",
                vlan_name,
            )
        vlan_group = None

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
                status=get_status_by_name(vlan_status),
                description=description,
                location=location_obj,
                vlan_group=vlan_group,
                tenant=tenant,
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

    claimed = not is_new and claim_for_tenant(vlan_obj, tenant)
    adopted = not is_new and vlan_group is not None and vlan_obj.vlan_group_id != vlan_group.pk
    if adopted:
        # A VLAN that predates the group is filed under it, since the constraint only covers what is
        # actually in the group.
        vlan_obj.vlan_group = vlan_group

    if is_new and writer.batched:
        # Saved immediately through `tag_object` below instead, since `VLAN.save()` makes the location
        # assignment itself and a queued VLAN is never saved.
        assignments = (
            (VLANLocationAssignment(vlan=vlan_obj, location_id=location_obj.pk),) if location_obj is not None else ()
        )
        # Keyed the way `resolve_interface_vlans` looks it up, so an Interface written later in
        # the same run can point at a VLAN this run has only queued.
        key = (vlan_id, location_obj.pk) if location_obj is not None else None
        return writer.create(vlan_obj, key=key, through_rows=assignments)

    try:
        if is_new or adopted or claimed:
            # tag_object performs validated_save(), which is the only save a new VLAN takes and the
            # one that persists the group or Tenant an existing VLAN has just been given.
            tag_object(nautobot_object=vlan_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        else:
            # Nothing above changed a field on a VLAN Nautobot already holds, so the stamp is the
            # whole of the write.
            restamp_synced(vlan_obj, LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.warning(f"Unable to perform validated_save() on VLAN named {vlan_name} with an ID of {vlan_obj.id}")
    return vlan_obj


def create_route_target(
    name: str, logger: Optional[logging.Logger] = None, tenant: Optional[Tenant] = None
) -> Optional[RouteTarget]:
    """Create a Route Target, or adopt the one Nautobot already holds under that name.

    A Route Target's name is unique across Nautobot, so one another process created is the same
    object this sync would have made. It is adopted and marked as synced rather than duplicated,
    which is also what lets the first run of this integration converge against an existing estate.

    Written directly rather than queued for a batch even in Bulk Write Mode. A network has a handful
    of Route Targets where it has thousands of Interfaces, so there is nothing worth batching, and
    the rows tying a VRF to its targets need the target's row to exist already.

    Args:
        name: Route target value, as IP Fabric reports it.
        logger: Logger to use for messaging.

    Returns:
        RouteTarget: When the Route Target is created or adopted.
        None: When Nautobot refuses it, which a value longer than the field allows does.
    """
    route_target = RouteTarget.objects.filter(name=name).first()
    if route_target is not None:
        claim_for_tenant(route_target, tenant)
        # Already there, so it is re-stamped in place; `tag_object` answers "does it carry the Tag
        # already" from the per-model set rather than asking the tag table for every target.
        try:
            tag_object(nautobot_object=route_target, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        except (DjangoBaseDBError, ValidationError) as err:
            if logger:
                logger.error("Unable to mark the Route Target named %s as synced. Error: %s", name, err)
        return route_target

    route_target = RouteTarget(name=name, tenant=tenant)
    # Stamped before the one save a new Route Target takes, so the Tag row that follows is the only
    # further write.
    stamp_synced(route_target, LAST_SYNCHRONIZED_CF_NAME)
    try:
        route_target.validated_save()
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error("Unable to create a Route Target named %s. Error: %s", name, err)
        return None
    route_target.tags.add(synced_tag_for(route_target))
    return route_target


def set_route_targets(  # pylint: disable=too-many-arguments
    vrf_obj: VRF,
    import_targets: Iterable[str],
    export_targets: Iterable[str],
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
):
    """Point a VRF at the Route Targets it imports and exports.

    The targets themselves are synced as their own object type, and are created before the VRFs that
    name them, so this matches rather than creates. A name that is missing here is one whose own
    creation was refused, and is reported and left out so that the VRF still records the rest.

    Args:
        vrf_obj: The VRF to assign to.
        import_targets: Route target values the VRF imports.
        export_targets: Route target values the VRF exports.
        logger: Logger to use for messaging.
        writer: Where the join rows of a VRF the writer has queued go, behind it. A VRF Nautobot
            already holds is assigned directly even in bulk mode, since `set()` reads the rows it has
            to remove and a queued VRF has none.
    """
    import_targets, export_targets = list(import_targets), list(export_targets)
    wanted = set(import_targets) | set(export_targets)
    by_name = {route_target.name: route_target for route_target in RouteTarget.objects.filter(name__in=wanted)}
    missing = sorted(wanted - set(by_name))
    if missing and logger:
        logger.warning(
            "Not recording the Route Target(s) %s on the VRF named %s, as Nautobot does not hold them",
            ", ".join(missing),
            vrf_obj.name,
        )
    resolved_imports = [by_name[name] for name in import_targets if name in by_name]
    resolved_exports = [by_name[name] for name in export_targets if name in by_name]

    if writer.holds(vrf_obj):
        for route_target in resolved_imports:
            writer.assign(VRF.import_targets.through(vrf_id=vrf_obj.pk, routetarget_id=route_target.pk))
        for route_target in resolved_exports:
            writer.assign(VRF.export_targets.through(vrf_id=vrf_obj.pk, routetarget_id=route_target.pk))
        return

    vrf_obj.import_targets.set(resolved_imports)
    vrf_obj.export_targets.set(resolved_exports)


@job_scoped_cache(group=BULK_WRITTEN_LOOKUPS)
def get_vlan_at_location(vid: int, location_id: Any) -> Optional[VLAN]:
    """Return the VLAN with the given ID at the given Location, if Nautobot holds one.

    Nautobot does not constrain a VLAN ID to be unique at a Location, so the first is taken; the
    adapters report the duplicate when they load it.
    """
    return VLAN.objects.filter(vid=vid, locations__id=location_id).first()


def resolve_interface_vlans(  # pylint: disable=too-many-arguments
    interface_obj: Interface,
    untagged_vid: Optional[int],
    tagged_vids: Iterable[int],
    *,
    writer: "Writer",
    logger: Optional[logging.Logger] = None,
) -> tuple:
    """Return the `(untagged, tagged)` VLAN objects for an Interface, given the IDs it carries.

    A VLAN this run has queued is not in the database yet, so the queue is asked first. An ID the
    Interface's Location has no VLAN for is reported and left out, since Nautobot has nothing to
    point the Interface at; that is the ordinary state under a Site Filter, where the run covers one
    site's VLANs but a trunk may name another's.
    """
    location_id = interface_obj.device.location_id

    def one(vid):
        return writer.find(VLAN, (vid, location_id)) or get_vlan_at_location(vid, location_id)

    untagged = one(untagged_vid) if untagged_vid is not None else None
    if untagged_vid is not None and untagged is None and logger:
        logger.warning(
            "No VLAN with ID %s at the Location of %s, so it is not set as the untagged VLAN of %s",
            untagged_vid,
            interface_obj.device.name,
            interface_obj.name,
        )
    tagged, missing = [], []
    for vid in tagged_vids:
        vlan = one(vid)
        if vlan is None:
            missing.append(vid)
        else:
            tagged.append(vlan)
    if missing and logger:
        logger.warning(
            "No VLAN at the Location of %s for %s, so they are not tagged on %s",
            interface_obj.device.name,
            ", ".join(str(vid) for vid in missing),
            interface_obj.name,
        )
    return untagged, tagged


def set_interface_vlans(  # pylint: disable=too-many-arguments,too-many-locals
    device_name: str,
    interface_name: str,
    mode: str,
    untagged_vid: Optional[int],
    tagged_vids: Iterable[int],
    scope: DeviceScope,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
) -> bool:
    """Set an Interface's 802.1Q mode and the VLANs it carries, or clear them.

    Nautobot requires a VLAN to be available at the Interface's Device's Location before an
    Interface may reference it, which is why this is written after the VLANs rather than with the
    Interface.

    Args:
        device_name: Name of the Device the Interface belongs to.
        interface_name: Name of the Interface.
        mode: One of Nautobot's 802.1Q modes, or an empty string to take the Interface out of one.
        untagged_vid: VLAN ID to carry untagged, or None.
        tagged_vids: VLAN IDs to carry tagged.
        scope: The Devices this run covers; see `DeviceScope`.
        logger: Logger to use for messaging.
        writer: What writes the Interface and its VLANs, and where queued objects are found.

    Returns:
        bool: Whether the Interface now holds what was asked for.
    """
    device_obj = writer.find(Device, device_name) or get_syncable_device(device_name, scope=scope)
    interface_obj = writer.find(Interface, (device_obj.pk, interface_name)) if device_obj is not None else None
    if interface_obj is None:
        interface_obj = get_tagged_interface(device_name, interface_name, scope=scope, logger=logger)
    if interface_obj is None:
        return False

    untagged, tagged = resolve_interface_vlans(interface_obj, untagged_vid, tagged_vids, writer=writer, logger=logger)
    interface_obj.mode = mode
    interface_obj.untagged_vlan = untagged

    if writer.batched:
        # Its own path, since a queued Interface and one Nautobot already holds are written
        # differently in a batch, and the tagged VLANs of the second are reconciled against the
        # join table rather than replaced through it.
        rows = [Interface.tagged_vlans.through(interface_id=interface_obj.pk, vlan_id=vlan.pk) for vlan in tagged]
        if writer.holds(interface_obj):
            # Interfaces are written before VLANs, so an Interface inserted now cannot carry a VLAN
            # this run has only queued: the insert would name a row that does not exist yet. The
            # mode goes on the insert, and the untagged VLAN follows as an update once both are
            # written. The tagged ones are join rows, written once both ends are there.
            if untagged is not None and writer.holds(untagged):
                interface_obj.untagged_vlan = None
                writer.set_later(interface_obj, {"untagged_vlan": untagged})
            for row in rows:
                writer.assign(row)
            return True
        writer.set_later(interface_obj, {"mode": mode, "untagged_vlan": untagged})
        # An Interface Nautobot already holds carries a set of tagged VLANs to be replaced, not
        # added to. The collector only inserts, so the rows this run no longer reports are removed
        # here, and the ones it still reports are left alone rather than queued a second time
        # against the join table's uniqueness.
        held = set(interface_obj.tagged_vlans.values_list("pk", flat=True))
        wanted = {vlan.pk for vlan in tagged}
        if held - wanted:
            Interface.tagged_vlans.through.objects.filter(
                interface_id=interface_obj.pk, vlan_id__in=held - wanted
            ).delete()
        for row in rows:
            if row.vlan_id not in held:
                writer.assign(row)
        return True
    try:
        interface_obj.validated_save()
        interface_obj.tagged_vlans.set(tagged)
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(
                "Unable to set the VLANs of %s:%s. Error: %s",
                device_name,
                interface_name,
                err,
            )
        return False
    return True


def set_interface_vrf(  # pylint: disable=too-many-arguments
    device_name: str,
    interface_name: str,
    vrf_name: Optional[str],
    scope: DeviceScope,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
) -> bool:
    """Put an Interface in a VRF, or take it out of the one it is in.

    Nautobot requires the VRF to be assigned to the Interface's Device before an Interface may
    reference it, which is why this is written after the assignments rather than with the Interface.

    Args:
        device_name: Name of the Device the Interface belongs to.
        interface_name: Name of the Interface.
        vrf_name: Name of the VRF in the run's Namespace, or None to take the Interface out of one.
        scope: The Devices this run covers; see `DeviceScope`.
        logger: Logger to use for messaging.
        writer: What writes the Interface, and where queued objects are found.

    Returns:
        bool: Whether the Interface now holds what was asked for.
    """
    vrf_obj = None
    if vrf_name is not None:
        vrf_obj = writer.find(VRF, vrf_name) or get_vrf(vrf_name, logger=logger)
        if vrf_obj is None:
            if logger:
                logger.error("Unable to find a VRF named %s to put %s:%s in", vrf_name, device_name, interface_name)
            return False

    device_obj = writer.find(Device, device_name) or get_syncable_device(device_name, scope=scope)
    interface_obj = writer.find(Interface, (device_obj.pk, interface_name)) if device_obj is not None else None
    if interface_obj is None:
        interface_obj = get_tagged_interface(device_name, interface_name, scope=scope, logger=logger)
    if interface_obj is None:
        return False

    if writer.holds(interface_obj):
        # A queued Interface is inserted carrying the foreign key.
        interface_obj.vrf = vrf_obj
        return True
    try:
        # One already written is updated: at once, or in a batch once everything else is written,
        # since the VRF assignment it depends on may itself be queued.
        writer.set_later(interface_obj, {"vrf": vrf_obj})
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(
                "Unable to put %s:%s in the VRF named %s. Error: %s", device_name, interface_name, vrf_name, err
            )
        return False
    return True


def get_vrf_device_assignment(vrf_name: str, device_name: str) -> Optional[VRFDeviceAssignment]:
    """Return the row assigning the named VRF, in the run's Namespace, to the named Device, if there is one."""
    return VRFDeviceAssignment.objects.filter(
        vrf__name=vrf_name,
        vrf__namespace=get_run_namespace(),
        device__name=device_name,
    ).first()


def create_vrf_device_assignment(  # pylint: disable=too-many-arguments
    vrf_name: str,
    device_name: str,
    scope: DeviceScope,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
) -> Optional[VRFDeviceAssignment]:
    """Record that a Device carries a VRF.

    The assignment inherits the VRF's route distinguisher and name, which is what Nautobot's own
    `clean()` would do. Set here rather than left to it, so that a row written in a batch, where
    `clean()` never runs, is the same row as one written on its own.

    Args:
        vrf_name: Name of the VRF, in the run's Namespace.
        device_name: Name of the Device carrying it.
        scope: The Devices this run covers; see `DeviceScope`.
        logger: Logger to use for messaging.
        writer: What writes the assignment, and where a VRF or Device queued earlier in the run is
            found.

    Returns:
        VRFDeviceAssignment: When the assignment is created or queued.
        None: When either end could not be found, or Nautobot refused the row.
    """
    # Either end may have been queued earlier in this run and so have no row yet, which is where a
    # bulk mode sync finds both of them. Looked for there first, since the lookups below are cached
    # and would otherwise remember that a queued object could not be found.
    vrf_obj = writer.find(VRF, vrf_name) or get_vrf(vrf_name, logger=logger)
    if vrf_obj is None:
        if logger:
            logger.error("Unable to find a VRF named %s to assign to the Device named %s", vrf_name, device_name)
        return None
    device_obj = writer.find(Device, device_name) or get_syncable_device(device_name, scope=scope)
    if device_obj is None:
        if logger:
            logger.error("Unable to find a Device named %s to assign the VRF named %s to", device_name, vrf_name)
        return None

    assignment = VRFDeviceAssignment(
        vrf=vrf_obj,
        device=device_obj,
        rd=vrf_obj.rd,
        name=vrf_obj.name,
    )
    try:
        writer.create(assignment)
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(
                "Unable to assign the VRF named %s to the Device named %s. Error: %s", vrf_name, device_name, err
            )
        return None
    return assignment


@job_scoped_cache(group=BULK_WRITTEN_LOOKUPS)
def get_vrf(name: str, logger: Optional[logging.Logger] = None) -> Optional[VRF]:
    """Return the run's Namespace VRF of the given name, or None when there is not exactly one.

    Nautobot constrains a VRF to a unique route distinguisher within its Namespace, but not to a
    unique name, so one Namespace may hold two VRFs called the same thing. IP Fabric reports a VRF
    name as network wide and offers nothing to tell those two apart, so an ambiguous name is
    reported rather than resolved arbitrarily.

    Args:
        name: VRF name, as IP Fabric reports it.
        logger: Logger to use for messaging.

    Returns:
        VRF: The one VRF of that name in the run's Namespace.
        None: When no VRF has that name, or more than one does.
    """
    vrfs = list(VRF.objects.filter(name=name, namespace=get_run_namespace())[:2])
    if not vrfs:
        return None
    if len(vrfs) > 1:
        if logger:
            logger.error(
                "Namespace %s holds more than one VRF named %s, so which one IP Fabric is "
                "reporting cannot be determined; leaving them alone",
                get_run_namespace(),
                name,
            )
        return None
    return vrfs[0]


def create_vrf(  # pylint: disable=too-many-arguments
    name: str,
    rd: Optional[str],
    vrf_status: str,
    conflict: str,
    logger: Optional[logging.Logger] = None,
    *,
    writer: "Writer",
    tenant: Optional[Tenant] = None,
) -> Optional[VRF]:
    """Create a VRF in the run's Namespace.

    With a Tenant, an existing VRF of the name is adopted rather than duplicated, since the run reads
    only its Tenant's VRFs and so did not load one that has no Tenant. A name the Namespace holds
    more than once is refused, as the loader refuses it.

    Args:
        name: VRF name.
        rd: Route distinguisher, or None when IP Fabric reports none for it.
        vrf_status: Status name to set.
        conflict: What IP Fabric reported inconsistently for this VRF, or an empty string.
        logger: Logger to use for messaging.
        writer: What writes a new VRF. A queued one already has its primary key, so its join rows may
            be queued behind it.

    Returns:
        VRF: When the VRF is created or queued.
        None: When Nautobot refuses it.
    """
    status_obj = get_or_create_status_object(vrf_status, ColorChoices.COLOR_GREEN, app_label="ipam", model="vrf")
    if tenant is not None:
        existing = list(VRF.objects.filter(name=name, namespace=get_run_namespace())[:2])
        if len(existing) > 1:
            if logger:
                logger.error(
                    "Not creating a VRF named %s, as Namespace %s already holds more than one",
                    name,
                    get_run_namespace(),
                )
            return None
        if existing:
            vrf_obj = existing[0]
            claim_for_tenant(vrf_obj, tenant)
            vrf_obj.rd = rd or None
            vrf_obj.status = status_obj
            vrf_obj.cf[VRF_CONFLICT_CF_NAME] = conflict
            try:
                tag_object(nautobot_object=vrf_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
            except (DjangoBaseDBError, ValidationError) as err:
                if logger:
                    logger.error("Unable to adopt the VRF named %s. Error: %s", name, err)
                return None
            return vrf_obj
    vrf_obj = VRF(
        name=name,
        rd=rd or None,
        status=status_obj,
        namespace=get_run_namespace(),
        tenant=tenant,
    )
    vrf_obj.cf[VRF_CONFLICT_CF_NAME] = conflict
    try:
        # Queued, a route distinguisher that collides is refused by the database rather than by
        # `clean()`, so the collector's narrowing finds and reports it like any other bad row.
        writer.create(vrf_obj, key=name)
    except (DjangoBaseDBError, ValidationError) as err:
        # A route distinguisher is unique within a Namespace, so a network reporting one RD on two
        # VRF names reaches here for the second of them.
        if logger:
            logger.error("Unable to create a VRF named %s with a route distinguisher of %s. Error: %s", name, rd, err)
        return None
    return vrf_obj


@job_scoped_cache
def get_tagged_pks(model: Any, tag_id: Any) -> frozenset:
    """Return the primary keys of the model's objects already carrying the given Tag.

    Resolved once per model and Tag for the whole run. Asking whether one object carries a Tag is a
    query, and a sync removing a hundred thousand Interfaces would otherwise ask it that many times.
    Objects tagged during the run are not added here, as each is only ever considered once.
    """
    return frozenset(model.objects.filter(tags__id=tag_id).values_list("pk", flat=True))


def objects_left_on_the_default_synced_tag() -> int:
    """Return how many objects carry the default synced Tag while none carries the configured one.

    That is the state after `ipfabric_synced_tag` is changed without renaming the Tag in Nautobot,
    and also the first run of a second IP Fabric instance given a Tag of its own. Only the operator
    knows which, so the caller warns rather than refusing to run.
    """
    if SYNCED_TAG_NAME == DEFAULT_SYNCED_TAG_NAME:
        return 0
    if TaggedItem.objects.filter(tag__name=SYNCED_TAG_NAME).exists():
        return 0
    return TaggedItem.objects.filter(tag__name=DEFAULT_SYNCED_TAG_NAME).count()


def synced_tag_for(nautobot_object: Any, tag_name: str = SYNCED_TAG_NAME) -> Tag:
    """Return the Tag marking an object as synced from IP Fabric, for that object's content type."""
    content_type = ContentType.objects.get_for_model(nautobot_object)
    return get_or_create_tag_object(
        tag_name=tag_name,
        tag_color=ColorChoices.COLOR_LIGHT_GREEN,
        description="Object synced at some point from IPFabric to Nautobot",
        app_label=content_type.app_label,
        model=content_type.model,
    )


def queue_synced_tag(pending: Any, nautobot_object: Any, tag_name: str = SYNCED_TAG_NAME):
    """Queue the row tagging an object as synced, for an object being written in bulk.

    `tags.add` needs a saved object and issues its own statements, so a queued object gets the join
    row directly instead. Written after the object it points at, which the collector guarantees.
    """
    if not hasattr(nautobot_object, "tags"):
        # A `BaseModel` such as a through row carries no Tags, so there is no row to write.
        return
    pending.add_through(
        TaggedItem(
            content_type=ContentType.objects.get_for_model(nautobot_object),
            object_id=nautobot_object.pk,
            tag=synced_tag_for(nautobot_object, tag_name=tag_name),
        )
    )


def queue_new_object(pending: Any, instance: Any, key: Optional[Any] = None, through_rows: Iterable[Any] = ()):
    """Queue a newly built object for a batched write, with its stamp, Tag row and any join rows.

    The three go together: a queued object is never saved, so the stamp has to be on it before it is
    inserted and the Tag has to arrive as its own row. Kept in one place so that a model added later
    cannot queue a row without them.
    """
    stamp_synced(instance, LAST_SYNCHRONIZED_CF_NAME)
    pending.add(instance, key=key)
    for row in through_rows:
        pending.add_through(row)
    queue_synced_tag(pending, instance)
    return instance


def stamp_synced(nautobot_object: Any, custom_field: str):
    """Record this integration as the object's source of record, without saving it.

    Separate from `tag_object` so that a newly built object can be stamped before the one save it
    takes, rather than saved again afterwards purely to carry the stamp.
    """
    if hasattr(nautobot_object, "cf"):
        nautobot_object.cf["system_of_record"] = "IPFabric"
        nautobot_object.cf[custom_field] = datetime.date.today().isoformat()


def restamp_synced(nautobot_object: Any, custom_field: str, tag_name: str = SYNCED_TAG_NAME):
    """Record this run against an object the sync found unchanged, in as few statements as it takes.

    A re-sync that changes nothing still has to say it saw each object, and for most of them the
    stamp is the only thing to write. Doing that through `validated_save()` costs about eleven
    queries an object, because `IPAddress.save()` calls `clean()` and `clean()` issues three of its
    own, so on an estate of a hundred thousand addresses the run that changes nothing is the most
    expensive thing the integration does. One `UPDATE` of the custom field data says the same.

    What that skips is validation, the signals and the change log entry. None is a loss here: the
    object is unchanged apart from this integration's own bookkeeping, nothing revalidates by
    standing still, and an entry recording only that the date moved is noise in an object's history.

    For a caller that did change a field, `tag_object` is still the way to write it.
    """
    if not hasattr(nautobot_object, "cf"):
        return
    tag = synced_tag_for(nautobot_object, tag_name=tag_name)
    # `tags.add` is its own pair of statements, so it is asked for only where the Tag is missing.
    if hasattr(nautobot_object, "tags") and nautobot_object.pk not in get_tagged_pks(type(nautobot_object), tag.id):
        nautobot_object.tags.add(tag)
    stamp_synced(nautobot_object, custom_field)
    type(nautobot_object).objects.filter(pk=nautobot_object.pk).update(
        _custom_field_data=nautobot_object._custom_field_data  # pylint: disable=protected-access
    )


def tag_object(
    nautobot_object: Any,
    custom_field: str,
    tag_name: Optional[str] = SYNCED_TAG_NAME,
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
