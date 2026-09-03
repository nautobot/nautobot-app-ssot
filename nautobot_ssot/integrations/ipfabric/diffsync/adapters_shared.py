"""Diff sync shared adapter class attritbutes to synchronize applications."""

from typing import ClassVar, Optional, Set, Tuple

from diffsync import Adapter

from nautobot_ssot.integrations.ipfabric.diffsync import diffsync_models
from nautobot_ssot.integrations.ipfabric.strict_mode import StrictObjects
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

    def __init__(
        self,
        *args,
        scope: Optional[SyncScope] = None,
        strict: Optional[StrictObjects] = None,
        interfaces_without_a_subnet: Optional[Set[Tuple[str, str]]] = None,
        **kwargs,
    ):
        """Initialize the adapter with the object types this run covers.

        Held on the shared base so that both adapters read one scope and one strictness. They only
        agree about what is in scope, and about what they may create, by construction if there is one
        place for each to come from.

        The two controls answer different questions. The scope decides which object types this run
        covers; strictness is a further check, on the types it does cover, that what IP Fabric
        reported about them can be taken on trust.

        `interfaces_without_a_subnet` holds the `(device name, interface name)` of every Interface
        whose address IP Fabric reports no subnet for. The IP Fabric adapter fills it while loading
        and reports no address for those Interfaces; the Nautobot adapter is handed it afterwards so
        that it reports none either. Reporting one side and not the other would leave the address
        diffed on every run without ever being applied, and the mask Nautobot holds is the better of
        the two values anyway.
        """
        super().__init__(*args, **kwargs)
        self.scope = scope if scope is not None else SyncScope.from_job_kwargs({})
        self.strict = strict if strict is not None else StrictObjects.from_job_kwargs({})
        self.interfaces_without_a_subnet = set() if interfaces_without_a_subnet is None else interfaces_without_a_subnet

    def carries_pseudo_management_interface(self) -> bool:
        """Return whether this run reports the Interface fabricated for a NAT management address.

        Read by both adapters so that the condition exists once. The IP Fabric adapter invents the
        Interface only when this holds, and the Nautobot adapter withholds an existing one when it
        does not; written as two conditions, the two would have to stay exact opposites by hand, and
        a pairing broken on one side alone reads as absent from the source and deletes the record.
        """
        return self.scope.ip_addresses and not self.strict.interfaces

    def may_create(self, key: str) -> bool:
        """Return whether this run may create a supporting object of the named type.

        The scope decides first, and on its own: a type this run does not sync is not one it creates,
        and strictness has nothing to say about a type that is not being synced at all. Within what
        is synced, strictness is the further question of whether a name IP Fabric reported may be
        taken on trust. Strict, a name that resolves to nothing is bad data rather than a record
        to add.

        For the supporting object types only. `interfaces` and `ip_addresses` are also registered as
        strict, but neither is a creation gate: those two ask whether IP Fabric reported an Interface
        and whether it reported a subnet mask, and both are read at their own load sites rather than
        through here.
        """
        if not self.scope.covers(key):
            return False
        return not self.strict.is_enabled(key)

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
