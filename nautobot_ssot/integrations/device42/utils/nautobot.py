# pylint: disable=duplicate-code
"""Utility functions for Nautobot ORM."""

import logging
import random
from typing import List, OrderedDict
from uuid import UUID

from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from nautobot.circuits.models import CircuitType
from nautobot.dcim.models import Device, Interface, Platform
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Relationship, Role, Tag
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER_REVERSE, NAPALM_LIB_MAPPER_REVERSE
from taggit.managers import TaggableManager
from nautobot_ssot.integrations.device42.diffsync.models.base.dcim import Device as NautobotDevice

logger = logging.getLogger(__name__)

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM  # noqa: F401 # pylint: disable=unused-import

    LIFECYCLE_MGMT = True
except ImportError:
    logger.info("Device Lifecycle app isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False
except RuntimeError:
    logger.warning(
        "nautobot-device-lifecycle-mgmt is installed but not enabled. Did you forget to add it to your settings.PLUGINS?"
    )
    LIFECYCLE_MGMT = False


def get_random_color() -> str:
    """Get random hex code color string.

    Returns:
        str: Hex code value for a color with hash stripped.
    """
    return f"{random.randint(0, 0xFFFFFF):06x}"  # nosec: B311


def verify_device_role(diffsync, role_name: str, role_color: str = "") -> UUID:
    """Verifies DeviceRole object exists in Nautobot. If not, creates it.

    Args:
        diffsync (obj): DiffSync Job object.
        role_name (str): Name of role to verify.
        role_color (str): Color of role to verify. Must be hex code format.

    Returns:
        UUID: ID of found or created DeviceRole object.
    """
    if not role_color:
        role_color = get_random_color()
    try:
        role_obj = diffsync.role_map[role_name]
    except KeyError:
        role_obj = Role.objects.create(name=role_name, color=role_color)
        role_obj.content_types.add(ContentType.objects.get_for_model(Device))
        role_obj.validated_save()
        diffsync.role_map[role_name] = role_obj.id
        role_obj = role_obj.id
    return role_obj


def verify_platform(diffsync, platform_name: str, manu: UUID) -> UUID:
    """Verifies Platform object exists in Nautobot. If not, creates it.

    Args:
        diffsync (obj): DiffSync Job with maps.
        platform_name (str): Name of platform to verify.
        manu (UUID): The ID (primary key) of platform manufacturer.

    Returns:
        UUID: UUID for found or created Platform object.
    """
    if ANSIBLE_LIB_MAPPER_REVERSE.get(platform_name):
        _name = ANSIBLE_LIB_MAPPER_REVERSE[platform_name]
    else:
        _name = platform_name
    if NAPALM_LIB_MAPPER_REVERSE.get(platform_name):
        napalm_driver = NAPALM_LIB_MAPPER_REVERSE[platform_name]
    else:
        napalm_driver = platform_name
    try:
        platform_obj = diffsync.platform_map[_name]
    except KeyError:
        platform_obj = Platform(
            name=_name,
            manufacturer_id=manu,
            napalm_driver=napalm_driver[:50],
            network_driver=platform_name,
        )
        platform_obj.validated_save()
        diffsync.platform_map[_name] = platform_obj.id
        platform_obj = platform_obj.id
    return platform_obj


def get_or_create_mgmt_intf(intf_name: str, dev: Device) -> Interface:
    """Creates a Management interface with specified name.

    This is expected to be used when assigning a management IP to a device that doesn't
    have a Management interface and we can't determine which one to assign the IP to.

    Args:
        intf_name (str): Name of Interface to be created.
        dev (Device): Device object for Interface to be assigned to.

    Returns:
        Interface: Management Interface object that was created.
    """
    # check if Interface already exists, returns it or creates it
    try:
        mgmt_intf = Interface.objects.get(name=intf_name.strip(), device__name=dev.name)
    except Interface.DoesNotExist:
        print(f"Mgmt Intf Not Found! Creating {intf_name} {dev.name}")
        mgmt_intf = Interface(
            name=intf_name.strip(),
            device=dev,
            type="other",
            enabled=True,
            mgmt_only=True,
        )
        mgmt_intf.validated_save()
    return mgmt_intf


def get_or_create_tag(tag_name: str) -> Tag:
    """Finds or creates a Tag that matches `tag_name`.

    Args:
        tag_name (str): Name of Tag to be created.

    Returns:
        Tag: Tag object that was found or created.
    """
    try:
        _tag = Tag.objects.get(name=tag_name)
    except Tag.DoesNotExist:
        new_tag = Tag(
            name=tag_name,
            color=get_random_color(),
        )
        new_tag.validated_save()
        _tag = new_tag
    return _tag


def get_tags(tag_list: List[str]) -> List[Tag]:
    """Gets list of Tags from list of strings.

    This is the opposite of the `get_tag_strings` function.

    Args:
        tag_list (List[str]): List of Tags as strings to find.

    Returns:
        (List[Tag]): List of Tag object primary keys matching list of strings passed in.
    """
    return [get_or_create_tag(x) for x in tag_list if x != ""]


def update_tags(tagged_obj: object, new_tags: List[str]):
    """Update tags on Nautobot object to match what is provided in new tags.

    Args:
        tagged_obj (object): Nautobot object with Tags attached.
        new_tags (List[str]): List of updated Tags.
    """
    current_tags = tagged_obj.tags.names()
    for tag in new_tags:
        if tag not in current_tags:
            tagged_obj.tags.add(tag)
    for tag in current_tags:
        if tag not in new_tags:
            tagged_obj.tags.remove(tag)


def get_tag_strings(list_tags: TaggableManager) -> List[str]:
    """Gets string values of all Tags in a list.

    This is the opposite of the `get_tags` function.

    Args:
        list_tags (TaggableManager): List of Tag objects to convert to strings.

    Returns:
        List[str]: List of string values matching the Tags passed in.
    """
    _strings = list(list_tags.names())
    if len(_strings) > 1:
        _strings.sort()
    return _strings


def get_custom_field_dict(cfields: OrderedDict) -> dict:
    """Creates dictionary of CustomField with CF key, value, and description.

    Args:
        cfields (OrderedDict): List of CustomFields with their value.

    Returns:
        cf_dict (dict): Return a dict of CustomField with key, value, and note (description).
    """
    cf_dict = {}
    for _cf, _cf_value in cfields.items():
        cf_dict[_cf.label] = {
            "key": _cf.label,
            "value": _cf_value,
            "notes": _cf.description if _cf.description != "" else None,
        }
    return cf_dict


def update_custom_fields(new_cfields: dict, update_obj: object):
    """Update passed object's CustomFields.

    Args:
        new_cfields (OrderedDict): Dictionary of CustomFields on object to be updated to match.
        update_obj (object): Object to be updated with CustomFields.
    """
    current_cf = get_custom_field_dict(update_obj.get_custom_fields())
    for old_cf, old_cf_dict in current_cf.items():
        if old_cf not in new_cfields:
            removed_cf = CustomField.objects.get(
                label=old_cf_dict["key"], content_types=ContentType.objects.get_for_model(type(update_obj))
            )
            removed_cf.delete()
    for new_cf, new_cf_dict in new_cfields.items():
        new_key = new_cf_dict["key"].replace(" ", "_").replace("-", "_")
        if new_cf not in current_cf:
            _cf_dict = {
                "key": new_key,
                "type": CustomFieldTypeChoices.TYPE_TEXT,
                "label": new_cf_dict["key"],
            }
            field, _ = CustomField.objects.get_or_create(key=_cf_dict["key"], defaults=_cf_dict)
            field.content_types.add(ContentType.objects.get_for_model(type(update_obj)).id)
        update_obj.custom_field_data.update({new_key: new_cf_dict["value"]})


def verify_circuit_type(circuit_type: str) -> CircuitType:
    """Method to find or create a CircuitType in Nautobot.

    Args:
        circuit_type (str): Name of CircuitType to be found or created.

    Returns:
        CircuitType: CircuitType object found or created.
    """
    try:
        _ct = CircuitType.objects.get(name=circuit_type)
    except CircuitType.DoesNotExist:
        _ct = CircuitType(
            name=circuit_type,
        )
        _ct.validated_save()
    return _ct


def get_software_version_from_lcm(relations: dict):
    """Method to obtain Software version for a Device from Relationship.

    Args:
        relations (dict): Results of a `get_relationships()` on a Device.

    Returns:
        str: String of SoftwareLCM version.
    """
    version = ""
    if LIFECYCLE_MGMT:
        _softwarelcm = Relationship.objects.get(label="Software on Device")
        if _softwarelcm in relations["destination"]:
            if len(relations["destination"][_softwarelcm]) > 0:
                if hasattr(relations["destination"][_softwarelcm][0].source, "version"):
                    version = relations["destination"][_softwarelcm][0].source.version
    return version


def get_version_from_custom_field(fields: OrderedDict):
    """Method to obtain a software version for a Device from its custom fields."""
    for field, value in fields.items():
        if field.label == "OS Version":
            return value
    return ""


def determine_vc_position(vc_map: dict, virtual_chassis: str, device_name: str) -> int:
    """Determine position of Member Device in Virtual Chassis based on name and other factors.

    Args:
        vc_map (dict): Dictionary of virtual chassis positions mapped to devices.
        virtual_chassis (str): Name of the virtual chassis that device is being added to.
        device_name (str): Name of member device to be added in virtual chassis.

    Returns:
        int: Position for member device in Virtual Chassis. Will always be position 2 or higher as 1 is master device.
    """
    return sorted(vc_map[virtual_chassis]["members"]).index(device_name) + 2


def get_dlc_version_map():
    """Method to create nested dictionary of Software versions mapped to their ID along with Platform.

    This should only be used if the Device Lifecycle app is found to be installed.

    Returns:
        dict: Nested dictionary of versions mapped to their ID and to their Platform.
    """
    version_map = {}
    for ver in SoftwareLCM.objects.only("id", "device_platform", "version"):
        if ver.device_platform.network_driver not in version_map:
            version_map[ver.device_platform.network_driver] = {}
        version_map[ver.device_platform.network_driver][ver.version] = ver.id
    return version_map


def get_cf_version_map():
    """Method to create nested dictionary of Software versions mapped to their ID along with Platform.

    This should only be used if the Device Lifecycle app is not found. It will instead use custom field "OS Version".

    Returns:
        dict: Nested dictionary of versions mapped to their ID and to their Platform.
    """
    version_map = {}
    for dev in Device.objects.only("id", "platform", "_custom_field_data"):
        if dev.platform.name not in version_map:
            version_map[dev.platform.name] = {}
        if "os-version" in dev.custom_field_data:
            version_map[dev.platform.name][dev.custom_field_data["OS Version"]] = dev.id
    return version_map


def apply_vlans_to_port(diffsync, device_name: str, mode: str, vlans: list, port: Interface):
    """Determine appropriate VLANs to add to a Port link.

    Args:
        diffsync (DiffSyncAdapter): DiffSync Adapter with get and vlan_map.
        device_name (str): Name of Device associated to Port.
        mode (str): Port mode, access or trunk.
        vlans (list): List of VLANs to be attached to Port.
        port (Interface): Port to have VLANs applied to.
    """
    try:
        dev = diffsync.get(NautobotDevice, device_name)
        site_name = dev.building
    except ObjectNotFound:
        site_name = "Global"
    if mode == "access" and len(vlans) == 1:
        _vlan = vlans[0]
        port.untagged_vlan_id = diffsync.vlan_map[site_name][_vlan]
    else:
        tagged_vlans = []
        for _vlan in vlans:
            tagged_vlan = diffsync.vlan_map[site_name][_vlan]
            if tagged_vlan:
                tagged_vlans.append(tagged_vlan)
        port.tagged_vlans.set(tagged_vlans)
        port.validated_save()
