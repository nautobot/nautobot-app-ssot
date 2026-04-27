"""Replay diff_results rows produced by `streaming_differ` against a Nautobot adapter.

Generic across integrations — each integration's existing DiffSync model
classes (`adapter.namespace.create()`, `adapter.namespace.update()` etc.)
already know how to convert (ids, attrs) pairs into ORM operations. The
BulkSyncer just feeds rows back into them in the right order.

Two tiers
---------
Tier 1 (`tier="tier1"`)
    - applies via the existing `validated_save()` path on each model
    - wraps the entire sync in `deferred_change_logging_for_bulk_operation`
    - keeps clean(), signals, and changelog
    - measured uplift in our benchmark: it depends on the workload — for
      Infoblox it's currently *slower* than per-object validated_save() at
      sub-10k rows because the deferred-changelog dict bookkeeping costs
      more than per-OC writes. Worth keeping for correctness comparisons.

Tier 2 (`tier="tier2"`)
    - relies on a bulk adapter (e.g. `BulkNautobotAdapter` for Infoblox)
      whose `create/update/delete` methods queue ORM objects, not save them
    - calls `adapter.flush_all()` at the end to issue bulk_create/bulk_update
    - skips clean(), signals, and changelog (intentional trade-off)
    - measured: ~9× total speedup vs Tier 1 baseline on medium scale.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Optional

from django.contrib.auth import get_user_model

from .sqlite_store import DiffSyncStore, decode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier 1 helper — wrap per-object writes in deferred change logging
# ---------------------------------------------------------------------------


@contextmanager
def _deferred_changelog(user):
    """Wrap a block in web_request_context + deferred_change_logging_for_bulk_operation.

    Both context managers are imported lazily so this module is importable
    outside of a fully-set-up Django process (helps with tests + linting).
    """
    from nautobot.extras.context_managers import (
        deferred_change_logging_for_bulk_operation,
        web_request_context,
    )

    with web_request_context(user, context_detail="ssot-streaming"):
        with deferred_change_logging_for_bulk_operation():
            yield


def _benchmark_user():
    """Return (or create) a generic user for the deferred change logging context."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="ssot-streaming",
        defaults={"is_superuser": True, "is_active": True},
    )
    return user


# ---------------------------------------------------------------------------
# BulkSyncer
# ---------------------------------------------------------------------------


class BulkSyncer:
    """Replays diff_results rows against a Nautobot DiffSync adapter."""

    def __init__(
        self,
        dst_adapter,
        store: DiffSyncStore,
        tier: str = "tier1",
        user=None,
        *,
        bulk_clean: bool = False,
        bulk_signal: bool = False,
        refire_post_save: bool = False,
        signal_context: str | None = None,
    ):
        if tier not in ("tier1", "tier2"):
            raise ValueError(f"BulkSyncer: tier must be 'tier1' or 'tier2', got {tier!r}")
        self.dst_adapter = dst_adapter
        self.store = store
        self.tier = tier
        self.user = user
        self.bulk_clean = bulk_clean
        self.bulk_signal = bulk_signal
        self.refire_post_save = refire_post_save
        self.signal_context = signal_context
        self.stats = {"create": 0, "update": 0, "delete": 0, "errors": 0}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def sync(self) -> dict:
        """Apply all queued diff_results. Returns the stats dict."""
        if self.tier == "tier1":
            user = self.user or _benchmark_user()
            with _deferred_changelog(user):
                self._apply_actions()
            return dict(self.stats)

        # Tier 2: bulk adapter; replay creates/updates/deletes, then flush.
        self._apply_actions()
        self.dst_adapter.flush_all(
            bulk_clean=self.bulk_clean,
            bulk_signal=self.bulk_signal,
            refire_post_save=self.refire_post_save,
            signal_context=self.signal_context,
        )
        # Some adapters need extra bulk-write hooks after flush_all(), e.g.
        # `BulkNautobotAdapter._flush_ip_tags()` bulk-inserts tag rows for
        # all IPs created in this run.
        post_flush = getattr(self.dst_adapter, "bulk_sync_complete", None)
        if callable(post_flush):
            post_flush()
        else:
            for hook in ("_flush_ip_tags",):
                fn = getattr(self.dst_adapter, hook, None)
                if callable(fn):
                    fn()
        return dict(self.stats)

    # ------------------------------------------------------------------
    # Action replay
    # ------------------------------------------------------------------

    def _apply_actions(self) -> None:
        """Replay create / update / delete in a deterministic order.

        Order matters because of FK constraints:
            CREATE: ascending  type_order, ascending  tree_depth (parents first)
            UPDATE: any order
            DELETE: descending type_order, descending tree_depth (children first)
        """
        for row in self.store.fetch_diff_results("create"):
            self._apply_create(row)
        for row in self.store.fetch_diff_results("update"):
            self._apply_update(row)
        for row in self.store.fetch_diff_results("delete"):
            self._apply_delete(row)

    def _model_class(self, model_type: str) -> Optional[type]:
        """Resolve the DiffSync model class on the destination adapter."""
        cls = getattr(type(self.dst_adapter), model_type, None)
        if cls is None:
            logger.debug("BulkSyncer: no model class for %r on %s", model_type, type(self.dst_adapter).__name__)
        return cls

    def _apply_create(self, diff_row: tuple) -> None:
        (_id, model_type, unique_key, _action, ids_json,
         new_attrs_json, _old_attrs_json, _depth, _order) = diff_row
        cls = self._model_class(model_type)
        if cls is None:
            self.stats["errors"] += 1
            return
        ids = decode(ids_json)
        attrs = decode(new_attrs_json)
        try:
            cls.create(adapter=self.dst_adapter, ids=ids, attrs=attrs)
            self.stats["create"] += 1
        except Exception as exc:  # pragma: no cover - log and keep replaying
            logger.exception(
                "BulkSyncer: create failed for %s/%s: %s", model_type, unique_key, exc
            )
            self.stats["errors"] += 1

    def _apply_update(self, diff_row: tuple) -> None:
        (_id, model_type, unique_key, _action, ids_json,
         new_attrs_json, _old_attrs_json, _depth, _order) = diff_row
        cls = self._model_class(model_type)
        if cls is None:
            self.stats["errors"] += 1
            return
        ids = decode(ids_json)
        attrs = decode(new_attrs_json)
        try:
            instance = cls(adapter=self.dst_adapter, **ids)
            instance.update(attrs=attrs)
            self.stats["update"] += 1
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "BulkSyncer: update failed for %s/%s: %s", model_type, unique_key, exc
            )
            self.stats["errors"] += 1

    def _apply_delete(self, diff_row: tuple) -> None:
        (_id, model_type, unique_key, _action, ids_json,
         _new_attrs_json, _old_attrs_json, _depth, _order) = diff_row
        cls = self._model_class(model_type)
        if cls is None:
            self.stats["errors"] += 1
            return
        ids = decode(ids_json)
        try:
            instance = cls(adapter=self.dst_adapter, **ids)
            instance.delete()
            self.stats["delete"] += 1
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "BulkSyncer: delete failed for %s/%s: %s", model_type, unique_key, exc
            )
            self.stats["errors"] += 1
