# pylint: disable=duplicate-code
"""Utility functions for Nautobot ORM."""
import datetime
import logging
from typing import Any, Optional

from django.contrib.contenttypes.models import ContentType
from django.db import Error as DjangoBaseDBError
from django.core.exceptions import ValidationError
from netutils.ip import netmask_to_cidr
from netutils.lib_mapper import NAPALM_LIB_MAPPER
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Manufacturer,
    Location,
    LocationType,
    Platform,
)
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Role, Tag
from nautobot.extras.models.statuses import Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix, VLAN
from nautobot.ipam.choices import PrefixTypeChoices
from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME


# pylint: disable=too-many-branches


def create_location(
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
        location_obj, _ = Location.objects.get_or_create(
            name=location_name,
            location_type=LocationType.objects.get(name="Site"),
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


def create_manufacturer(vendor_name: str, logger: Optional[logging.Logger] = None) -> Optional[Manufacturer]:
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


def create_device_type_object(
    device_type: str,
    vendor_name: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[DeviceType]:
    """Create a specified device type in Nautobot.

    Args:
        device_type: Device model gathered from DiffSync model.
        vendor_name: Vendor Name.
        logger: Logger to use for messaging.

    Returns:
        DeviceType: When a DeviceType Object is retrieved or created.
        None: When there is a failure in getting or creating a DeviceType.
    """
    manufacturer_obj = create_manufacturer(vendor_name, logger=logger)
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


def create_platform_object(
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
    if platform == "ios-xe":
        network_driver = "cisco_ios"
        napalm_driver = "cisco_ios"
    else:
        network_driver = f"{manufacturer_obj.name.lower()}_{platform.lower()}"
        napalm_driver = NAPALM_LIB_MAPPER.get(platform, "")

    defaults = {"network_driver": network_driver, "napalm_driver": napalm_driver}
    try:
        platform_obj, _ = Platform.objects.get_or_create(
            name=platform,
            manufacturer=manufacturer_obj,
            defaults=defaults,
        )
        return platform_obj
    except Platform.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple Platforms returned with the name {platform}")
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new Platform named {platform}")
    return None


def get_or_create_device_role_object(
    role_name: str,
    role_color: str,
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


def create_status(  # pylint: disable=too-many-arguments
    status_name: str,
    status_color: str,
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


def create_ip(
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
        status_obj = Status.objects.get_for_model(IPAddress).get(name=status)
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
        namespace_obj = Namespace.objects.get(name="Global")
        cidr = netmask_to_cidr(subnet_mask)
        ip_obj = None
        try:
            ip_obj, _ = IPAddress.objects.get_or_create(address=f"{ip_address}/{cidr}", status=status_obj)
        except IPAddress.MultipleObjectsReturned:
            if logger:
                logger.error(f"Multiple IPAddresses returned with the address of {ip_address}/{subnet_mask}")
        except (DjangoBaseDBError, ValidationError):
            try:
                parent, _ = Prefix.objects.get_or_create(
                    network="0.0.0.0",  # nosec B104
                    prefix_length=0,
                    type=PrefixTypeChoices.TYPE_NETWORK,
                    status=Status.objects.get_for_model(Prefix).get(name="Active"),
                    namespace=namespace_obj,
                )
            except (DjangoBaseDBError, ValidationError):
                if logger:
                    logger.error(f"Unable to create a new IPAddress of {ip_address}/{subnet_mask}")
            else:
                try:
                    ip_obj, _ = IPAddress.objects.get_or_create(
                        address=f"{ip_address}/{cidr}", status=status_obj, parent=parent
                    )
                except (DjangoBaseDBError, ValidationError):
                    if logger:
                        logger.error(f"Unable to create a new IPAddress of {ip_address}/{subnet_mask}")

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
                try:
                    # Tag Interface (object_pk)
                    tag_object(nautobot_object=object_pk, custom_field=LAST_SYNCHRONIZED_CF_NAME)
                except (DjangoBaseDBError, ValidationError):
                    if logger:
                        logger.warning(
                            f"Unable to perform validated_save() on Interface {object_pk.name} with an ID of {object_pk.id}"
                        )

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
    try:
        status_obj = Status.objects.get_for_model(Interface).get(name=status)
    except Status.MultipleObjectsReturned:
        if logger:
            logger.error(
                f"Multiple Statuses returned with name {status}, "
                f"and therefore cannot create an Interface named {interface_name}"
            )
    except Status.DoesNotExist:
        if logger:
            logger.error(
                f"Unable to find a Status with the name {status}, "
                f"and therefore cannot create an Interface named {interface_name}"
            )
    else:
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
                logger.error(
                    f"Multiple Interfaces returned with name {interface_name} on Device named {device_obj.name}"
                )
        except (DjangoBaseDBError, ValidationError):
            if logger:
                logger.error(
                    f"Unable to create a new Interface named {interface_name} on Device named {device_obj.name}"
                )
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
    try:
        vlan_obj, _ = location_obj.vlans.get_or_create(
            name=vlan_name, vid=vlan_id, status=Status.objects.get(name=vlan_status), description=description
        )
    except VLAN.MultipleObjectsReturned:
        if logger:
            logger.error(f"Multiple VLANs returned with name {vlan_name} and ID {vlan_id}")
    except (DjangoBaseDBError, ValidationError):
        if logger:
            logger.error(f"Unable to create a new VLAN named {vlan_name} with an ID {vlan_id}")
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


def tag_object(nautobot_object: Any, custom_field: str, tag_name: Optional[str] = "SSoT Synced from IPFabric"):
    """Apply the given tag and custom field to the identified object.

    Args:
        nautobot_object (Any): Nautobot ORM Object
        custom_field (str): Name of custom field to update
        tag_name (Optional[str], optional): Tag name. Defaults to "SSoT Synced From IPFabric".
    """
    if tag_name == "SSoT Synced from IPFabric":
        tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={
                "description": "Object synced at some point from IPFabric to Nautobot",
                "color": ColorChoices.COLOR_LIGHT_GREEN,
            },
        )
    else:
        tag, _ = Tag.objects.get_or_create(name=tag_name)

    today = datetime.date.today().isoformat()

    def _tag_object(nautobot_object):
        """Apply custom field and tag to object, if applicable."""
        if hasattr(nautobot_object, "tags"):
            nautobot_object.tags.add(tag)
        if hasattr(nautobot_object, "cf"):
            # Update custom field date stamp
            nautobot_object.cf["system_of_record"] = "IPFabric"
            nautobot_object.cf[custom_field] = today
        nautobot_object.validated_save()

    _tag_object(nautobot_object)
    # Ensure proper save
