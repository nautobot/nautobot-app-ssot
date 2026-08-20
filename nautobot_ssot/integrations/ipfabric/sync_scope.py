"""Per object type controls over what an IP Fabric sync covers.

Every object type the integration can synchronize is registered here once, and the job form, the
resolved scope a run works from, and the administrative deny list are all derived from that single
registration. Adding a new object type means adding a `SyncableObject` and gating both adapters on
it, rather than threading another keyword argument through the job and both adapters.

Two rules make the toggles safe to act on:

* A toggle must gate **both** adapters. Loading an object type from Nautobot but not from IP Fabric
  makes every existing record look absent from the source, which a sync would then delete.
* A type whose parent is disabled is disabled with it, because it has nothing to attach to. The
  `requires` field records those edges and `SyncScope` closes over them.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Tuple

from diffsync.enum import DiffSyncModelFlags
from nautobot.extras.jobs import BooleanVar

from nautobot_ssot.integrations.ipfabric.constants import CONFIG

# Settings key holding the object types that may not be selected on the job form at all.
DISABLED_OBJECTS_SETTING = "ipfabric_disabled_sync_objects"


@dataclass(frozen=True)
class SyncableObject:
    """An object type whose synchronization can be turned on and off independently."""

    key: str
    label: str
    description: str
    default: bool
    requires: Tuple[str, ...] = field(default=())

    @property
    def field_name(self) -> str:
        """Name of the job form field and of the job keyword argument."""
        return f"sync_{self.key}"

    @property
    def setting_name(self) -> str:
        """Settings key that overrides this object type's default selection."""
        return f"ipfabric_sync_{self.key}"

    def default_selection(self) -> bool:
        """Return the default form selection, which `PLUGINS_CONFIG` may override."""
        return bool(CONFIG.get(self.setting_name, self.default))

    def form_field(self) -> BooleanVar:
        """Return the job form field for this object type."""
        description = self.description
        if self.requires:
            required = ", ".join(f"'{key}'" for key in self.requires)
            description = f"{description} Skipped unless {required} is also selected."
        return BooleanVar(default=self.default_selection(), label=self.label, description=description)


# Object types that can be turned on and off, in the order they appear on the job form.
#
# Devices are deliberately absent. Every other object type is either a Device or hangs off one, so
# a run with Devices disabled has nothing left to do.
#
# Locations are present but special: they are the root of the object tree, so they keep being read
# even when out of scope. Deselecting them withholds only the writing of them; see
# `UNSYNCED_LOCATION_ATTRS` and `unsynced_location_flags`.
SYNCABLE_OBJECTS: Tuple[SyncableObject, ...] = (
    SyncableObject(
        key="locations",
        label="Sync Locations",
        description=(
            "Create, update and delete Nautobot Locations from IP Fabric sites. Deselect where "
            "another system owns the site list; Devices at Locations that already exist in Nautobot "
            "are still synced, but a site IP Fabric has discovered will not be created, and neither "
            "will the Devices at it."
        ),
        default=True,
    ),
    SyncableObject(
        key="interfaces",
        label="Sync Interfaces",
        description="Sync each Device's Interfaces.",
        default=True,
    ),
    SyncableObject(
        key="ip_addresses",
        label="Sync IP Addresses",
        description="Sync the IP Address on each Interface.",
        default=True,
        requires=("interfaces",),
    ),
    SyncableObject(
        key="primary_ip",
        label="Sync Primary IP",
        description=(
            "Assign a Device's primary IP from IP Fabric. IP Fabric reports the address it logged in "
            "with, which is not necessarily the address a CMDB considers the management one."
        ),
        default=True,
        requires=("ip_addresses",),
    ),
    SyncableObject(
        key="vlans",
        label="Sync VLANs",
        description="Sync each Location's VLANs.",
        default=True,
    ),
    SyncableObject(
        key="cables",
        label="Sync Cables",
        description=(
            "Sync the connections in IP Fabric's connectivity matrix to Nautobot Cables. Only links "
            "whose Devices and Interfaces are both in scope are synced."
        ),
        default=False,
        requires=("interfaces",),
    ),
)


def validate_registry(syncables: Iterable[SyncableObject]) -> Dict[str, SyncableObject]:
    """Index the registry by key, rejecting a registration that could never work.

    A duplicate key would collapse two object types into one form field, and a `requires` entry
    naming an unregistered type would never be satisfied, silently disabling whatever declared it.
    Both are mistakes worth failing at import rather than at sync time.
    """
    by_key: Dict[str, SyncableObject] = {}
    for syncable in syncables:
        if syncable.key in by_key:
            raise ValueError(f"Duplicate object type {syncable.key!r}")
        by_key[syncable.key] = syncable
    for syncable in by_key.values():
        for required in syncable.requires:
            if required not in by_key:
                raise ValueError(f"{syncable.key!r} requires unknown object type {required!r}")
    return by_key


_BY_KEY: Dict[str, SyncableObject] = validate_registry(SYNCABLE_OBJECTS)


def disabled_keys() -> Tuple[str, ...]:
    """Return the object types an administrator has denied for this Nautobot instance."""
    configured = CONFIG.get(DISABLED_OBJECTS_SETTING) or ()
    return tuple(key for key in configured if key in _BY_KEY)


