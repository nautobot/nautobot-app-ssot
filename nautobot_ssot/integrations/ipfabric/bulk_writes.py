"""Batched writes for a bulk mode IP Fabric sync.

A sync that writes each object on its own spends most of its time in `validated_save()`. Writing in
batches is much faster, and is what `bulk_write_mode` on the job form turns on. It costs the
per-object `clean()`, the signals, and a change log entry each; database constraints still apply.

Two things make batching workable here:

Nautobot assigns every model a UUID primary key when the instance is constructed, not when it is
saved. A child can therefore be built holding a reference to a parent that has not been written yet,
and the reference is valid as soon as the parent's row exists. `LEVELS` is the order that guarantees.

`bulk_create` does not call `save()`, so anything a model computes there has to be supplied by the
caller instead. The collector takes objects that are already complete and does not add to them, so
what each model needs stays at the call site that knows: an IP Address arrives with the Prefix it
belongs under, a VLAN with its location assignment row.

Cables are deliberately absent. Creating one also sets `cable`, `_cable_peer` and `_path` on both
Interfaces it terminates on, and builds the Cable paths, all through signals that a batched insert
does not fire. They keep the per-object path.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import Error as DjangoBaseDBError
from django.db import connection, transaction
from nautobot.dcim.models import Device, Interface, Location
from nautobot.extras.models import TaggedItem
from nautobot.ipam.models import VLAN, IPAddress, IPAddressToInterface, VLANLocationAssignment

logger = logging.getLogger("nautobot.ssot.ipfabric")

# How many rows to insert per statement.
WRITE_BATCH_SIZE = 1000

# Insertion order. A model may only reference one before it: an Interface needs its Device, a VLAN
# its Location. IP Addresses reference no queued model, only Prefixes, which are written as they are
# resolved because there are few of them.
LEVELS: Tuple[Any, ...] = (Location, Device, Interface, IPAddress, VLAN)

# Join tables, written once the rows they point at exist. None of these define `save()`, so there is
# nothing for a batched insert to skip.
THROUGH_LEVELS: Tuple[Any, ...] = (TaggedItem, IPAddressToInterface, VLANLocationAssignment)


def _check_deferred_constraints(model: Any) -> None:
    """Check the foreign keys of a just written batch, where the database would otherwise defer them.

    PostgreSQL declares foreign keys deferrable and checks them at `COMMIT`, and that commit belongs
    to whichever model operation triggered the flush, not to the collector. Checking here turns a
    broken reference into a refusal this batch can report and retry, instead of a failure that ends
    the job and loses every write in the enclosing transaction.
    """
    if connection.features.can_defer_constraint_checks:
        connection.check_constraints(table_names=[model._meta.db_table])  # pylint: disable=protected-access


class PendingWrites:
    """Objects built but not yet written, plus the join rows and field updates that follow them."""

    def __init__(self, batch_size: int = WRITE_BATCH_SIZE):
        """Start empty, writing `batch_size` rows per statement."""
        self.batch_size = batch_size
        self._queued: Dict[Any, List[Any]] = {model: [] for model in LEVELS}
        self._keys: Dict[Any, Dict[Any, Any]] = {model: {} for model in LEVELS}
        self._through: Dict[Any, List[Any]] = defaultdict(list)
        self._updates: List[Tuple[Any, Dict[str, Any]]] = []

    def add(self, instance: Any, key: Optional[Any] = None) -> Any:
        """Queue an object for insertion, optionally findable later by `key`.

        Returns the instance, so a caller can go straight on to using its primary key.
        """
        model = type(instance)
        if model not in self._queued:
            raise ValueError(f"{model.__name__} is not a level this collector writes")
        self._queued[model].append(instance)
        if key is not None:
            self._keys[model][key] = instance
        return instance

    def find(self, model: Any, key: Any) -> Optional[Any]:
        """Return an object queued under `key`, or None if this run has not built one."""
        return self._keys.get(model, {}).get(key)

    def add_through(self, row: Any) -> Any:
        """Queue a join table row, written after the rows it references."""
        model = type(row)
        if model not in THROUGH_LEVELS:
            raise ValueError(f"{model.__name__} is not a join table this collector writes")
        self._through[model].append(row)
        return row

    def defer_update(self, instance: Any, values: Mapping[str, Any]) -> Any:
        """Queue field values to set on an object, applied after every insertion.

        The values are assigned when the update is applied rather than now, because what they point
        at may be written later in the order: a Device carries its primary IP Address, and Addresses
        are written after Devices. Assigning one to a Device that is itself still queued would insert
        that Device holding a foreign key to a row that does not exist yet, which PostgreSQL refuses
        at `COMMIT` and which takes the whole batch with it.
        """
        self._updates.append((instance, dict(values)))
        return instance

    def __len__(self) -> int:
        """Return how many rows are waiting, across everything."""
        queued = sum(len(objects) for objects in self._queued.values())
        through = sum(len(rows) for rows in self._through.values())
        return queued + through + len(self._updates)

    def counts(self) -> Dict[str, int]:
        """Return what is waiting, by model name, for logging."""
        counts = {model.__name__: len(objects) for model, objects in self._queued.items() if objects}
        counts.update({model.__name__: len(rows) for model, rows in self._through.items() if rows})
        if self._updates:
            counts["field updates"] = len(self._updates)
        return counts

    def flush(self) -> int:
        """Write everything queued, parents before children, and return how many rows were written.

        Empties the collector as it goes, so a caller may flush repeatedly.

        A row the database refuses is reported and skipped rather than ending the flush, so the join
        rows and updates that reference it are dropped with it. Writing them anyway would point them
        at nothing, and a foreign key to nothing fails the transaction the flush is running inside.
        """
        written = 0
        missing: Set[Any] = set()
        for model in LEVELS:
            written += self._insert(model, self._queued[model], missing)
            self._queued[model] = []
            self._keys[model] = {}
        for model in THROUGH_LEVELS:
            rows = self._without_missing_references(model, self._through[model], missing)
            written += self._insert(model, rows, missing)
            self._through[model] = []
        written += self._apply_updates(missing)
        return written

    @staticmethod
    def _without_missing_references(model: Any, rows: List[Any], missing: Set[Any]) -> List[Any]:
        """Return the rows that reference only objects which were written, reporting the rest."""
        if not missing:
            return rows
        foreign_keys = [field for field in model._meta.concrete_fields if field.many_to_one]  # pylint: disable=protected-access
        kept = [row for row in rows if not any(getattr(row, field.attname) in missing for field in foreign_keys)]
        if len(kept) != len(rows):
            logger.warning(
                "Skipped %d %s rows in bulk mode because an object they reference could not be written",
                len(rows) - len(kept),
                model.__name__,
            )
        return kept

    def _insert(self, model: Any, objects: List[Any], missing: Set[Any]) -> int:
        """Insert the given objects in batches, falling back to one at a time on refusal.

        The primary keys of any objects that could not be written are added to `missing`.
        """
        written = 0
        for start in range(0, len(objects), self.batch_size):
            batch = objects[start : start + self.batch_size]
            try:
                # Its own savepoint, so a refused batch leaves the transaction usable.
                with transaction.atomic():
                    model.objects.bulk_create(batch)
                    _check_deferred_constraints(model)
            except DjangoBaseDBError:
                written += self._insert_one_at_a_time(model, batch, missing)
            else:
                written += len(batch)
        return written

    @staticmethod
    def _insert_one_at_a_time(model: Any, objects: List[Any], missing: Set[Any]) -> int:
        """Insert objects individually, so one row a batch refused does not lose the rest.

        Validated on the way in, since a batch is only retried like this because something in it was
        wrong and the offending row is worth naming.
        """
        written = 0
        for instance in objects:
            # `bulk_create` marks everything it hands to the database as saved, and a constraint
            # PostgreSQL defers to `COMMIT` fails after that, so the batch being retried here was
            # rolled back while its objects still look written. Left that way, `save()` would issue
            # an `UPDATE` matching no rows, and a `clean()` that reads its own row back would raise
            # `DoesNotExist` instead of a validation error.
            instance._state.adding = True  # pylint: disable=protected-access
            try:
                with transaction.atomic():
                    instance.validated_save()
                    _check_deferred_constraints(model)
            except (DjangoBaseDBError, ValidationError, ObjectDoesNotExist) as error:
                logger.warning("Unable to write %s %s in bulk mode: %s", model.__name__, instance, error)
                missing.add(instance.pk)
            else:
                written += 1
        return written

    def _apply_updates(self, missing: Set[Any]) -> int:
        """Apply the deferred field updates, grouped by model and by the fields they touch.

        An update is dropped when its own object or the object it points at could not be written.
        """
        written = 0
        by_model_and_fields = defaultdict(list)
        for instance, values in self._updates:
            if instance.pk in missing or any(getattr(value, "pk", None) in missing for value in values.values()):
                logger.warning(
                    "Unable to set %s on %s %s in bulk mode, as an object it references could not be written",
                    ", ".join(values),
                    type(instance).__name__,
                    instance,
                )
                continue
            for field, value in values.items():
                setattr(instance, field, value)
            by_model_and_fields[(type(instance), tuple(sorted(values)))].append(instance)
        self._updates = []

        for (model, fields), instances in by_model_and_fields.items():
            try:
                with transaction.atomic():
                    model.objects.bulk_update(instances, fields, batch_size=self.batch_size)
            except DjangoBaseDBError as error:
                logger.warning(
                    "Unable to update %s on %d %s objects in bulk mode: %s",
                    ", ".join(fields),
                    len(instances),
                    model.__name__,
                    error,
                )
            else:
                written += len(instances)
        return written
