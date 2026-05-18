#!/usr/bin/env python
"""Standalone Infoblox SSoT performance benchmark.

Modes:
  (default)        — times InfobloxAdapter.load() only (no DB writes)
  --full           — **PRODUCTION baseline**: validated_save() inside web_request_context (full_clean + save + per-row OC)
  --full-no-cl     — validated_save() outside any change context — no OC rows written (reference)
  --save           — full pipeline, per-object .save() — NO active change_context, no changelog
  --save-cl        — per-object .save() inside web_request_context (signals fire, OC INSERTs per-save)
  --save-defer     — per-object .save() inside web_request_context + deferred_change_logging
  --bulk           — full pipeline, bulk_create / bulk_update (batch=250, no clean/signals/cl)
  --bulk-1000      — bulk pipeline with batch_size=1000
  --bulk-audit     — legacy bulk pipeline + REFIRE_POST_SAVE + deferred_change_logging
                     (full audit chain restored — NO streaming required)
  --stream-tier1   — SQLite-streaming pipeline, replays via validated_save() inside deferred CL
  --stream-tier1-5 — streaming + Hook 1 (strict source) + Hook 2 (clean_fields at dump) + Tier 2 writes
  --stream-tier1-7 — stream-tier1-5 + Hook 3 (Phase B IP-in-prefix validator) + Tier 2 writes
  --stream-tier2   — SQLite-streaming pipeline, replays via BulkNautobotAdapter (bulk_create)
  --stream-tier2-audit — stream-tier2 + REFIRE_POST_SAVE wrapped in deferred_change_logging
                          (fast bulk + full audit chain — webhooks/jobhooks/events fire)
  --matrix         — runs all of the above across tiny / small / medium and prints a summary table

Usage (inside the container):
    python scripts/benchmark_infoblox.py                # source load only, all scales
    python scripts/benchmark_infoblox.py small          # source load, one scale
    python scripts/benchmark_infoblox.py --full tiny    # baseline pipeline
    python scripts/benchmark_infoblox.py --bulk tiny    # bulk pipeline
    python scripts/benchmark_infoblox.py --matrix       # full grid, takes a few minutes

Required env (only needed when this container has its own postgres + redis):
    NAUTOBOT_DB_HOST=127.0.0.1   NAUTOBOT_REDIS_HOST=127.0.0.1
    NAUTOBOT_DB_PASSWORD=<pg_pw> NAUTOBOT_REDIS_PASSWORD=""
"""

import json
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

from contextlib import contextmanager  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402

from nautobot.extras.context_managers import (  # noqa: E402
    deferred_change_logging_for_bulk_operation,
    web_request_context,
)
from nautobot.ipam.models import IPAddress as OrmIPAddress  # noqa: E402
from nautobot.ipam.models import Namespace as OrmNamespace  # noqa: E402
from nautobot.ipam.models import Prefix as OrmPrefix  # noqa: E402

from nautobot_ssot.tests.infoblox.performance.test_infoblox_baseline import (  # noqa: E402
    SCALES as SOURCE_SCALES,
    _run_load,
)
from nautobot_ssot.tests.infoblox.performance.test_infoblox_full_pipeline import (  # noqa: E402
    SCALES as PIPELINE_SCALES,
    _InfobloxFullPipelineBase,
)
from nautobot_ssot.tests.infoblox.performance.test_infoblox_bulk_pipeline import (  # noqa: E402
    _InfobloxBulkPipelineBase,
)

from nautobot_ssot.flags import SSoTFlags  # noqa: E402
from nautobot_ssot.utils.streaming_pipeline import run_streaming_sync  # noqa: E402


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _setup_db():
    """Ensure minimum Nautobot base data exists for pipeline runs."""
    from django.contrib.contenttypes.models import ContentType
    from nautobot.extras.models import Status
    from nautobot.ipam.models import VLAN, VLANGroup

    status_active, _ = Status.objects.get_or_create(name="Active")
    for model in [OrmIPAddress, OrmPrefix, VLAN, VLANGroup, OrmNamespace]:
        status_active.content_types.add(ContentType.objects.get_for_model(model))
    return status_active