def selectable_objects() -> Tuple[SyncableObject, ...]:
    """Return the object types that may appear on the job form."""
    denied = disabled_keys()
    return tuple(syncable for syncable in SYNCABLE_OBJECTS if syncable.key not in denied)


def form_fields() -> Dict[str, BooleanVar]:
    """Return the job form fields for every selectable object type."""
    return {syncable.field_name: syncable.form_field() for syncable in selectable_objects()}


def scope_field_order() -> Tuple[str, ...]:
    """Return the job form field names, for `Meta.field_order`.

    Names every registered object type rather than only the selectable ones, so that ordering does
    not depend on settings. Django's `order_fields` ignores names it does not find.
    """
    return tuple(syncable.field_name for syncable in SYNCABLE_OBJECTS)


class SyncScope:
    """The object types one run of the sync covers.

    Resolved once from the submitted job form, then read by both adapters so that they cannot
    disagree about what is in scope. Attribute access mirrors the registry, so `scope.cables` reads
    the same as the form field it came from.
    """

    def __init__(self, enabled: Iterable[str]):
        """Build a scope from the object types selected, closing over `requires` and the deny list."""
        self._enabled = {key for key in enabled if key in _BY_KEY}
        self._denied_by_settings = set(disabled_keys()) & self._enabled
        self._enabled -= self._denied_by_settings
        self._disabled_by_parent = self._close_over_requirements()

    def _close_over_requirements(self) -> Dict[str, Tuple[str, ...]]:
        """Drop every object type whose requirements are not met, repeating until nothing changes.

        Iterates rather than walking the graph once so that a chain collapses in full: turning
        Interfaces off has to take IP Addresses with it, and Primary IP with those.
        """
        dropped: Dict[str, Tuple[str, ...]] = {}
        while True:
            newly_dropped = {
                syncable.key: unmet
                for syncable in SYNCABLE_OBJECTS
                if syncable.key in self._enabled
                and (unmet := tuple(key for key in syncable.requires if key not in self._enabled))
            }
            if not newly_dropped:
                return dropped
            self._enabled -= set(newly_dropped)
            dropped.update(newly_dropped)

    @classmethod
    def from_job_kwargs(cls, kwargs: Dict) -> "SyncScope":
        """Build a scope from a job's keyword arguments.

        An object type missing from `kwargs` falls back to its default, so that a job run through
        the API or a scheduled run created before a new object type existed still behaves as the
        form would have.
        """
        return cls(
            syncable.key
            for syncable in SYNCABLE_OBJECTS
            if kwargs.get(syncable.field_name, syncable.default_selection())
        )

    def is_enabled(self, key: str) -> bool:
        """Return whether the named object type is in scope."""
        return key in self._enabled

    def __getattr__(self, name: str) -> bool:
        """Expose each registered object type as an attribute."""
        if name in _BY_KEY:
            return name in self._enabled
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __iter__(self) -> Iterator[str]:
        """Iterate the object types in scope, in registration order."""
        return (syncable.key for syncable in SYNCABLE_OBJECTS if syncable.key in self._enabled)

    def __repr__(self) -> str:
        """Return a representation naming the object types in scope."""
        return f"{type(self).__name__}({', '.join(self) or 'nothing'})"

    def describe(self) -> str:
        """Return a one line summary of what is in scope, for the job log."""
        return ", ".join(f"{key}: {self.is_enabled(key)}" for key in _BY_KEY)

    def explanations(self) -> List[str]:
        """Return a message for each object type dropped for a reason the operator did not choose.

        A selection silently doing nothing is the failure worth reporting: an operator who ticked
        Cables and got no Cables should be told it was Interfaces that decided that.
        """
        messages = []
        for key in sorted(self._denied_by_settings):
            messages.append(
                f"Not syncing '{key}' as it is disabled for this Nautobot instance by the "
                f"'{DISABLED_OBJECTS_SETTING}' setting."
            )
        for key, unmet in sorted(self._disabled_by_parent.items()):
            required = ", ".join(f"'{name}'" for name in unmet)
            messages.append(f"Not syncing '{key}' as it requires {required}, which is not in scope.")
        return messages


# Attribute values both adapters report for a Location that is out of scope.
#
# A Location cannot simply be left unloaded when out of scope, because every Device and VLAN is a
# child of one; drop the Location and its children go with it. So it is still loaded, as a tree node
# rather than as synced data. Reporting the same placeholder attributes from both adapters is what
# makes it a node: the Location matches on its name and diffs as unchanged, so no attribute of it is
# ever written, while its children diff normally.
UNSYNCED_LOCATION_ATTRS = {"site_id": None, "status": "Not synced"}


def unsynced_location_flags() -> DiffSyncModelFlags:
    """Return the model flags that stop an out of scope Location being created or deleted.

    Matching attributes only prevent updates. A Location that exists on one side alone would still
    be created or deleted, taking its children with it, so both unmatched cases are skipped too.
    `SKIP_UNMATCHED_*` applies only to a Location missing from the other side, which is why a matched
    Location still carries its Devices and VLANs into the diff.
    """
    return DiffSyncModelFlags.SKIP_UNMATCHED_BOTH
