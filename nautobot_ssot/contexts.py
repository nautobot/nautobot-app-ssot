"""Deferred-X context managers — the conceptual companion to `SSoTFlags`.

Where the flags answer *how* the bulk write happens (per-row save vs
bulk_create), these context managers answer *what to do with the
side-effects* — capture them during the bulk window and either replay them
deduplicated (shape A) or run a batched form once (shape B).

Mental model
------------

Every signal handler that fires post-save in Nautobot core falls into one
of two categories:

    Shape A — per-row replay
        Handler does I/O per row (write a log row, enqueue a task, send a
        webhook). Deferral captures the invocations and batches the I/O at
        end of block. Per-row Python work still runs N times. Example:
        `deferred_change_logging_for_bulk_operation` (Nautobot core).

    Shape B — batched-handler invocation
        Handler does cross-row work (walk a graph, cascade a state). Per-row
        replay is wasteful; a single batched call against the whole set is
        dramatically cheaper. Requires the handler to be rewritten in a
        batched form. Example: `deferred_domainlogic_cable` below.

The full menu of "deferred X" contexts that *could* exist:

    Shape A:
        deferred_changelog              ← exists in Nautobot core
        deferred_webhook                ← would need to write
        deferred_jobhook                ← would need to write
        deferred_publish                ← would need to write
        deferred_cacheinvalidate_*      ← could write; handlers already cheap

    Shape B:
        deferred_domainlogic_cable      ← demonstrated below
        deferred_domainlogic_rack       ← stub below
        deferred_domainlogic_rackgroup  ← stub below
        deferred_domainlogic_circuit    ← stub below
        deferred_domainlogic_<...>      ← per domain

Composition
-----------

Contexts compose via `contextlib.ExitStack` or simply nesting:

    with deferred_changelog(), deferred_domainlogic_cable():
        run_streaming_sync(src, dst, flags=SSoTFlags.STREAM_TIER2 | SSoTFlags.BULK_SIGNAL)
    # end-of-block flushes each context in reverse order

Why a context manager and not another flag
------------------------------------------

A flag is a binary "do this" / "don't do this". A context manager has
start / capture / flush semantics — naturally maps to deferred work.
`SSoTFlags` stays focused on the data-path question (per-row vs bulk);
contexts handle side-effect deferral. Different concerns, different shapes.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator

from nautobot_ssot.signals import bulk_post_create, bulk_post_update

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shape B — batched-handler context for Cable
# ---------------------------------------------------------------------------


@contextmanager
def deferred_domainlogic_cable(*, batched: bool = True) -> Iterator[None]:
    """Capture bulk-created/updated Cables; replay the connected-endpoint
    maintenance work *once* per cable at end of block.

    Without this context, `BULK_WRITES` skips Nautobot's
    `dcim.signals.update_connected_endpoints` post_save handler, leaving
    Cable.connection_state and termination ``_cable_peer`` references stale.
    `REFIRE_POST_SAVE` resurrects the per-row handler — works, but if the
    same termination is referenced by multiple cables in the batch, the
    handler walks the cable graph N times for the same vertex.

    With this context (shape B):

        * `batched=True` (default) — bulk_update on the affected
          terminations grouped by termination model class, then
          deduplicated path-computation per cable. One batch per
          termination model, regardless of cable count.

        * `batched=False` — deduplicated shape-A: each unique cable in
          the captured batch has the per-row handler called exactly once.
          Same correctness as `REFIRE_POST_SAVE`, minus the duplicate
          calls when terminations are shared.

    Compose with `BULK_SIGNAL` so the bulk pipeline emits the
    `bulk_post_create` / `bulk_post_update` signals this context listens
    for.

        with deferred_domainlogic_cable():
            run_streaming_sync(src, dst, flags=STREAM_TIER2 | BULK_SIGNAL)
    """
    captured_creates: dict = {}  # {pk: instance}
    captured_updates: dict = {}

    def _capture_create(sender, instances, **kwargs):
        from nautobot.dcim.models import Cable
        if sender is Cable:
            for inst in instances:
                captured_creates[inst.pk] = inst

    def _capture_update(sender, instances, fields=None, **kwargs):
        from nautobot.dcim.models import Cable
        if sender is Cable:
            for inst in instances:
                captured_updates[inst.pk] = inst

    bulk_post_create.connect(_capture_create)
    bulk_post_update.connect(_capture_update)
    try:
        yield
    finally:
        bulk_post_create.disconnect(_capture_create)
        bulk_post_update.disconnect(_capture_update)

        all_cables = {**captured_updates, **captured_creates}
        if not all_cables:
            return
        if batched:
            _flush_cable_terminations_batched(all_cables.values(), is_create=captured_creates)
        else:
            _flush_cable_terminations_replay(all_cables.values(), is_create=captured_creates)


def _flush_cable_terminations_batched(cables, is_create) -> None:
    """Shape-B flush: one bulk_update per termination model class.

    Collects every termination object that needs its `cable` and
    `_cable_peer` cached, groups by model class, and emits one
    `bulk_update` per class. Path computation still runs per-cable but
    only once per cable.
    """
    # Lazy imports — keep this module importable without Nautobot fully ready
    from nautobot.dcim.utils import create_cablepath, rebuild_paths
    from nautobot.dcim.models import PathEndpoint

    # Pass 1: collect terminations needing cache update, grouped by model
    by_term_class: dict = defaultdict(list)
    for cable in cables:
        for term, peer in (
            (cable.termination_a, cable.termination_b),
            (cable.termination_b, cable.termination_a),
        ):
            if term is None:
                continue
            if getattr(term, "cable", None) != cable:
                term.cable = cable
                term._cable_peer = peer
                by_term_class[type(term)].append(term)

    # Pass 2: one bulk_update per termination class
    total_updated = 0
    for term_class, terms in by_term_class.items():
        term_class.objects.bulk_update(terms, ["cable", "_cable_peer"], batch_size=250)
        total_updated += len(terms)
    logger.debug(
        "deferred_domainlogic_cable: bulk-updated %d termination(s) across %d model class(es)",
        total_updated, len(by_term_class),
    )

    # Pass 3: cable paths — still per-cable (graph walk). Deduplicated by
    # virtue of `cables` being a unique set already.
    for cable in cables:
        if cable.pk not in is_create:
            continue  # only on create per the original signal handler
        for term in (cable.termination_a, cable.termination_b):
            if term is None:
                continue
            if isinstance(term, PathEndpoint):
                create_cablepath(term)
            else:
                rebuild_paths(term)


def _flush_cable_terminations_replay(cables, is_create) -> None:
    """Shape-A flush: call the existing per-row handler once per unique cable.

    Same correctness as `REFIRE_POST_SAVE` minus duplicate calls when
    terminations are shared between cables in the batch.
    """
    from nautobot.dcim.signals import update_connected_endpoints

    for cable in cables:
        update_connected_endpoints(
            instance=cable,
            created=cable.pk in is_create,
            raw=False,
        )


# ---------------------------------------------------------------------------
# Stubs for the rest of the deferred-X menu
# ---------------------------------------------------------------------------


@contextmanager
def deferred_domainlogic_rack(*, batched: bool = True) -> Iterator[None]:  # pragma: no cover
    """[Stub] Capture Rack saves, then bulk-update child Devices' location.

    Sketch of the shape-B implementation. Not wired today — included so
    the deferred-X menu in the docs has a concrete target.

    A real implementation would:

    1. Subscribe to `bulk_post_update` for sender=Rack.
    2. Capture the set of (rack_pk, new_location_pk) where location changed.
    3. At end of block, do one bulk_update over Devices grouped by
       affected rack to set their `location_id`. Replaces N invocations
       of `dcim.signals.handle_rack_location_change` with one batched op.
    """
    raise NotImplementedError(
        "deferred_domainlogic_rack is a stub — see module docstring for the design"
    )


@contextmanager
def deferred_domainlogic_rackgroup(*, batched: bool = True) -> Iterator[None]:  # pragma: no cover
    """[Stub] Capture RackGroup saves, then cascade location to child Racks."""
    raise NotImplementedError(
        "deferred_domainlogic_rackgroup is a stub — see module docstring for the design"
    )


@contextmanager
def deferred_domainlogic_circuit(*, batched: bool = True) -> Iterator[None]:  # pragma: no cover
    """[Stub] Capture CircuitTermination saves, then update parent Circuits."""
    raise NotImplementedError(
        "deferred_domainlogic_circuit is a stub — see module docstring for the design"
    )


@contextmanager
def deferred_webhook() -> Iterator[None]:  # pragma: no cover
    """[Stub] Capture webhook dispatches, batch enqueue them.

    Shape-A. Would re-implement Nautobot's webhook dispatch site to read a
    deferral flag, stash work in a queue, and bulk-enqueue Celery tasks at
    end of block. Currently left to the existing `web_request_context` →
    `ObjectChange` → `enqueue_webhooks` chain (which composes naturally
    with `deferred_change_logging_for_bulk_operation`).
    """
    raise NotImplementedError(
        "deferred_webhook is a stub — Nautobot core's existing change_context "
        "cleanup loop already provides this functionality when an OC is written"
    )


@contextmanager
def deferred_jobhook() -> Iterator[None]:  # pragma: no cover
    """[Stub] Same shape as deferred_webhook for job hooks."""
    raise NotImplementedError("deferred_jobhook is a stub")


@contextmanager
def deferred_publish() -> Iterator[None]:  # pragma: no cover
    """[Stub] Capture event publish calls, batch them."""
    raise NotImplementedError("deferred_publish is a stub")
