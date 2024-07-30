"""Utility functions for working with Nautobot."""

from nautobot.ipam.models import PrefixLocationAssignment, VRFPrefixAssignment


def get_vrf_prefix_assignments(prefix):
    """Retreive all VRF assignments for a Prefix and return a list of VRF Names."""
    _assignments = []
    _vrf_assignments = VRFPrefixAssignment.objects.filter(prefix_id=prefix.id)

    if _vrf_assignments:
        for _vrf in _vrf_assignments:
            _assignments.append(f"{_vrf.vrf.name}__{prefix.namespace.name}")
        return _assignments

    return None


def get_prefix_location_assignments(prefix):
    """Retrieve all Location assignments for a Prefix and return a list of Location Names."""
    _locations = []
    _location_assignments = PrefixLocationAssignment.objects.filter(prefix_id=prefix.id)

    if _location_assignments:
        for _location in _location_assignments:
            _locations.append(_location.location.name)
        return _locations

    return None
