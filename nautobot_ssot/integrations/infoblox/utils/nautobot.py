"""Utility functions for working with Nautobot."""

from nautobot.extras.models import Relationship
from nautobot.ipam.models import Prefix


def build_vlan_map_from_relations(vlans: list):
    """Create a map of VLANs for a Prefix from a list.

    The map should follow the pattern of {vlan_id: {"vid": vlan_id, "name": vlan_name, "group": vlan_group_name}}

    Args:
        vlans (list): List of VLANs that have a RelationshipAssociation to a Prefix.
    """
    vlan_map = {}
    for vlan in vlans:
        vlan_map[vlan.vid] = {"vid": vlan.vid, "name": vlan.name}
        if vlan.vlan_group:
            vlan_map[vlan.vid]["group"] = vlan.vlan_group.name
        else:
            vlan_map[vlan.vid]["group"] = None
    return vlan_map


def get_prefix_vlans(prefix: Prefix) -> list:
    """Get list of current VLANs with RelationshipAssociation to a Prefix.

    Args:
        prefix (Prefix): Prefix to get list of current VLANs with RelationshipAssociation to Prefix.

    Returns:
        list: List of VLAN objects with RelationshipAssociation to passed Prefix.
    """
    pf_relations = prefix.get_relationships()
    pf_vlan_relationship = Relationship.objects.get(label="Prefix -> VLAN")
    return [x.destination for x in pf_relations["source"][pf_vlan_relationship]]
