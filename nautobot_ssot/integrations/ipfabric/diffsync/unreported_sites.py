"""Keep what belongs to the Devices at a site IP Fabric does not report, when Locations are out of scope."""

from typing import Set

from diffsync import Adapter
from diffsync.enum import DiffSyncModelFlags

# Top-level models tied to a Device, each mapped to the fields that hold its Device's name.
UNREPORTED_SITE_DEPENDENTS = {
    "cable": ("termination_a_device", "termination_b_device"),
    "vrf_device_assignment": ("device_name",),
    "interface_vrf": ("device_name",),
    "interface_vlan": ("device_name",),
}


def shield_unreported_sites(adapter: Adapter, reported: Set[str]) -> None:
    """Flag the Cables and assignments of the Devices at a site the source does not report, so the diff keeps them.

    With Locations out of scope, a Location the source does not report is skipped along with the
    Devices and Interfaces under it, since the sync holds no opinion on which sites exist. Cables,
    VRF assignments and the VRFs and VLANs set on Interfaces are top level rather than under it,
    so this function flags each one with `SKIP_UNMATCHED_DST` as well. The source lacks them only
    because it lacks their site, not because they were deleted. A Cable is flagged when either end
    is at such a site.

    Calling this twice on the same adapter has the same effect as calling it once.

    Args:
        adapter: The destination adapter, whose models are flagged.
        reported: The names of the Locations the source reports.
    """
    unreported = {device.name for device in adapter.get_all("device") if device.location_name not in reported}
    for model_name, device_fields in UNREPORTED_SITE_DEPENDENTS.items():
        for instance in adapter.get_all(model_name):
            if any(getattr(instance, field) in unreported for field in device_fields):
                instance.model_flags |= DiffSyncModelFlags.SKIP_UNMATCHED_DST
