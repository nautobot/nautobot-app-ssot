"""Bulk operation mixin for Nautobot DiffSync adapters.

Replaces per-object validated_save() with bulk_create() / bulk_update() calls,
reducing N DB round-trips to ceil(N / batch_size) round-trips.

Design notes
------------
UUID PKs are generated at OrmModel() instantiation time (before any DB write).
This means you can:

    _prefix = OrmPrefix(name=..., namespace_id=adapter.namespace_map["Global"])
    adapter.prefix_map[key] = _prefix.pk   # ← UUID already set, no save needed
    adapter.queue_for_create(OrmPrefix, _prefix)

Later objects in the same batch can reference that PK immediately, so the full
FK chain (Namespace → Prefix → IPAddress) resolves correctly as long as
flush_all() is called in dependency order.

Validation
----------
Validation is skipped by default (validate=False). Nautobot's clean()
implementations (e.g. IPAddress.clean() → _get_closest_parent()) query the
DB for FK parents that may be queued-but-not-yet-flushed, causing
DoesNotExist errors. FK validity is guaranteed by flush_all()'s dependency
ordering (parents before children) and enforced by DB constraints at INSERT.
Pass validate=True only for models whose clean() has no DB round-trips.

Change logging
--------------
bulk_create / bulk_update do not fire post_save signals, so ObjectChange records
are NOT created automatically. This is a known trade-off. Change log support
can be layered on top using Nautobot's deferred_change_logging_for_bulk_operation
context manager in a future phase.
"""

from collections import defaultdict
from typing import ClassVar


class BulkOperationsMixin:
    """Mixin for Nautobot DiffSync adapters that enables bulk create/update.

    Usage
    -----
    1.  Mix in before Adapter in the MRO::

            class MyAdapter(BulkOperationsMixin, NautobotAdapter):
                _bulk_create_order = [OrmNamespace, OrmPrefix, OrmIPAddress]

    2.  In each model's create() / update():

            adapter.queue_for_create(OrmPrefix, orm_obj)
            # or
            adapter.queue_for_update(OrmPrefix, orm_obj, ["description"])

        Update adapter maps immediately using the pre-set UUID::

            adapter.prefix_map[key] = orm_obj.pk   # UUID is set at OrmPrefix()

    3.  Override sync_complete() to flush::

            def sync_complete(self, source, *args, **kwargs):
                self.flush_all()
                super().sync_complete(source, *args, **kwargs)

    Class variables
    ---------------
    _bulk_create_order
        List of ORM model classes in FK dependency order (parents first).
        flush_all() flushes creates in this order, then any remaining queues.
    _bulk_batch_size
        Default batch size for bulk_create / bulk_update statements.
    """

    _bulk_create_order: ClassVar[list] = []
    _bulk_batch_size: ClassVar[int] = 250

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # {OrmModelClass: [orm_instance, ...]}
        self._create_queue: dict = defaultdict(list)
        # {OrmModelClass: {"objects": [...], "fields": set()}}
        self._update_queue: dict = defaultdict(lambda: {"objects": [], "fields": set()})

    # ------------------------------------------------------------------
    # Queuing
    # ------------------------------------------------------------------

    def queue_for_create(self, model_class, orm_obj, validate: bool = False) -> None:
        """Queue an ORM object for bulk creation.

        Args:
            model_class: The Django ORM model class (e.g. OrmPrefix).
            orm_obj: An unsaved ORM model instance. Its pk is already a UUID.
            validate: If True, runs clean() before queuing. Defaults to False.
                      Nautobot's clean() implementations (e.g. IPAddress.clean() calls
                      _get_closest_parent()) query the DB for FK parents that may be
                      queued-but-not-yet-flushed, causing DoesNotExist errors mid-queue.
                      FK validity is guaranteed by flush ordering (parents first) and
                      enforced at INSERT time by DB constraints.
        """
        if validate:
            orm_obj.clean()
        self._create_queue[model_class].append(orm_obj)

    def queue_for_update(
        self, model_class, orm_obj, update_fields: list[str], validate: bool = False
    ) -> None:
        """Queue an ORM object for bulk update.

        Args:
            model_class: The Django ORM model class.
            orm_obj: A saved ORM model instance with modified field values.
            update_fields: Field names to include in the bulk_update statement.
            validate: If True, runs clean() before queuing. Defaults to False.
                      See queue_for_create() for the same caveat about Nautobot's
                      clean() implementations making DB queries mid-queue.
        """
        if validate:
            orm_obj.clean()
        entry = self._update_queue[model_class]
        entry["objects"].append(orm_obj)
        entry["fields"].update(update_fields)

    # ------------------------------------------------------------------
    # Flushing
    # ------------------------------------------------------------------

    def flush_creates(self, model_class, batch_size: int | None = None) -> list:
        """Execute bulk_create for one model class and return the created objects.

        Args:
            model_class: The ORM model class to flush.
            batch_size: Objects per INSERT. Defaults to _bulk_batch_size.

        Returns:
            List of created ORM instances (PKs confirmed by DB on PostgreSQL).
        """
        queue = self._create_queue.pop(model_class, [])
        if not queue:
            return []

        size = batch_size or self._bulk_batch_size
        created = model_class.objects.bulk_create(queue, batch_size=size)
        if hasattr(self, "job"):
            self.job.logger.debug(f"Bulk created {len(created)} {model_class.__name__}.")
        return created

    def flush_updates(self, model_class, batch_size: int | None = None) -> None:
        """Execute bulk_update for one model class."""
        entry = self._update_queue.pop(model_class, None)
        if not entry or not entry["objects"]:
            return

        objs = entry["objects"]
        fields = entry["fields"]

        size = batch_size or self._bulk_batch_size
        model_class.objects.bulk_update(objs, list(fields), batch_size=size)
        if hasattr(self, "job"):
            self.job.logger.debug(f"Bulk updated {len(objs)} {model_class.__name__}.")

    def flush_all(self, create_order: list | None = None, batch_size: int | None = None) -> None:
        """Flush all queued creates and updates.

        Creates are flushed in FK dependency order (parents before children)
        so that FK constraints are satisfied at INSERT time.

        Args:
            create_order: Explicit FK-ordered list of model classes for creates.
                          Defaults to self._bulk_create_order.
            batch_size: Batch size for all operations. Defaults to _bulk_batch_size.
        """
        order = create_order if create_order is not None else self._bulk_create_order

        # Flush creates in explicit dependency order
        for model_class in order:
            self.flush_creates(model_class, batch_size=batch_size)

        # Flush any remaining creates not covered by the explicit order
        for model_class in list(self._create_queue.keys()):
            self.flush_creates(model_class, batch_size=batch_size)

        # Flush all updates
        for model_class in list(self._update_queue.keys()):
            self.flush_updates(model_class, batch_size=batch_size)

    def pending_create_count(self) -> int:
        """Return total number of objects queued for creation (not yet written)."""
        return sum(len(v) for v in self._create_queue.values())

    def pending_update_count(self) -> int:
        """Return total number of objects queued for update (not yet written)."""
        return sum(len(v["objects"]) for v in self._update_queue.values())