def _clean_sync_data():
    """Remove all IP/Prefix/Namespace objects written by a previous benchmark run.

    Prevents the next run's NautobotAdapter.load() from picking up stale data
    from the prior run. Safe for the dev environment — only removes objects
    that live under namespaces named 'ns-*' (created by MockInfobloxClient).
    """
    mock_ns_names = list(OrmNamespace.objects.filter(name__startswith="ns-").values_list("name", flat=True))
    if not mock_ns_names:
        return
    deleted_ips, _ = OrmIPAddress.objects.filter(parent__namespace__name__in=mock_ns_names).delete()
    deleted_pfx, _ = OrmPrefix.objects.filter(namespace__name__in=mock_ns_names).delete()
    deleted_ns, _ = OrmNamespace.objects.filter(name__startswith="ns-").delete()
    total = deleted_ips + deleted_pfx + deleted_ns
    if total:
        print(f"\n[cleanup] Removed {deleted_ips} IPs, {deleted_pfx} prefixes, {deleted_ns} namespaces from prior run.")


def _bench_user():
    """Return a user record to drive web_request_context (creates one if absent)."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="benchmark", defaults={"is_superuser": True, "is_active": True})
    return user


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


@contextmanager
def _patched_validated_save_to_save():
    """Temporarily make validated_save() skip full_clean() on the IPAM models we touch.

    Isolates the cost of clean() so we can compare:
        validated_save (full_clean + save)   vs   save (no clean)

    Touches only OrmNamespace/OrmPrefix/OrmIPAddress so we don't bleed into other
    Nautobot operations the test harness performs (Status setup etc.).
    """
    targets = [OrmNamespace, OrmPrefix, OrmIPAddress]
    originals = {cls: cls.validated_save for cls in targets}
    try:
        for cls in targets:
            cls.validated_save = lambda self, *a, **kw: type(self).save(self, *a, **kw)
        yield
    finally:
        for cls, fn in originals.items():
            cls.validated_save = fn


@contextmanager
def _deferred_changelog_context(user):
    """Wrap a block in web_request_context + deferred_change_logging_for_bulk_operation.

    Defers ObjectChange row writes until block exit, batching them.
    """
    with web_request_context(user, context_detail="benchmark"):
        with deferred_change_logging_for_bulk_operation():
            yield


@contextmanager
def _immediate_changelog_context(user):
    """Wrap a block in just web_request_context (no deferral).

    Activates the change context so post_save signals fire and write
    ObjectChange rows IMMEDIATELY, per-save. Baseline for measuring what
    `deferred_change_logging` actually saves vs the per-save default.
    """
    with web_request_context(user, context_detail="benchmark"):
        yield


# ---------------------------------------------------------------------------
# Pipeline runners (return timing dict)
# ---------------------------------------------------------------------------


def _run_full(scale, status_active, mode_label, sync_wrapper=None):
    """Run the validated_save / save / save-defer pipeline.

    sync_wrapper is an optional context manager used to wrap the sync_to() call
    only — load and diff phases run unwrapped so timings are comparable.
    """
    runner = _InfobloxFullPipelineBase()
    runner.status_active = status_active
    runner.SCALE = scale

    if sync_wrapper is not None:
        # Wrap only the sync_to() call by monkey-patching for this run.
        from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter

        original_sync_to = InfobloxAdapter.sync_to

        def wrapped_sync_to(self, target, *args, **kwargs):
            with sync_wrapper():
                return original_sync_to(self, target, *args, **kwargs)

        InfobloxAdapter.sync_to = wrapped_sync_to
        try:
            result = runner._run_pipeline()
        finally:
            InfobloxAdapter.sync_to = original_sync_to
    else:
        result = runner._run_pipeline()
    result["mode"] = mode_label
    result["scale"] = scale
    return result


def _run_bulk(scale, status_active, batch_size, mode_label):
    """Run the bulk_create/bulk_update pipeline at the given batch size."""
    from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot_bulk import BulkNautobotAdapter

    original = BulkNautobotAdapter._bulk_batch_size
    BulkNautobotAdapter._bulk_batch_size = batch_size
    try:
        runner = _InfobloxBulkPipelineBase()
        runner.status_active = status_active
        runner.SCALE = scale
        result = runner._run_pipeline()
    finally:
        BulkNautobotAdapter._bulk_batch_size = original
    result["mode"] = mode_label
    result["scale"] = scale
    return result


def _run_bulk_audit(scale, status_active, mode_label, user):
    """Legacy bulk pipeline (DiffSync diff_to + sync_to) with audit chain restored.

    This proves the bulk + audit composition does NOT require the streaming
    pipeline. Wraps `src.sync_to(dst)` in `web_request_context` +
    `deferred_change_logging_for_bulk_operation`, with `BulkNautobotAdapter`
    configured to re-fire post_save (so the changelog handler captures into
    the deferred dict) and emit `bulk_post_create` after each flush stage.

    The composition:
        1. diff_to: builds the in-memory Diff tree (no signals)
        2. sync_to: walks the Diff tree, calling per-model create() which
           queues ORM objects to the BulkNautobotAdapter's flush queues
        3. sync_complete: flush_all(refire_post_save=True, bulk_signal=True)
           - bulk_create per model class
           - per-instance post_save re-fire → changelog handler captures OCs
             into the deferred dict (because defer_object_changes=True from
             the wrapping context)
           - bulk_post_create signal fires once per model class
        4. Exit deferred CL block: flush_deferred_object_changes →
           bulk_create OC rows
        5. Exit web_request_context: cleanup loop fires webhooks/jobhooks/events

    Same audit semantics as `stream_tier2_audit` but uses the LEGACY bulk
    pipeline (no streaming, no SQLite). Useful for measuring "audit
    composition" independent of "streaming."
    """
    from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot_bulk import BulkNautobotAdapter

    BulkNautobotAdapter.refire_post_save = True
    BulkNautobotAdapter.bulk_signal = True
    try:
        runner = _InfobloxBulkPipelineBase()
        runner.status_active = status_active
        runner.SCALE = scale
        with _deferred_changelog_context(user):
            result = runner._run_pipeline()
    finally:
        BulkNautobotAdapter.refire_post_save = False
        BulkNautobotAdapter.bulk_signal = False
    result["mode"] = mode_label
    result["scale"] = scale
    return result


def _run_stream(scale, status_active, mode_label, user, *,
                flags: SSoTFlags = SSoTFlags.STREAMING,
                use_strict_source=False,
                store_class=None):
    """Run the SQLite-streaming pipeline at one scale.

    flags: SSoTFlags word — must include STREAMING; BULK_WRITES picks Tier 2;
           VALIDATE_ON_DUMP / VALIDATE_RELATIONS / VALIDATE_STRICT compose Hooks 2/3.
    use_strict_source: Hook 1 — swap InfobloxAdapter for StrictInfobloxAdapter.
                       (Hook 1 isn't a flag bit; it's a per-integration adapter
                       class swap. The benchmark exposes it as a separate kwarg
                       to keep the framework-vs-integration split clean.)

    Returns a dict shaped like the other _run_* helpers so the matrix table
    can pivot results consistently.
    """
    from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
    from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox_strict import StrictInfobloxAdapter
    from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter
    from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot_bulk import BulkNautobotAdapter
    from nautobot_ssot.tests.infoblox.performance.mock_client import MockInfobloxClient
    from nautobot_ssot.tests.infoblox.performance.test_infoblox_full_pipeline import (
        SCALES as PIPELINE_SCALES,
        _make_config,
        _make_job,
    )

    client = MockInfobloxClient(**PIPELINE_SCALES[scale])
    nv_names = [nv["name"] for nv in client.get_network_views()]
    config = _make_config(nv_names, default_status=status_active)
    job = _make_job()
    src_cls = StrictInfobloxAdapter if use_strict_source else InfobloxAdapter
    src = src_cls(job=job, sync=None, conn=client, config=config)
    use_bulk = bool(flags & SSoTFlags.BULK_WRITES)
    dst_cls = BulkNautobotAdapter if use_bulk else NautobotAdapter
    dst = dst_cls(job=job, sync=None, config=config)

    sr = run_streaming_sync(src, dst, flags=flags, user=user, store_class=store_class)

    tier_label = "TIER2" if use_bulk else "TIER1"
    print(
        f"\n{'='*62}\n"
        f"  SCALE : {scale.upper()}  [STREAM-{tier_label}]  flags={flags!r}\n"
        f"{'='*62}\n"
        f"  Phase 1 src load   : {sr.t_src:.3f}s\n"
        f"  Phase 1b src dump  : {sr.t_src_dump:.3f}s\n"
        f"  Phase 2 dst load   : {sr.t_dst:.3f}s\n"
        f"  Phase 2b dst dump  : {sr.t_dst_dump:.3f}s\n"
        f"  Phase 3 diff       : {sr.t_diff:.3f}s   diff_stats={sr.diff_stats}\n"
        f"  Phase 4 sync       : {sr.t_sync:.3f}s   sync_stats={sr.sync_stats}\n"
        f"  ──────────────────────────────────────\n"
        f"  TOTAL              : {sr.total:.3f}s\n"
    )

    # Map streaming timings into the same shape used by _run_full / _run_bulk.
    return {
        "mode": mode_label,
        "scale": scale,
        "t_src": sr.t_src + sr.t_src_dump,
        "t_dst": sr.t_dst + sr.t_dst_dump,
        "t_diff": sr.t_diff,
        "t_sync": sr.t_sync,
        "creates": sr.diff_stats.get("create", 0),
        "src_objects": sr.store_counts.get("source_records", 0),
    }


# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------


def run_mode(mode, scale, status_active, user):
    """Dispatch one mode × scale and return the timing dict."""
    _clean_sync_data()
    if mode == "validated_save_no_cl":
        # validated_save() running OUTSIDE any web_request_context. The
        # changelog signal handler short-circuits because change_context_state
        # is None, so no OC rows get written. NOT a production-shaped path —
        # it's a strict lower bound on validated_save's cost without changelog.
        return _run_full(scale, status_active, mode)
    if mode == "validated_save":
        # **Production baseline**: validated_save() inside web_request_context
        # with NO deferral. This is what an SSoT job actually does today —
        # signals fire, OC rows get INSERTed per save, web_request_context
        # cleanup fires webhooks/jobhooks/events.
        return _run_full(
            scale,
            status_active,
            mode,
            sync_wrapper=lambda: _immediate_changelog_context(user),
        )
    if mode == "save":
        with _patched_validated_save_to_save():
            return _run_full(scale, status_active, mode)
    if mode == "save_deferred_cl":
        with _patched_validated_save_to_save():
            return _run_full(
                scale,
                status_active,
                mode,
                sync_wrapper=lambda: _deferred_changelog_context(user),
            )
    if mode == "save_immediate_cl":
        # Same as save_deferred_cl but signals write OC rows per-save instead
        # of batching at end of block. Quantifies what the deferral actually saves.
        with _patched_validated_save_to_save():
            return _run_full(
                scale,
                status_active,
                mode,
                sync_wrapper=lambda: _immediate_changelog_context(user),
            )
    if mode == "bulk_b250":
        return _run_bulk(scale, status_active, 250, mode)
    if mode == "bulk_b1000":
        return _run_bulk(scale, status_active, 1000, mode)
    if mode == "bulk_b250_audit":
        return _run_bulk_audit(scale, status_active, mode, user)
    if mode == "stream_tier1":
        return _run_stream(scale, status_active, mode, user, flags=SSoTFlags.STREAM_TIER1)
    if mode == "stream_tier2":
        return _run_stream(scale, status_active, mode, user, flags=SSoTFlags.STREAM_TIER2)
    if mode == "stream_tier1_5":
        # Composite shorthand from SSoTFlags: STREAMING|BULK_WRITES|VALIDATE_SOURCE_SHAPE|VALIDATE_ON_DUMP
        return _run_stream(
            scale, status_active, mode, user,
            flags=SSoTFlags.STREAM_TIER1_5,
            use_strict_source=True,  # Hook 1 — adapter class swap, not a flag bit
        )
    if mode == "stream_tier1_7":
        # Adds Hook 3 (Phase B IP-in-prefix validator) on top of stream_tier1_5
        return _run_stream(
            scale, status_active, mode, user,
            flags=SSoTFlags.STREAM_TIER1_7,
            use_strict_source=True,
        )
    if mode == "stream_tier2_audit":
        # STREAM_TIER2 (bulk_create) + REFIRE_POST_SAVE wrapped in the
        # deferred_change_logging context. Demonstrates the composition that
        # gives "fast bulk + full audit chain" — bulk INSERT speed for the
        # data path, post_save re-fired per row so the changelog handler
        # captures into the deferred dict, deferred CL flushes OCs in one
        # bulk_create at end of block, web_request_context cleanup fires
        # webhooks/jobhooks/events. Same audit semantics as stream_tier1
        # but skips the per-row save() round-trip and full_clean().
        flags = SSoTFlags.STREAM_TIER2 | SSoTFlags.REFIRE_POST_SAVE
        with _deferred_changelog_context(user):
            return _run_stream(
                scale, status_active, mode, user,
                flags=flags,
            )
    if mode == "stream_tier2_pydict":
        # Same as stream_tier2 but the diff store is in-memory Python dicts
        # instead of SQLite. Isolates "what does SQLite specifically buy us
        # vs plain Python dicts in the streaming pipeline?" — should produce
        # identical correctness at slightly different timing for the diff
        # phase. No validators / scope (PyDictStore has no SQL conn).
        from nautobot_ssot.utils.pydict_store import PyDictStore
        return _run_stream(
            scale, status_active, mode, user,
            flags=SSoTFlags.STREAM_TIER2,
            store_class=PyDictStore,
        )
    raise ValueError(f"Unknown mode: {mode}")


MATRIX_MODES = [
    "validated_save",         # PRODUCTION baseline: validated_save inside web_request_context
    "validated_save_no_cl",   # reference: validated_save outside any change context (no OC writes)
    "save",
    "save_immediate_cl",
    "save_deferred_cl",
    "bulk_b250",
    "bulk_b1000",
    "bulk_b250_audit",        # legacy bulk pipeline + REFIRE + deferred CL: same audit story without streaming

    "stream_tier1",
    "stream_tier1_5",
    "stream_tier1_7",
    "stream_tier2",
    "stream_tier2_audit",     # bulk_create + REFIRE + deferred CL: fast bulk with full audit chain
    "stream_tier2_pydict",    # SAME as stream_tier2 but diff store is Python dicts instead of SQLite
]
MATRIX_SCALES = ["tiny", "small", "medium"]


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------


def _print_results_table(results):
    """Render a markdown-style table to stdout. Each row is one mode × scale."""
    print("\n" + "=" * 80)
    print("  RESULTS")
    print("=" * 80)
    header = ["mode", "scale", "src_load(s)", "diff(s)", "sync->DB(s)", "TOTAL(s)", "creates"]
    widths = [max(len(h), 16) for h in header]
    rows = []
    for r in results:
        row = [
            r["mode"],
            r["scale"],
            f"{r['t_src']:.3f}",
            f"{r['t_diff']:.3f}",
            f"{r['t_sync']:.3f}",
            f"{r['t_src'] + r['t_dst'] + r['t_diff'] + r['t_sync']:.3f}",
            str(r["creates"]),
        ]
        rows.append(row)
        widths = [max(w, len(c)) for w, c in zip(widths, row)]

    def fmt(cells):
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths))

    print(fmt(header))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt(row))


def _print_pivot_table(results):
    """Render a pivot of TOTAL seconds: rows=mode, cols=scale."""
    pivot = {}
    scales_seen = []
    for r in results:
        s = r["scale"]
        if s not in scales_seen:
            scales_seen.append(s)
        total = r["t_src"] + r["t_dst"] + r["t_diff"] + r["t_sync"]
        pivot.setdefault(r["mode"], {})[s] = total

    print("\n" + "=" * 80)
    print("  TOTAL TIME (seconds) -- rows: mode, columns: scale")
    print("=" * 80)
    width = max(20, *(len(m) for m in pivot))
    header = "mode".ljust(width) + "  " + "  ".join(s.rjust(10) for s in scales_seen)
    print(header)
    print("-" * len(header))
    for mode, by_scale in pivot.items():
        row = mode.ljust(width) + "  " + "  ".join(
            (f"{by_scale.get(s, float('nan')):>10.3f}" if s in by_scale else "       n/a")
            for s in scales_seen
        )
        print(row)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    scales_arg = [a for a in args if not a.startswith("--")]

    matrix_mode = "--matrix" in flags
    full_mode = "--full" in flags                  # PRODUCTION baseline (validated_save + web_request_context)
    full_no_cl_mode = "--full-no-cl" in flags      # validated_save outside change context (reference only)
    save_mode = "--save" in flags
    save_cl_mode = "--save-cl" in flags
    save_defer_mode = "--save-defer" in flags
    bulk_mode = "--bulk" in flags
    bulk1000_mode = "--bulk-1000" in flags
    bulk_audit_mode = "--bulk-audit" in flags
    stream_t1_mode = "--stream-tier1" in flags
    stream_t15_mode = "--stream-tier1-5" in flags
    stream_t17_mode = "--stream-tier1-7" in flags
    stream_t2_mode = "--stream-tier2" in flags
    stream_t2_audit_mode = "--stream-tier2-audit" in flags
    stream_t2_pydict_mode = "--stream-tier2-pydict" in flags
    source_mode = not any([
        matrix_mode, full_mode, full_no_cl_mode, save_mode, save_cl_mode, save_defer_mode,
        bulk_mode, bulk1000_mode, bulk_audit_mode,
        stream_t1_mode, stream_t15_mode, stream_t17_mode,
        stream_t2_mode, stream_t2_audit_mode, stream_t2_pydict_mode,
    ])

    if source_mode:
        valid = list(SOURCE_SCALES.keys())
        requested = scales_arg or valid
        invalid = [s for s in requested if s not in valid]
        if invalid:
            print(f"Unknown scale(s): {invalid}. Valid choices: {valid}")
            sys.exit(1)
        for scale in requested:
            _run_load(scale)
        sys.exit(0)

    if matrix_mode:
        valid = list(PIPELINE_SCALES.keys())
        requested = scales_arg or MATRIX_SCALES
        invalid = [s for s in requested if s not in valid]
        if invalid:
            print(f"Unknown scale(s): {invalid}. Valid choices: {valid}")
            sys.exit(1)
        status_active = _setup_db()
        user = _bench_user()
        results = []
        t0 = time.perf_counter()
        for mode in MATRIX_MODES:
            for scale in requested:
                print(f"\n>>> {mode} x {scale} <<<")
                result = run_mode(mode, scale, status_active, user)
                results.append(result)
        elapsed = time.perf_counter() - t0
        _clean_sync_data()
        _print_results_table(results)
        _print_pivot_table(results)
        print(f"\nMatrix completed in {elapsed:.1f}s ({len(results)} runs).")
        out_path = "/tmp/benchmark_results.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Raw results written to {out_path}")
        sys.exit(0)

    # Single-mode dispatch (one or more flags can be combined for side-by-side).
    valid = list(PIPELINE_SCALES.keys())
    requested = scales_arg or valid
    invalid = [s for s in requested if s not in valid]
    if invalid:
        print(f"Unknown scale(s): {invalid}. Valid choices: {valid}")
        sys.exit(1)
    status_active = _setup_db()
    user = _bench_user()

    mode_flags = [
        ("validated_save", full_mode),
        ("validated_save_no_cl", full_no_cl_mode),
        ("save", save_mode),
        ("save_immediate_cl", save_cl_mode),
        ("save_deferred_cl", save_defer_mode),
        ("bulk_b250", bulk_mode),
        ("bulk_b1000", bulk1000_mode),
        ("bulk_b250_audit", bulk_audit_mode),
        ("stream_tier1", stream_t1_mode),
        ("stream_tier1_5", stream_t15_mode),
        ("stream_tier1_7", stream_t17_mode),
        ("stream_tier2", stream_t2_mode),
        ("stream_tier2_audit", stream_t2_audit_mode),
        ("stream_tier2_pydict", stream_t2_pydict_mode),
    ]
    for mode, on in mode_flags:
        if not on:
            continue
        for scale in requested:
            print(f"\n>>> {mode} x {scale} <<<")
            run_mode(mode, scale, status_active, user)
