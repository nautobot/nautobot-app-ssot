"""Per object type checks that IP Fabric actually reported what a synced object needs.

This is a layer on top of the sync scope, not another copy of it. The scope decides which object
types a run covers; strictness applies only within those, and asks a different question of each one:
may what IP Fabric said be taken on trust, or should it be checked first?

Without it the sync takes the report at face value and fills any gap itself. A site name becomes a
Location, a model becomes a Device Type, a family becomes a Platform, an address with no reported
subnet becomes a host route, and a management address matching no reported Interface gets an
Interface invented to hold it. Where the data is good that is exactly right, and it is what makes
bootstrapping an empty Nautobot work. Where it is not, a typo mints a near duplicate that is
indistinguishable from a curated record, an address lands under the wrong parent Prefix, or Nautobot
holds an Interface that is not on the device.

Selected, the type is checked instead. For a supporting object the check is that the name resolves to
something Nautobot already holds; for an address it is that IP Fabric reported a subnet mask for it;
for an Interface it is that IP Fabric reported the Interface. What fails the check is reported and
the affected record left unwritten, and the sync carries on with the rest.

Every entry defaults to taking the report on trust, except `ip_addresses`. Whether a name may be
trusted depends on who owns the object, which only the operator knows; a mask the source never
reported is not data whoever owns IPAM.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Tuple

from nautobot.extras.jobs import MultiChoiceVar

from nautobot_ssot.integrations.ipfabric import sync_scope
from nautobot_ssot.integrations.ipfabric.constants import CONFIG

# Name of the job form field and of the job keyword argument.
FIELD_NAME = "strict_objects"


@dataclass(frozen=True)
class StrictObject:
    """An object type whose reported value the sync can be told to check rather than trust.

    `scoped` records whether the type also has a sync scope toggle. Declared rather than discovered,
    so that `validate_registry` can hold the two registries to it: a key misspelled here would
    otherwise read as a type the scope does not govern, which is silently the wrong answer.
    """

    key: str
    label: str
    description: str
    default: bool = False
    scoped: bool = True

    @property
    def setting_name(self) -> str:
        """Settings key that overrides this object type's default selection."""
        return f"ipfabric_strict_{self.key}"

    def default_selection(self) -> bool:
        """Return the default form selection, which `PLUGINS_CONFIG` may override."""
        return bool(CONFIG.get(self.setting_name, self.default))


# Object types strictness can be applied to, in the order they appear on the job form.
#
# Every entry names a type the scope can cover; nothing here brings a type into scope, and selecting
# one that is out of scope does nothing. `StrictObjects.explanations` reports that rather than
# leaving the selection looking like the reason nothing was written.
STRICT_OBJECTS: Tuple[StrictObject, ...] = (
    StrictObject(
        key="locations",
        label="Locations",
        description="a site name that matches no Location is reported, and the Devices at it skipped",
    ),
    StrictObject(
        key="manufacturers",
        label="Manufacturers",
        description="a vendor that matches no Manufacturer is reported, and no Device Type filed under it",
    ),
    StrictObject(
        key="device_types",
        label="Device Types",
        description="a model that matches no Device Type is reported, and the Device skipped, as it needs one",
    ),
    StrictObject(
        key="roles",
        label="Roles",
        description="a role that matches no Role is reported, and the Device skipped, as it needs one",
    ),
    StrictObject(
        key="platforms",
        label="Platforms",
        description="a family that matches no Platform is reported, and the Device synced without one",
    ),
    StrictObject(
        key="statuses",
        scoped=False,
        label="Statuses",
        description="a status that matches no Status is reported, and the record that needed it skipped",
    ),
    StrictObject(
        key="virtual_chassis",
        scoped=False,
        label="Virtual Chassis",
        description="a stack that matches no Virtual Chassis is reported, and its membership left unrecorded",
    ),
    StrictObject(
        key="interfaces",
        label="Interfaces",
        description=(
            "no Interface is invented for a management address IP Fabric reports against none, "
            "leaving that address unsynced"
        ),
    ),
    StrictObject(
        key="ip_addresses",
        label="IP Addresses",
        description="an address IP Fabric reports no subnet mask for is reported, and left as Nautobot holds it",
        default=True,
    ),
)


