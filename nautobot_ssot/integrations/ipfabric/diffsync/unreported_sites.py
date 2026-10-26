"""Keeping what belongs to the Devices at a site IP Fabric does not report, when Locations are out of scope."""

from typing import Set

from diffsync import Adapter
from diffsync.enum import DiffSyncModelFlags

# The top-level models that belong to a Device, by the fields naming it.
UNREPORTED_SITE_DEPENDENTS = {
    "cable": ("termination_a_device", "termination_b_device"),
    "vrf_device_assignment": ("device_name",),
    "interface_vrf": ("device_name",),
    "interface_vlan": ("device_name",),
}


def shield_unreported_sites(adapter: Adapter, reported: Set[str]) -> None:
    """Leave the Cables and assignments of the Devices at a site the source does not report alone.

    With Locations out of scope, a Location the source does not report is skipped along with the
    Devices and Interfaces under it, since the sync holds no opinion on which sites exist. Cables,
    VRF assignments and the VRFs and VLANs set on Interfaces are top level rather than under it,
    so each is flagged the same way here: absent from the source because its site is, not because
    it is gone. A Cable is shielded when either end is at such a site.

    A Device with no Location counts as at an unreported site, so what belongs to it is kept. The
    flags stay set, so flagging the same adapter again before its sync changes nothing.

    Args:
        adapter: The destination adapter, whose models are flagged.
        reported: The names of the Locations the source reports.
    """
    unreported = {device.name for device in adapter.get_all("device") if device.location_name not in reported}
    for model_name, device_fields in UNREPORTED_SITE_DEPENDENTS.items():
        for instance in adapter.get_all(model_name):
            if any(getattr(instance, field) in unreported for field in device_fields):
                instance.model_flags |= DiffSyncModelFlags.SKIP_UNMATCHED_DST
