"""Utility functions for Nautobot Cable objects synced from IP Fabric.

Nautobot stores Cable terminations either on the `termination_a`/`termination_b` foreign keys or in
the `CableToCableTermination` join table, depending on the version. Creating and reading a Cable is
the same on both, but the `select_related` path that avoids a query per Interface is not, so the two
layouts are distinguished here rather than at each call site.
"""

import logging
from typing import Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from nautobot.dcim.models import Cable, Interface

from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import get_or_create_status_object, tag_object

# The join table layout replaces the concrete `cable` field with a reverse relation to
# `CableToCableTermination`, which is what decides the query path in `cabled_interfaces`.
CABLE_TERMINATIONS_ARE_JOINED = not any(field.name == "cable" for field in Interface._meta.get_fields())

# A single end of a link, as a (device name, interface name) pair.
Endpoint = Tuple[str, str]


def canonical_endpoints(first: Endpoint, second: Endpoint) -> Tuple[Endpoint, Endpoint]:
    """Order a link's two ends, lowest first, so both sides of the sync derive the same identifier.

    IP Fabric reports each link once from each device's point of view and Nautobot records an
    arbitrary end as the A side, so neither source agrees on which end is which.
    """
    return tuple(sorted((first, second)))


def cabled_interfaces(device_queryset):
    """Return the Interfaces of the given Devices that terminate a Cable.

    The Device, the Cable and the Cable's Status are selected alongside so that reading them while
    iterating does not issue a query per Interface.
    """
    interfaces = Interface.objects.filter(device__in=device_queryset).select_related("device")
    if CABLE_TERMINATIONS_ARE_JOINED:
        return interfaces.filter(cable_termination__isnull=False).select_related("cable_termination__cable__status")
    return interfaces.filter(cable__isnull=False).select_related("cable__status")


def cable_connects(cable: Cable, interface_a: Interface, interface_b: Interface) -> bool:
    """Determine whether a Cable terminates on exactly the two given Interfaces.

    Compares termination IDs so that establishing identity does not fetch either Interface.
    """
    return {cable.termination_a_id, cable.termination_b_id} == {interface_a.pk, interface_b.pk}


def create_cable(  # pylint: disable=too-many-arguments
    interface_a: Interface,
    interface_b: Interface,
    status: str,
    logger: Optional[logging.Logger] = None,
    create_statuses: bool = True,
) -> Optional[Cable]:
    """Create a Cable between two Interfaces.

    Args:
        interface_a: Interface to terminate the A side on.
        interface_b: Interface to terminate the B side on.
        status: Status name to assign to the Cable.
        logger: Logger to use for messaging.
        create_statuses: Whether the Cable's Status may be created when none of that name exists.

    Returns:
        Cable: When the Cable is created.
        None: When there is a failure in creating the Cable.
    """
    status_obj = get_or_create_status_object(
        status, app_label="dcim", model="cable", create=create_statuses, logger=logger
    )
    if not status_obj:
        if logger:
            logger.error(
                f"Unable to resolve a Status named {status}, so no Cable will be created between "
                f"{interface_a.device.name}:{interface_a.name} and {interface_b.device.name}:{interface_b.name}"
            )
        return None
    cable = Cable(termination_a=interface_a, termination_b=interface_b, status=status_obj)
    try:
        cable.validated_save()
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(
                f"Unable to create a new Cable between {interface_a.device.name}:{interface_a.name} and "
                f"{interface_b.device.name}:{interface_b.name}. Error: {err}"
            )
        return None
    try:
        # tag_object performs validated_save()
        tag_object(nautobot_object=cable, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.warning(f"Unable to perform a validated_save() on Cable with an ID of {cable.id}")
    return cable


def update_cable_status(
    cable: Cable,
    status: str,
    logger: Optional[logging.Logger] = None,
    create_statuses: bool = True,
) -> bool:
    """Set a Cable's Status and record that it was synced from IP Fabric.

    Args:
        cable: Cable to update.
        status: Status name to assign to the Cable.
        logger: Logger to use for messaging.
        create_statuses: Whether the Status may be created when none of that name exists.

    Returns:
        True when the Cable was saved, False when it could not be.
    """
    if cable.status.name != status:
        status_obj = get_or_create_status_object(
            status, app_label="dcim", model="cable", create=create_statuses, logger=logger
        )
        if not status_obj:
            if logger:
                logger.error(
                    f"Unable to resolve a Status named {status}, "
                    f"so Cable with an ID of {cable.id} will not be updated"
                )
            return False
        cable.status = status_obj
    try:
        # tag_object performs validated_save()
        tag_object(nautobot_object=cable, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    except (DjangoBaseDBError, ValidationError) as err:
        if logger:
            logger.error(f"Unable to update Cable with an ID of {cable.id} to a Status of {status}. Error: {err}")
        return False
    return True
