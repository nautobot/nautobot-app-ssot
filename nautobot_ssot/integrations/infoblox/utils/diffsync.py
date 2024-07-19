"""Utilities for DiffSync related stuff."""

from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify
from nautobot.extras.models import CustomField, Tag
from nautobot.ipam.models import VLAN, IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox.constant import TAG_COLOR


def create_tag_sync_from_infoblox():
    """Create tag for tagging objects that have been created by Infoblox."""
    tag, _ = Tag.objects.get_or_create(
        name="SSoT Synced from Infoblox",
        defaults={
            "name": "SSoT Synced from Infoblox",
            "description": "Object synced at some point from Infoblox",
            "color": TAG_COLOR,
        },
    )
    for model in [IPAddress, Namespace, Prefix, VLAN]:
        tag.content_types.add(ContentType.objects.get_for_model(model))
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


def get_ext_attr_dict(extattrs: dict, excluded_attrs: Optional[list] = None):
    """Rebuild Extensibility Attributes dict into standard k/v pattern.

    The standard extattrs dict pattern is to have the dict look like so:

    {<attribute_key>: {"value": <actual_value>}}

    Args:
        extattrs (dict): Extensibility Attributes dict for object.
        excluded_attrs (list): List of Extensibility Attributes to exclude.

    Returns:
        dict: Standardized dictionary for Extensibility Attributes.
    """
    if excluded_attrs is None:
        excluded_attrs = []
    fixed_dict = {}
    for key, value in extattrs.items():
        if key in excluded_attrs:
            continue
        fixed_dict[slugify(key).replace("-", "_")] = value["value"]
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


def get_valid_custom_fields(cfs: dict, excluded_cfs: Optional[list] = None):
    """Remove custom fields that are on the excluded list.

    Args:
        cfs: custom fields
        excluded_cfs: list of excluded custom fields
    """
    if excluded_cfs is None:
        excluded_cfs = []
    default_excluded_cfs = [
        "dhcp_ranges",
        "dns_a_record_comment",
        "dns_host_record_comment",
        "dns_ptr_record_comment",
        "fixed_address_comment",
        "mac_address",
        "ssot_synced_to_infoblox",
    ]
    excluded_cfs.extend(default_excluded_cfs)
    valid_cfs = {}
    for cf_name, val in cfs.items():
        if cf_name in excluded_cfs:
            continue
        valid_cfs[cf_name] = val

    return valid_cfs


def get_default_custom_fields(cf_contenttype: ContentType, excluded_cfs: Optional[list] = None) -> dict:
    """Get default Custom Fields for specific ContentType.

    Args:
        cf_contenttype (ContentType): Specific ContentType to get all Custom Fields for.

    Returns:
        dict: Dictionary of all Custom Fields for a specific object type.
    """
    if excluded_cfs is None:
        excluded_cfs = []
    customfields = CustomField.objects.filter(content_types=cf_contenttype)
    # These cfs are always excluded
    default_excluded_cfs = [
        "dhcp_ranges",
        "dns_a_record_comment",
        "dns_host_record_comment",
        "dns_ptr_record_comment",
        "fixed_address_comment",
        "mac_address",
        "ssot_synced_to_infoblox",
    ]
    # User defined excluded cfs
    excluded_cfs.extend(default_excluded_cfs)
    default_cfs = {}
    for customfield in customfields:
        if customfield.key in excluded_cfs:
            continue
        if customfield.key not in default_cfs:
            default_cfs[customfield.key] = None
    return default_cfs


def map_network_view_to_namespace(value: str, direction: str) -> str:
    """Remaps Infoblox Network View name to Nautobot Namespace name.

    This matters most for mapping default "default" Network View to default Namespace "Global".

    Args:
        network_view (str): Infoblox Network View name

    Returns:
        (str) corresponding Nautobot Namespace name
    """
    network_view_to_namespace = {
        "default": "Global",
    }
    namespace_to_network_view = {ns: nv for nv, ns in network_view_to_namespace.items()}

    if direction == "nv_to_ns":
        return network_view_to_namespace.get(value, value)
    if direction == "ns_to_nv":
        return namespace_to_network_view.get(value, value)

    return None


def validate_dns_name(infoblox_client: object, dns_name: str, network_view: str) -> bool:
    """Checks if DNS name matches any of the zones found in Infoblox.

    Args:
        (object) infoblox_conn: Infoblox API client
        (str) dns_name: DNS name
        (str) network_view: network view name

    Returns:
        (bool)
    """
    dns_view = infoblox_client.get_dns_view_for_network_view(network_view=network_view)
    zones = infoblox_client.get_authoritative_zones_for_dns_view(view=dns_view)
    dns_name_valid = False
    for zone in zones:
        if zone["fqdn"] in dns_name:
            dns_name_valid = True
            break

    return dns_name_valid
