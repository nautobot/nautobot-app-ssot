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
from .validator_registry import EMPTY_REGISTRY, Phase, ValidatorContext

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
        validate_relations=False,
        bulk_clean: bool = False,
        bulk_signal: bool = False,
        refire_post_save: bool = False,
        signal_context: str | None = None,
    ):
        if tier not in ("tier1", "tier2"):
            raise ValueError(f"BulkSyncer: tier must be 'tier1' or 'tier2', got {tier!r}")
        if validate_relations not in (False, True, "strict"):
            raise ValueError(
                f"validate_relations must be False / True / 'strict', got {validate_relations!r}"
            )
        self.dst_adapter = dst_adapter
        self.store = store
        self.tier = tier
        self.user = user
        self.validate_relations = validate_relations
        self.bulk_clean = bulk_clean
        self.bulk_signal = bulk_signal
        self.refire_post_save = refire_post_save
        self.signal_context = signal_context
        self.stats = {"create": 0, "update": 0, "delete": 0, "errors": 0,
                      "phase_a_issues": 0, "phase_b_issues": 0, "phase_c_issues": 0}

    # Resolved lazily so non-streaming code paths don't pull the registry.
    @property
    def _registry(self):
        return getattr(self.dst_adapter, "validator_registry", None) or EMPTY_REGISTRY

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def sync(self) -> dict:
        """Apply all queued diff_results. Returns the stats dict."""
        # Phase A — pre-flush validators (uniqueness, topology, cross-model
        # invariants). Run first because they can decide to abort the whole
        # sync if `validate_relations="strict"` and an issue is found.
        self._run_phase("A")

        if self.tier == "tier1":
            user = self.user or _benchmark_user()
            with _deferred_changelog(user):
                self._apply_actions()
            return dict(self.stats)

        # Tier 2: bulk adapter; replay creates/updates/deletes, then flush.
        self._apply_actions()
        self._tier2_flush_with_phase_b()
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
        # Phase C — final consistency / audit hooks.
        self._run_phase("C")
        return dict(self.stats)

    def _tier2_flush_with_phase_b(self) -> None:
        """Replicate `flush_all()` but interleave Phase B validators between FK stages.

        For each ORM class in `_bulk_create_order`, we run any Phase B
        validators registered with `fires_before_flush_of=<that_class>`,
        then issue the bulk_create for it.

        BULK_CLEAN / BULK_SIGNAL flags are forwarded to flush_creates /
        flush_updates so the per-batch cleanup and post-flush signal
        dispatch happen at each FK stage, not just at the very end.
        """
        adapter = self.dst_adapter
        order = list(getattr(adapter, "_bulk_create_order", []))
        flush_kwargs = {
            "bulk_clean": self.bulk_clean,
            "bulk_signal": self.bulk_signal,
            "refire_post_save": self.refire_post_save,
            "signal_context": self.signal_context,
        }

        for model_class in order:
            self._run_phase_b_before(model_class)
            adapter.flush_creates(model_class, **flush_kwargs)

        # Flush any creates not in the explicit order
        for model_class in list(adapter._create_queue.keys()):
            adapter.flush_creates(model_class, **flush_kwargs)

        # Flush all updates
        for model_class in list(adapter._update_queue.keys()):
            adapter.flush_updates(model_class, **flush_kwargs)

    def _build_context(self) -> ValidatorContext:
        """Construct a ValidatorContext snapshot of the current pipeline state."""
        adapter = self.dst_adapter
        return ValidatorContext(
            store=self.store,
            dst_adapter=adapter,
            pending_queues=getattr(adapter, "_create_queue", None),
        )

    def _run_phase(self, phase: str) -> None:
        """Run all validators registered for `phase` and tally issues into stats."""
        ctx = self._build_context()
        strict = self.validate_relations == "strict"
        if not self.validate_relations:
            return
        issues = self._registry.run_phase(Phase(phase), ctx, strict=strict)
        if issues:
            key = f"phase_{phase.lower()}_issues"
            self.stats[key] = self.stats.get(key, 0) + len(issues)
            logger.info("Phase %s: %d issue(s) collected", phase, len(issues))

    def _run_phase_b_before(self, model_class) -> None:
        """Run Phase B validators tied to `model_class` immediately before its flush."""
        if not self.validate_relations:
            return
        ctx = self._build_context()
        strict = self.validate_relations == "strict"
        issues = self._registry.run_before_flush(model_class, ctx, strict=strict)
        if issues:
            self.stats["phase_b_issues"] = self.stats.get("phase_b_issues", 0) + len(issues)
            logger.info(
                "Phase B before flushing %s: %d issue(s) collected",
                model_class.__name__, len(issues),
            )

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
