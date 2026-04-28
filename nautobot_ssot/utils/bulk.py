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

    def flush_creates(
        self,
        model_class,
        batch_size: int | None = None,
        *,
        bulk_clean: bool = False,
        bulk_signal: bool = False,
        refire_post_save: bool = False,
        signal_context: str | None = None,
    ) -> list:
        """Execute bulk_create for one model class and return the created objects.

        Args:
            model_class: The ORM model class to flush.
            batch_size: Objects per INSERT. Defaults to _bulk_batch_size.
            bulk_clean: When True, call ``model_class.bulk_clean(queue)`` before
                INSERT. Hypothetical Nautobot core feature
                (`Model.bulk_clean(instances)`) that batches Django's per-row
                ``clean()`` queries into a single query when the model overrides
                it. If the method doesn't exist, this flag is a silent no-op —
                the plumbing is here so the day Nautobot ships the feature, our
                bulk path picks it up automatically.
            bulk_signal: When True, fire ``bulk_post_create.send(...)`` after
                bulk_create returns. Subscribed handlers see the full batch as
                ``instances=[...]``. See `nautobot_ssot.signals` for the contract.
            refire_post_save: When True, re-fire Django's ``post_save`` signal
                per instance after the bulk_create completes. This restores
                Nautobot core handlers that bulk_create normally skips (Cable
                propagation, Rack location cascading, custom-field cache
                invalidation, etc.). Per-row dispatch — pays back some of the
                speed bulk_create bought, but keeps existing handler semantics.
                See `docs/dev/performance_validation_menu.md` §10.
            signal_context: Optional string passed to the bulk signal as
                the ``context=`` kwarg (e.g. the SSoT job's run identifier).

        Returns:
            List of created ORM instances (PKs confirmed by DB on PostgreSQL).
        """
        queue = self._create_queue.pop(model_class, [])
        if not queue:
            return []

        if bulk_clean:
            _maybe_invoke_bulk_clean(model_class, queue)

        size = batch_size or self._bulk_batch_size
        created = model_class.objects.bulk_create(queue, batch_size=size)
        if hasattr(self, "job"):
            self.job.logger.debug(f"Bulk created {len(created)} {model_class.__name__}.")

        if refire_post_save and created:
            _refire_post_save(model_class, created, created_kw=True)

        if bulk_signal and created:
            from nautobot_ssot.signals import bulk_post_create
            bulk_post_create.send(sender=model_class, instances=created, context=signal_context)

        return created

    def flush_updates(
        self,
        model_class,
        batch_size: int | None = None,
        *,
        bulk_clean: bool = False,
        bulk_signal: bool = False,
        refire_post_save: bool = False,
        signal_context: str | None = None,
    ) -> None:
        """Execute bulk_update for one model class.

        Args mirror `flush_creates` — see that method for `bulk_clean`,
        `bulk_signal`, and `refire_post_save` semantics.
        """
        entry = self._update_queue.pop(model_class, None)
        if not entry or not entry["objects"]:
            return

        objs = entry["objects"]
        fields = entry["fields"]

        if bulk_clean:
            _maybe_invoke_bulk_clean(model_class, objs)

        size = batch_size or self._bulk_batch_size
        model_class.objects.bulk_update(objs, list(fields), batch_size=size)
        if hasattr(self, "job"):
            self.job.logger.debug(f"Bulk updated {len(objs)} {model_class.__name__}.")

        if refire_post_save and objs:
            _refire_post_save(model_class, objs, created_kw=False, update_fields=set(fields))

        if bulk_signal:
            from nautobot_ssot.signals import bulk_post_update
            bulk_post_update.send(
                sender=model_class, instances=objs, fields=fields, context=signal_context
            )

    def flush_all(
        self,
        create_order: list | None = None,
        batch_size: int | None = None,
        *,
        bulk_clean: bool = False,
        bulk_signal: bool = False,
        refire_post_save: bool = False,
        signal_context: str | None = None,
    ) -> None:
        """Flush all queued creates and updates.

        Creates are flushed in FK dependency order (parents before children)
        so that FK constraints are satisfied at INSERT time.

        Args:
            create_order: Explicit FK-ordered list of model classes for creates.
                          Defaults to self._bulk_create_order.
            batch_size: Batch size for all operations. Defaults to _bulk_batch_size.
            bulk_clean / bulk_signal / signal_context: forwarded to per-model
                flush_creates / flush_updates calls. See those methods.
        """
        order = create_order if create_order is not None else self._bulk_create_order
        kwargs = {
            "batch_size": batch_size,
            "bulk_clean": bulk_clean,
            "bulk_signal": bulk_signal,
            "refire_post_save": refire_post_save,
            "signal_context": signal_context,
        }

        # Flush creates in explicit dependency order
        for model_class in order:
            self.flush_creates(model_class, **kwargs)

        # Flush any remaining creates not covered by the explicit order
        for model_class in list(self._create_queue.keys()):
            self.flush_creates(model_class, **kwargs)

        # Flush all updates
        for model_class in list(self._update_queue.keys()):
            self.flush_updates(model_class, **kwargs)

    def pending_create_count(self) -> int:
        """Return total number of objects queued for creation (not yet written)."""
        return sum(len(v) for v in self._create_queue.values())

    def pending_update_count(self) -> int:
        """Return total number of objects queued for update (not yet written)."""
        return sum(len(v["objects"]) for v in self._update_queue.values())


