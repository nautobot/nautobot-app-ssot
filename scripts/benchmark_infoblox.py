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
  --matrix         — runs all of the above across tiny / small / medium and prints a summary table

Usage (inside the container):
    python scripts/benchmark_infoblox.py                # source load only, all scales
    python scripts/benchmark_infoblox.py small          # source load, one scale
    python scripts/benchmark_infoblox.py --full tiny    # baseline pipeline
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
    """Remove all IP/Prefix/Namespace objects written by a previous benchmark run."""
    mock_ns_names = list(OrmNamespace.objects.filter(name__startswith="ns-").values_list("name", flat=True))
    if not mock_ns_names:
        return
    OrmIPAddress.objects.filter(parent__namespace__name__in=mock_ns_names).delete()
    OrmPrefix.objects.filter(namespace__name__in=mock_ns_names).delete()
    OrmNamespace.objects.filter(name__in=mock_ns_names).delete()


def _bench_user():
    """Get-or-create a user that can be passed into web_request_context()."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="benchmark-runner")
    return user


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


@contextmanager
def _patched_validated_save_to_save():
    """Temporarily make validated_save() skip full_clean() on the IPAM models we touch.

    Isolates the cost of clean() so we can compare:
        validated_save (full_clean + save)   vs   save (no clean)
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
    """Wrap a block in web_request_context + deferred_change_logging_for_bulk_operation."""
    with web_request_context(user, context_detail="benchmark"):
        with deferred_change_logging_for_bulk_operation():
            yield


@contextmanager
def _immediate_changelog_context(user):
    """Wrap a block in just web_request_context (no deferral)."""
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

    Same audit semantics as Tier 2 streaming with REFIRE + deferred CL but
    uses the LEGACY bulk pipeline (no streaming, no SQLite). Useful for
    measuring "audit composition" independent of "streaming."
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


# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------


def run_mode(mode, scale, status_active, user):
    """Dispatch one mode × scale and return the timing dict."""
    _clean_sync_data()
    if mode == "validated_save_no_cl":
        return _run_full(scale, status_active, mode)
    if mode == "validated_save":
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
    raise ValueError(f"Unknown mode: {mode}")


MATRIX_MODES = [
    "validated_save",
    "validated_save_no_cl",
    "save",
    "save_immediate_cl",
    "save_deferred_cl",
    "bulk_b250",
    "bulk_b1000",
    "bulk_b250_audit",
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
    full_mode = "--full" in flags
    full_no_cl_mode = "--full-no-cl" in flags
    save_mode = "--save" in flags
    save_cl_mode = "--save-cl" in flags
    save_defer_mode = "--save-defer" in flags
    bulk_mode = "--bulk" in flags
    bulk1000_mode = "--bulk-1000" in flags
    bulk_audit_mode = "--bulk-audit" in flags
    source_mode = not any([
        matrix_mode, full_mode, full_no_cl_mode, save_mode, save_cl_mode, save_defer_mode,
        bulk_mode, bulk1000_mode, bulk_audit_mode,
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
    ]
    for mode, on in mode_flags:
        if not on:
            continue
        for scale in requested:
            print(f"\n>>> {mode} x {scale} <<<")
            run_mode(mode, scale, status_active, user)
