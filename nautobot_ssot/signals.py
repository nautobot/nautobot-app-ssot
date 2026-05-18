"""SSoT-defined Django signals fired by the bulk-write pipeline.

These are **new** signals — they do NOT replace `pre_save` / `post_save` /
`pre_delete` / `post_delete`. Subscribe to these when:

  * you want to learn about changes a `BULK_WRITES` (Tier 2) sync makes
  * you want one notification per batch, not per row
  * the changelog mechanism (`deferred_change_logging_for_bulk_operation`)
    is not what you need (you don't want `ObjectChange` rows — you want
    a hook for cache invalidation, search-index updates, batched webhook
    dispatch, etc.)

Why a new signal instead of resurrecting `post_save`?
-----------------------------------------------------
`bulk_create()` skipping `post_save` is intentional and well-known. Apps
that subscribe to `post_save` typically expect a *single* instance, not a
list — invoking those handlers N times after a bulk_create would defeat
the point. A separate signal lets handlers opt in with the batched shape.

Pattern
-------
The signal is fired by `BulkOperationsMixin.flush_creates` etc. when
`SSoTFlags.BULK_SIGNAL` is set. Handlers subscribe with the batched form:

    from nautobot_ssot.signals import bulk_post_create

    @receiver(bulk_post_create, sender=IPAddress)
    def invalidate_caches(sender, instances, **kwargs):
        cache.delete_many([f"ip:{i.pk}" for i in instances])

Flag-gated so it costs nothing when off.

Compare to "defer_signal"
-------------------------
A separate but related pattern is *deferred per-row signals* — capture
each per-row signal during the bulk window, replay them in batch at end.
That requires handler-side awareness of deferral (which is what
`deferred_change_logging_for_bulk_operation` does for the changelog
signal specifically — the handler reads `change_context.defer_object_changes`
and changes its behavior). For other signal domains, the same pattern can
be added per-domain — there is no clean *generic* defer mechanism because
handlers must know how to be deferred.

In short:
  * `bulk_post_*`     — dispatch ONCE per batch, handler sees a list
  * deferred per-row  — dispatch N times, handler-side opt-in to batching
"""

from django.dispatch import Signal

# Fired AFTER `model_class.objects.bulk_create(queue, ...)` returns.
#
# kwargs:
#   sender    — ORM model class
#   instances — list of created ORM objects (PKs assigned)
#   context   — optional str describing the SSoT sync that produced them
bulk_post_create = Signal()

# Fired AFTER `model_class.objects.bulk_update(queue, fields, ...)` returns.
#
# kwargs:
#   sender    — ORM model class
#   instances — list of updated ORM objects
#   fields    — set of field names that were updated
#   context   — optional str describing the SSoT sync
bulk_post_update = Signal()

# Fired AFTER a bulk delete operation completes.
#
# kwargs:
#   sender    — ORM model class
#   pks       — list of PKs that were deleted (instances are gone)
#   context   — optional str describing the SSoT sync
bulk_post_delete = Signal()
