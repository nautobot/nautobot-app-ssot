"""Utilities for DiffSync related stuff."""
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify
from nautobot.extras.models import CustomField, Tag
from nautobot_ssot_infoblox.constant import TAG_COLOR


def create_tag_sync_from_infoblox():
    """Create tag for tagging objects that have been created by Infoblox."""
    tag, _ = Tag.objects.get_or_create(
        slug="ssot-synced-from-infoblox",
        defaults={
            "name": "SSoT Synced from Infoblox",
            "description": "Object synced at some point from Infoblox",
            "color": TAG_COLOR,
        },
    )
    return tag


def get_vlan_view_name(reference):
    """Get the Infoblox vlanview name by the reference resource string.

    Args:
        reference (str): Vlan view Reference resource.

    Returns:
        (str): Vlan view name.

    Returns Response:
        "Nautobot"
    """
    return reference.split("/")[1].split(":")[-1]


def nautobot_vlan_status(status: str) -> str:
    """Return VLAN Status from mapping."""
    statuses = {
        "Active": "ASSIGNED",
        "Deprecated": "UNASSIGNED",
        "Reserved": "RESERVED",
    }
    return statuses[status]


def get_ext_attr_dict(extattrs: dict):
    """Rebuild Extensibility Attributes dict into standard k/v pattern.

    The standard extattrs dict pattern is to have the dict look like so:

    {<attribute_key>: {"value": <actual_value>}}

    Args:
        extattrs (dict): Extensibility Attributes dict for object.

    Returns:
        dict: Standardized dictionary for Extensibility Attributes.
    """
    fixed_dict = {}
    for key, value in extattrs.items():
        fixed_dict[slugify(key)] = value["value"]
    return fixed_dict


def build_vlan_map(vlans: list):
    """Build map of VLAN ID to VLAN name.

    Args:
        vlans (list): List of VLANs assigned to

    Returns:
        dict: Dictionary mapping VLAN ID to VLAN name, VLAN ID, and VLAN View (group).
    """
    vlan_map = {}
    for vlan in vlans:
        vlan_map[vlan["id"]] = {"vid": vlan["id"], "name": vlan["name"], "group": get_vlan_view_name(vlan["vlan"])}
    return vlan_map


def get_default_custom_fields(cf_contenttype: ContentType) -> dict:
    """Get default Custom Fields for specific ContentType.

    Args:
        cf_contenttype (ContentType): Specific ContentType to get all Custom Fields for.

    Returns:
        dict: Dictionary of all Custom Fields for a specific object type.
    """
    customfields = CustomField.objects.filter(content_types=cf_contenttype)
    default_cfs = {}
    for customfield in customfields:
        if customfield.name != "ssot-synced-to-infoblox":
            if customfield.name not in default_cfs:
                default_cfs[customfield.name] = None
    return default_cfs
