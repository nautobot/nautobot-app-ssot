"""How the IP Fabric sync writes what it builds: one object at a time, or in batches.

Every ORM helper takes a writer and writes through it, rather than branching on whether a batch is
being collected. `ImmediateWriter` saves each object as it is built, validated, signalled and change
logged. `BatchedWriter` queues it on a `PendingWrites` for Bulk Write Mode. An object a writer hands
back, whether it built it or found it queued, is only ever written through that same writer: a queued
object has no row yet, and saving something that points at it would fail when the run commits.
"""

from typing import Any, Iterable, Mapping, Optional, Union

from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME
from nautobot_ssot.integrations.ipfabric.utilities import nbutils


class ImmediateWriter:
    """Write each object as soon as it is built."""

    batched = False
    pending = None

    def find(self, model: Any, key: Any) -> Optional[Any]:  # pylint: disable=unused-argument
        """Return an object this run queued under `key`; nothing is ever queued here."""
        return None

    def holds(self, instance: Any) -> bool:  # pylint: disable=unused-argument
        """Return whether `instance` is queued rather than written; nothing is."""
        return False

    def create(self, instance: Any, key: Optional[Any] = None, through_rows: Iterable[Any] = ()) -> Any:  # pylint: disable=unused-argument
        """Save a newly built object, stamped and tagged as synced, then its join rows.

        Stamped before its one save, so that the Tag row is the only further write. Raises what
        `validated_save()` raises, for the caller to report.
        """
        nbutils.stamp_synced(instance, LAST_SYNCHRONIZED_CF_NAME)
        instance.validated_save()
        if hasattr(instance, "tags"):
            instance.tags.add(nbutils.synced_tag_for(instance))
        for row in through_rows:
            row.validated_save()
        return instance

    def save(self, instance: Any) -> Any:
        """Save the changes made to an object."""
        instance.validated_save()
        return instance

    def assign(self, row: Any) -> Any:
        """Save a join row."""
        row.validated_save()
        return row

    def set_later(self, instance: Any, values: Mapping[str, Any]) -> Any:
        """Set field values on an object and save it."""
        for field, value in values.items():
            setattr(instance, field, value)
        instance.validated_save()
        return instance


class BatchedWriter:
    """Queue what is built on a `PendingWrites`, for Bulk Write Mode to write in batches."""

    batched = True

    def __init__(self, pending: PendingWrites):
        """Queue on `pending`."""
        self.pending = pending

    def find(self, model: Any, key: Any) -> Optional[Any]:
        """Return an object this run queued under `key`, or None if it has built none."""
        return self.pending.find(model, key)

    def holds(self, instance: Any) -> bool:
        """Return whether `instance` is queued rather than written.

        Everything a batched run builds is queued, so an object without a row is a queued one.
        """
        return instance._state.adding  # pylint: disable=protected-access

    def create(self, instance: Any, key: Optional[Any] = None, through_rows: Iterable[Any] = ()) -> Any:
        """Queue a newly built object, with its stamp, its Tag row and its join rows."""
        return nbutils.queue_new_object(self.pending, instance, key=key, through_rows=through_rows)

    def save(self, instance: Any) -> Any:
        """Write the changes made to an object.

        A queued object carries them into its insert. One already in the database is saved now,
        since the queue only inserts.
        """
        if not self.holds(instance):
            instance.validated_save()
        return instance

    def assign(self, row: Any) -> Any:
        """Queue a join row, written after the rows it points at."""
        return self.pending.add_through(row)

    def set_later(self, instance: Any, values: Mapping[str, Any]) -> Any:
        """Queue field values, set once everything queued is written."""
        return self.pending.defer_update(instance, values)


# Either kind, for the helpers that write through one.
Writer = Union[ImmediateWriter, BatchedWriter]
