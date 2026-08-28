"""Batched writes for a bulk mode IP Fabric sync.

A sync that writes each object on its own spends most of its time in `validated_save()`. Writing in
batches is much faster, and is what `bulk_write_mode` on the job form turns on. It costs the
per-object `clean()`, the signals, and a change log entry each; database constraints still apply.

Two things make batching workable here:

Nautobot assigns every model a UUID primary key when the instance is constructed, not when it is
saved. A child can therefore be built holding a reference to a parent that has not been written yet,
and the reference is valid as soon as the parent's row exists. `LEVELS` is the order that guarantees.

`bulk_create` does not call `save()`, so anything a model computes there has to be supplied by the
caller instead. What each model needs is recorded in the admin documentation; the collector here
takes objects that are already complete and does not add to them.

Cables are deliberately absent. Creating one also sets `cable`, `_cable_peer` and `_path` on both
Interfaces it terminates on, and builds the Cable paths, all through signals that a batched insert
does not fire. They keep the per-object path.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from django.db import IntegrityError, transaction
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


class PendingWrites:
    """Objects built but not yet written, plus the join rows and field updates that follow them."""

    def __init__(self, batch_size: int = WRITE_BATCH_SIZE):
        """Start empty, writing `batch_size` rows per statement."""
        self.batch_size = batch_size
        self._queued: Dict[Any, List[Any]] = {model: [] for model in LEVELS}
        self._keys: Dict[Any, Dict[Any, Any]] = {model: {} for model in LEVELS}
        self._through: Dict[Any, List[Any]] = defaultdict(list)
        self._updates: List[Tuple[Any, Tuple[str, ...]]] = []

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

    def defer_update(self, instance: Any, fields: Iterable[str]) -> Any:
        """Queue a field update on an object, applied after every insertion.

        For values that are only known once something later in the order exists, such as the IP
        Address a Device carries as its primary.
        """
        self._updates.append((instance, tuple(fields)))
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
        """
        written = 0
        for model in LEVELS:
            written += self._insert(model, self._queued[model])
            self._queued[model] = []
            self._keys[model] = {}
        for model in THROUGH_LEVELS:
            written += self._insert(model, self._through[model])
            self._through[model] = []
        written += self._apply_updates()
        return written

    def _insert(self, model: Any, objects: List[Any]) -> int:
        """Insert the given objects in batches, falling back to one at a time on refusal."""
        written = 0
        for start in range(0, len(objects), self.batch_size):
            batch = objects[start : start + self.batch_size]
            try:
                # Its own savepoint, so a refused batch leaves the transaction usable.
                with transaction.atomic():
                    model.objects.bulk_create(batch)
            except (IntegrityError, DjangoBaseDBError):
                written += self._insert_one_at_a_time(model, batch)
            else:
                written += len(batch)
        return written

    @staticmethod
    def _insert_one_at_a_time(model: Any, objects: List[Any]) -> int:
        """Insert objects individually, so one row a batch refused does not lose the rest.

        Validated on the way in, since a batch is only retried like this because something in it was
        wrong and the offending row is worth naming.
        """
        written = 0
        for instance in objects:
            try:
                with transaction.atomic():
                    instance.validated_save()
            except (IntegrityError, DjangoBaseDBError, ValidationError) as error:
                logger.warning("Unable to write %s %s in bulk mode: %s", model.__name__, instance, error)
            else:
                written += 1
        return written

    def _apply_updates(self) -> int:
        """Apply the deferred field updates, grouped by model and by the fields they touch."""
        written = 0
        by_model_and_fields = defaultdict(list)
        for instance, fields in self._updates:
            by_model_and_fields[(type(instance), fields)].append(instance)
        self._updates = []

        for (model, fields), instances in by_model_and_fields.items():
            try:
                with transaction.atomic():
                    model.objects.bulk_update(instances, fields, batch_size=self.batch_size)
            except (IntegrityError, DjangoBaseDBError) as error:
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