# ---------------------------------------------------------------------------
# bulk_clean shim
# ---------------------------------------------------------------------------


def _refire_post_save(model_class, instances, *, created_kw: bool, update_fields=None) -> None:
    """Re-fire Django's `post_save` signal once per instance.

    `bulk_create()` / `bulk_update()` skip Django signals by design — that's
    the source of their speed. This helper restores the signal dispatch *after*
    the bulk operation has completed, so handlers subscribed to `post_save`
    (Cable propagation, Rack location cascading, custom-field cache
    invalidation, etc.) get to run.

    The trade-off: per-row dispatch is N invocations of the handler, which
    pays back some of the speed bulk_create bought. But the alternative is
    "silent loss of cascading state" (e.g., Cable.connection_state never
    gets updated), which is worse than slow.

    Args:
        model_class: ORM model class for the bulk operation.
        instances:   list of the model instances that were created/updated.
        created_kw:  value passed as `created=` to the post_save signal.
                     True for bulk_create, False for bulk_update.
        update_fields: optional set of fields, passed as `update_fields=` to
                       the post_save signal — relevant only for bulk_update,
                       where some receivers branch on which fields changed.
    """
    from django.db import router
    from django.db.models.signals import post_save

    using = router.db_for_write(model_class) or "default"
    for instance in instances:
        post_save.send(
            sender=model_class,
            instance=instance,
            created=created_kw,
            raw=False,
            using=using,
            update_fields=update_fields,
        )


def _maybe_invoke_bulk_clean(model_class, instances) -> None:
    """Call ``model_class.bulk_clean(instances)`` if the model defines it.

    `Model.bulk_clean(instances)` is a hypothetical Nautobot core API that
    runs validation across a batch of instances, ideally amortizing per-row
    DB queries (e.g. `IPAddress._get_closest_parent`) into a single query.

    Contract (when Nautobot core ships it):

        @classmethod
        def bulk_clean(cls, instances) -> None:
            '''Validate a batch. Raises ValidationError on failure.'''
            ...

    Until that lands, this function is a no-op for models that don't define
    the method — the SSoT bulk path picks up the optimization automatically
    on the day Nautobot adds it. No SSoT-side change required.
    """
    bulk_clean_fn = getattr(model_class, "bulk_clean", None)
    if not callable(bulk_clean_fn):
        return  # Nautobot core hasn't shipped Model.bulk_clean yet — silently skip
    bulk_clean_fn(instances)
