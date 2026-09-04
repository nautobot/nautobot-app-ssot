"""Diff sync shared adapter class attritbutes to synchronize applications."""

from typing import ClassVar, Optional

from diffsync import Adapter

from nautobot_ssot.integrations.ipfabric.diffsync import diffsync_models
from nautobot_ssot.integrations.ipfabric.sync_scope import (
    UNSYNCED_LOCATION_ATTRS,
    UNSYNCED_LOCATION_FLAGS,
    SyncScope,
)


class DiffSyncModelAdapters(Adapter):
    """Nautobot adapter for DiffSync."""

    safe_delete_mode: ClassVar[bool] = True

    # The collector to queue writes into, or None when they go one at a time. Declared here so that
    # a model may ask any adapter; only the destination adapter ever sets it.
    pending = None

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

    def __init__(self, *args, scope: Optional[SyncScope] = None, **kwargs):
        """Initialize the adapter with the object types this run covers.

        Held on the shared base so that both adapters read one scope. They only agree about what is
        in scope by construction if there is one place for it to come from.
        """
        super().__init__(*args, **kwargs)
        self.scope = scope if scope is not None else SyncScope.from_job_kwargs({})

    def location_model(self, name: str, *, site_id: Optional[str], status: str):
        """Return the Location model to load, in scope or out of it.

        Out of scope a Location is loaded as a tree node rather than as data, since every Device and
        VLAN is a child of one: placeholder attributes so it diffs as unchanged, and a flag so one the
        source does not report is not deleted. Built here because the placeholders only cancel out
        while both adapters report the same ones.
        """
        if self.scope.locations:
            return self.location(adapter=self, name=name, site_id=site_id, status=status)
        node = self.location(adapter=self, name=name, **UNSYNCED_LOCATION_ATTRS)
        node.model_flags |= UNSYNCED_LOCATION_FLAGS
        return node
