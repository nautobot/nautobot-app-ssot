"""Diff sync shared adapter class attritbutes to synchronize applications."""

from typing import ClassVar

from diffsync import Adapter

from nautobot_ssot.integrations.ipfabric.diffsync import diffsync_models


class DiffSyncModelAdapters(Adapter):
    """Nautobot adapter for DiffSync."""

    safe_delete_mode: ClassVar[bool] = True

    location = diffsync_models.Location
    device = diffsync_models.Device
    interface = diffsync_models.Interface
    vlan = diffsync_models.Vlan
    cable = diffsync_models.Cable

    # Cables are top level because a link may span two Locations, and come after "location" so the
    # Devices and Interfaces they terminate on exist by the time they are created.
    top_level = [
        "location",
        "cable",
    ]