def validate_registry(objects: Iterable[StrictObject]) -> Dict[str, StrictObject]:
    """Index the registry by key, rejecting a registration that could never work.

    A duplicate key would collapse two object types into one choice. A `scoped` value disagreeing
    with the sync scope registry means the two are joined on a key one of them does not have, which
    `SyncScope.covers` reads as a type the scope does not govern and so always covers — silently the
    wrong answer for what is usually a typo. Both are mistakes worth failing at import rather than
    at sync time.
    """
    by_key: Dict[str, StrictObject] = {}
    for strict_object in objects:
        if strict_object.key in by_key:
            raise ValueError(f"Duplicate object type {strict_object.key!r}")
        if strict_object.scoped != sync_scope.is_registered(strict_object.key):
            raise ValueError(
                f"{strict_object.key!r} declares scoped={strict_object.scoped}, which disagrees with "
                f"the sync scope registry"
            )
        by_key[strict_object.key] = strict_object
    return by_key


_BY_KEY: Dict[str, StrictObject] = validate_registry(STRICT_OBJECTS)


def default_keys() -> Tuple[str, ...]:
    """Return the object types strict by default, which `PLUGINS_CONFIG` may override."""
    return tuple(strict_object.key for strict_object in STRICT_OBJECTS if strict_object.default_selection())


def form_field() -> MultiChoiceVar:
    """Return the job form field naming the object types to be checked rather than trusted.

    One field rather than a checkbox per type: the choices are a set, and the form already carries a
    toggle per object type for the scope. Each type's own description goes into this field's, since
    what the check costs differs by type and there is nowhere else on the form to say so.
    """
    consequences = "; ".join(f"{strict_object.label}, {strict_object.description}" for strict_object in STRICT_OBJECTS)
    return MultiChoiceVar(
        choices=[(strict_object.key, strict_object.label) for strict_object in STRICT_OBJECTS],
        default=list(default_keys()),
        required=False,
        label="Strict Objects",
        description=(
            "Object types whose reported value is checked rather than trusted, on top of what is "
            "in scope. Nothing here brings a type into scope. Select the types another system is "
            f"authoritative for, so the sync reports bad data instead of filling the gap: {consequences}."
        ),
    )


class StrictObjects:
    """The object types one run of the sync checks rather than trusts.

    Resolved once from the submitted job form, then read by both adapters so that they cannot
    disagree. Attribute access mirrors the registry, so `strict.locations` reads as the choice it
    came from.
    """

    def __init__(self, enabled: Iterable[str]):
        """Build a strictness from the object types selected, ignoring any this version does not know."""
        self._enabled = {key for key in enabled if key in _BY_KEY}

    @classmethod
    def from_job_kwargs(cls, kwargs: Dict) -> "StrictObjects":
        """Build a strictness from a job's keyword arguments.

        A missing field falls back to the defaults, so that a run through the API or a schedule
        created before this field existed behaves as the form would have. An empty selection is a
        selection, not a missing one, so it is honoured.
        """
        selected = kwargs.get(FIELD_NAME)
        if selected is None:
            selected = default_keys()
        return cls(selected)

    def is_enabled(self, key: str) -> bool:
        """Return whether the named object type is checked rather than trusted.

        Says nothing about whether the type is in scope. `DiffSyncModelAdapters.may_create` puts the
        two together, and the scope decides first.
        """
        return key in self._enabled

    def __getattr__(self, name: str) -> bool:
        """Expose each registered object type as an attribute, for a key known at author time."""
        if name in _BY_KEY:
            return self.is_enabled(name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __iter__(self) -> Iterator[str]:
        """Iterate the object types being matched rather than created, in registration order."""
        return (strict_object.key for strict_object in STRICT_OBJECTS if strict_object.key in self._enabled)

    def __repr__(self) -> str:
        """Return a representation naming the object types this run is strict about."""
        return f"{type(self).__name__}({self.describe()})"

    def describe(self) -> str:
        """Return a one line summary for the job log."""
        return ", ".join(self) or "nothing"

    def explanations(self, scope: sync_scope.SyncScope) -> List[str]:
        """Return a message for each selection this run's scope has left nothing to check.

        Strictness checks what the sync was going to write, so a type out of scope has nothing for it
        to act on. Worth saying, so that an operator reading the log does not take the selection for
        the reason nothing was written. Takes the scope rather than holding one, since the two
        controls are resolved independently and only the run knows both.
        """
        return [
            f"Not checking '{key}', as it is out of scope for this sync and so nothing is written for it."
            for key in self
            if not scope.covers(key)
        ]
