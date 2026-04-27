#!/usr/bin/env python
"""Verify memory release after dump_adapter + _release_adapter_store.

Loads InfobloxAdapter at medium scale, measures peak in-memory model count
+ tracemalloc bytes, dumps to SQLite, releases the store, GCs, and re-measures.

Pass criteria: DiffSync model instance count drops to ~0 after release+GC.
"""
import gc
import os
import sys
import tracemalloc
from collections import Counter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()


def count_diffsync_models() -> Counter:
    """Walk the GC and count live DiffSync model instances by class name."""
    from diffsync import DiffSyncModel

    counts: Counter = Counter()
    for obj in gc.get_objects():
        try:
            if isinstance(obj, DiffSyncModel):
                counts[type(obj).__name__] += 1
        except (ReferenceError, TypeError):
            continue
    return counts


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def measure(label: str) -> tuple:
    gc.collect()
    counts = count_diffsync_models()
    total = sum(counts.values())
    current, peak = tracemalloc.get_traced_memory()
    print(f"\n--- {label} ---")
    print(f"  DiffSync model instances: {total:,}")
    if counts:
        for cls, n in counts.most_common(5):
            print(f"    {cls}: {n}")
    print(f"  tracemalloc current: {fmt_bytes(current)}  peak: {fmt_bytes(peak)}")
    return total, current, peak


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

tracemalloc.start()

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.mock_client import MockInfobloxClient  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.test_infoblox_full_pipeline import _make_config, _make_job  # noqa: E402
from nautobot_ssot.utils.sqlite_store import DiffSyncStore  # noqa: E402
from nautobot_ssot.utils.streaming_differ import dump_adapter  # noqa: E402
from nautobot_ssot.utils.streaming_pipeline import _release_adapter_store  # noqa: E402

# Use medium scale (8,143 source rows) to make the difference observable
client = MockInfobloxClient(num_namespaces=3, prefixes_per_namespace=10, ips_per_prefix=100)
nv_names = [nv["name"] for nv in client.get_network_views()]
config = _make_config(nv_names, default_status=None)
job = _make_job()
src = InfobloxAdapter(job=job, sync=None, conn=client, config=config)

print("=" * 60)
print(" Memory release test — Infoblox medium (8,143 expected rows)")
print("=" * 60)

# (1) Before load
measure("Before load")

# (2) After load — peak in-memory state
src.load()
peak_count, peak_current, peak_peak = measure("After src.load() (peak)")

# (3) After dump_adapter — local rows/snapshot dropped, but adapter store still populated
store = DiffSyncStore(path=":memory:")
n_rows = dump_adapter(src, store, "source_records")
print(f"\n  dumped {n_rows} rows into SQLite")
post_dump_count, _, _ = measure("After dump_adapter (store still populated)")

# (4) After _release_adapter_store — should drop the model instances
_release_adapter_store(src)
post_release_count, post_release_current, _ = measure("After _release_adapter_store + gc")

# (5) Drop the local refs to src to allow the adapter object itself to GC
del src
gc.collect()
final_count, final_current, _ = measure("After del src + gc (terminal state)")

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print(" Verdict")
print("=" * 60)
print(f"  Peak DiffSync models       : {peak_count:,}")
print(f"  After dump (no release)    : {post_dump_count:,}  ({100*post_dump_count/peak_count:.0f}% of peak)")
print(f"  After _release_adapter_store: {post_release_count:,}  ({100*post_release_count/peak_count:.0f}% of peak)")
print(f"  After del src + gc         : {final_count:,}  ({100*final_count/peak_count:.0f}% of peak)")

print(f"\n  Memory bytes drop (peak → final): {fmt_bytes(peak_current - final_current)}")

if final_count == 0:
    print("\n  PASS — all DiffSync model instances released")
elif final_count < peak_count * 0.05:
    print(f"\n  PASS (mostly) — {final_count} stragglers (< 5% of peak)")
else:
    print(f"\n  FAIL — {final_count} model instances still alive after release+gc")
    sys.exit(1)

store.close()
tracemalloc.stop()
