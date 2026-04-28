"""Phased validator registry — Hook 3 of the SSoT validation menu.

Generalizes the ad-hoc Hook 1/Hook 2 plumbing into a single registry where
each validator declares:

    * which **phase** it runs in (A / B / C)
    * which **category** of invariant it enforces (1..8 from the menu doc)
    * what **scope** of data it touches
    * what **severity** failures have (warn / error / strict)

The pipeline orchestrator queries the registry at three well-defined points:

    Phase A — after both adapters dumped, before any flush
              context: source_records, dest_records, diff_results
              covers: same-model uniqueness, topology, cross-model conditional,
                      aggregate, mutual exclusion, state-machine

    Phase B — between FK-ordered flush stages
              context: DB + remaining queues + adapter maps
              covers: FK existence pre-check, FK containment / fit

    Phase C — after all flushes
              context: final DB state
              covers: post-hoc consistency audits, tag rollups

A `Validator` registers itself with one phase. Phase B validators additionally
declare `fires_before_flush_of = OrmModelClass` so the BulkSyncer knows when
to invoke them in the FK-ordered flush sequence.

This file deliberately ships with NO pre-registered validators. Concrete
validators live in sibling modules (e.g. `validators_ipam.py`) and are wired
onto adapters via a `validator_registry` class attribute.

Reference: docs/dev/performance_validation_menu.md §§ 4–5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Iterable, List, Optional

from django.core.exceptions import ValidationError as DjangoValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums + value types
# ---------------------------------------------------------------------------


class Phase(str, Enum):
    """Where in the pipeline a validator runs."""

    A = "A"  # after dump, before any flush
    B = "B"  # between FK-ordered flushes
    C = "C"  # after all flushes


class Severity(str, Enum):
    """How loud a failed validation should be."""

    WARN = "warn"      # log and keep going
    ERROR = "error"    # log, collect, return non-zero issue count
    STRICT = "strict"  # raise immediately, abort the run


@dataclass
class Issue:
    """One validator finding. Multiple Issues per validator run are allowed."""

    validator: str
    model_type: str
    key: str
    detail: str
    severity: Severity = Severity.ERROR
    category: int = 0


# ---------------------------------------------------------------------------
# Context object — what a validator sees
# ---------------------------------------------------------------------------


@dataclass
class ValidatorContext:
    """The runtime data a Validator inspects.

    Different phases populate different fields. Validators should access only
    what they need — accessing an unpopulated field returns None / empty.

    Phase A: store, src_adapter, dst_adapter populated. Queues empty.
    Phase B: store, dst_adapter, pending_queues populated. flushed_models set.
    Phase C: store, dst_adapter populated. queues drained.
    """

    store: Any = None  # nautobot_ssot.utils.sqlite_store.DiffSyncStore
    src_adapter: Any = None
    dst_adapter: Any = None
    pending_queues: Optional[dict] = None  # {OrmClass: [obj, ...]}, Phase B only
    flushed_models: set = field(default_factory=set)  # ORM classes already flushed

    # ---- Convenience accessors that map onto the four "context verbs" -----

    def row(self, table: str, model_type: str, unique_key: str):
        """One row from `source_records` / `dest_records` / `diff_results`."""
        if self.store is None:
            return None
        if table == "source_records":
            cur = self.store.conn.execute(
                "SELECT identifiers, attrs FROM source_records WHERE model_type=? AND unique_key=?",
                (model_type, unique_key),
            )
            return cur.fetchone()
        if table == "dest_records":
            return self.store.fetch_dest(model_type, unique_key)
        return None

    def scope(self, table: str, model_type: str) -> Iterable[tuple]:
        """Iter rows of one model_type from one of the SQLite tables."""
        if self.store is None:
            return iter(())
        if table not in ("source_records", "dest_records", "diff_results"):
            raise ValueError(f"unknown table {table!r}")
        cur = self.store.conn.execute(
            f"SELECT * FROM {table} WHERE model_type = ?", (model_type,)
        )
        return iter(cur)

    def queue(self, model_class) -> Iterable:
        """Iter over queued ORM objects for `model_class` (Phase B only)."""
        if not self.pending_queues:
            return iter(())
        return iter(self.pending_queues.get(model_class, []))

    def aggregate(self, sql: str, params: tuple = ()) -> List[tuple]:
        """Run an arbitrary SQL aggregate against the SQLite store."""
        if self.store is None:
            return []
        return list(self.store.conn.execute(sql, params))


# ---------------------------------------------------------------------------
# Validator base class
# ---------------------------------------------------------------------------


class Validator:
    """Subclass and override `run()`.

    Class-level metadata describes WHEN and WHERE the validator runs; the
    `run()` method does the actual work and returns a list of Issues.

    Phase B validators MUST set `fires_before_flush_of = SomeOrmClass` so the
    BulkSyncer can schedule them at the right point in flush ordering.
    """

    name: ClassVar[str] = "unnamed"
    phase: ClassVar[Phase] = Phase.A
    category: ClassVar[int] = 0
    severity: ClassVar[Severity] = Severity.ERROR
    fires_before_flush_of: ClassVar[Optional[type]] = None  # Phase B only

    def run(self, ctx: ValidatorContext) -> List[Issue]:
        raise NotImplementedError(f"{type(self).__name__}.run() not implemented")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ValidatorRegistry:
    """Holds a list of Validator instances; dispatches them by phase.

    A registry is typically attached to a destination adapter as a class
    attribute, e.g.:

        class BulkNautobotAdapter(...):
            validator_registry = ValidatorRegistry([
                IPInPrefixValidator(),
                ...
            ])

    Empty registries are valid — they produce zero overhead at every phase.
    """

    def __init__(self, validators: Optional[Iterable[Validator]] = None):
        self.validators: List[Validator] = list(validators or [])

    def add(self, validator: Validator) -> None:
        self.validators.append(validator)

    def for_phase(self, phase: Phase) -> List[Validator]:
        return [v for v in self.validators if v.phase == phase]

    def for_phase_b_before(self, model_class: type) -> List[Validator]:
        return [
            v for v in self.validators
            if v.phase == Phase.B and v.fires_before_flush_of is model_class
        ]

    def run_phase(self, phase: Phase, ctx: ValidatorContext, *, strict: bool = False) -> List[Issue]:
        """Run all validators registered for `phase`. Returns collected issues."""
        return self._dispatch(self.for_phase(phase), ctx, strict=strict)

    def run_before_flush(self, model_class: type, ctx: ValidatorContext, *, strict: bool = False) -> List[Issue]:
        """Run Phase B validators tied to `model_class` (right before its flush)."""
        return self._dispatch(self.for_phase_b_before(model_class), ctx, strict=strict)

    # ------------------------------------------------------------------

    def _dispatch(self, validators: List[Validator], ctx: ValidatorContext, *, strict: bool) -> List[Issue]:
        all_issues: List[Issue] = []
        for v in validators:
            try:
                issues = list(v.run(ctx) or [])
            except Exception as exc:  # noqa: BLE001 — validator misbehavior shouldn't kill the sync
                logger.exception("Validator %s raised during run: %s", v.name, exc)
                if strict:
                    raise
                all_issues.append(
                    Issue(
                        validator=v.name,
                        model_type="",
                        key="",
                        detail=f"validator raised: {exc}",
                        severity=Severity.ERROR,
                        category=v.category,
                    )
                )
                continue

            for issue in issues:
                all_issues.append(issue)
                if strict or v.severity == Severity.STRICT or issue.severity == Severity.STRICT:
                    raise DjangoValidationError(
                        f"[{v.name}] {issue.model_type} {issue.key}: {issue.detail}"
                    )
                logger.warning(
                    "[%s] %s %s: %s",
                    v.name, issue.model_type, issue.key, issue.detail,
                )
        return all_issues


# Sentinel used by the BulkSyncer when an adapter exposes no registry.
EMPTY_REGISTRY = ValidatorRegistry()
