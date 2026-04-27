#!/usr/bin/env python
"""Compare peak in-memory state: LEGACY (in-memory Diff tree) vs STREAMING.

Both paths run against the same Infoblox medium fixture (8,143 source rows)
and record DiffSync model instance count + tracemalloc bytes at each phase.

The interesting numbers:
  * peak_models     — max concurrent live DiffSync model instances
  * peak_tracemalloc — max bytes tracked by the allocator
"""
import gc
import os
import tracemalloc

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

from django.contrib.contenttypes.models import ContentType  # noqa: E402
from nautobot.extras.models import Status  # noqa: E402
from nautobot.ipam.models import IPAddress, Namespace, Prefix, VLAN, VLANGroup  # noqa: E402

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter  # noqa: E402
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.mock_client import MockInfobloxClient  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.test_infoblox_full_pipeline import _make_config, _make_job  # noqa: E402
from nautobot_ssot.utils.sqlite_store import DiffSyncStore  # noqa: E402
from nautobot_ssot.utils.streaming_differ import StreamingDiffer, dump_adapter  # noqa: E402
from nautobot_ssot.utils.streaming_pipeline import _release_adapter_store  # noqa: E402

# Ensure required Status setup
active, _ = Status.objects.get_or_create(name="Active")
for m in [IPAddress, Prefix, Namespace, VLAN, VLANGroup]:
    active.content_types.add(ContentType.objects.get_for_model(m))

# Cleanup any prior demo state
IPAddress.objects.filter(parent__namespace__name__startswith="ns-").delete()
Prefix.objects.filter(namespace__name__startswith="ns-").delete()
Namespace.objects.filter(name__startswith="ns-").delete()


def count_diffsync_models() -> int:
    from diffsync import DiffSyncModel
    n = 0
    for obj in gc.get_objects():
        try:
            if isinstance(obj, DiffSyncModel):
                n += 1
        except (ReferenceError, TypeError):
            continue
    return n


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def make_adapters():
    """Fresh src + dst pair at medium scale."""
    client = MockInfobloxClient(num_namespaces=3, prefixes_per_namespace=10, ips_per_prefix=100)
    nv_names = [nv["name"] for nv in client.get_network_views()]
    config = _make_config(nv_names, default_status=active)
    job = _make_job()
    return (
        InfobloxAdapter(job=job, sync=None, conn=client, config=config),
        NautobotAdapter(job=job, sync=None, config=config),
    )


def measure(label: str, peak_so_far: list) -> None:
    gc.collect()
    n = count_diffsync_models()
    cur, peak = tracemalloc.get_traced_memory()
    peak_so_far[0] = max(peak_so_far[0], n)
    peak_so_far[1] = max(peak_so_far[1], cur)
    print(f"  [{label:<32}] models={n:>6,}   current={fmt_bytes(cur):>12}   peak={fmt_bytes(peak):>12}")


# ---------------------------------------------------------------------------
# RUN 1 — Legacy in-memory pipeline (src + dst + Diff tree concurrent)
# ---------------------------------------------------------------------------

print("=" * 72)
print(" RUN 1 — LEGACY in-memory pipeline (src.load + dst.load + diff_to)")
print("=" * 72)

tracemalloc.start()
gc.collect()
peak_legacy = [0, 0]  # [max model count, max tracemalloc current]

src, dst = make_adapters()
measure("Before any load", peak_legacy)

src.load()
measure("After src.load()", peak_legacy)

dst.load()
measure("After dst.load()", peak_legacy)

diff = src.diff_to(dst)
measure("After src.diff_to(dst)", peak_legacy)

# Hold everything alive (this is what production does until sync finishes)
hold = (src, dst, diff)
measure("Holding src + dst + diff", peak_legacy)

del src, dst, diff, hold
gc.collect()
measure("After all released", peak_legacy)

tracemalloc.stop()

# ---------------------------------------------------------------------------
# RUN 2 — Streaming pipeline (dump + release + dump + release + SQL diff)
# ---------------------------------------------------------------------------

print()
print("=" * 72)
print(" RUN 2 — STREAMING pipeline (dump + release; SQL diff in SQLite)")
print("=" * 72)

# Reset DB state for a clean run
IPAddress.objects.filter(parent__namespace__name__startswith="ns-").delete()
Prefix.objects.filter(namespace__name__startswith="ns-").delete()
Namespace.objects.filter(name__startswith="ns-").delete()

tracemalloc.start()
gc.collect()
peak_streaming = [0, 0]

src, dst = make_adapters()
store = DiffSyncStore(path=":memory:")
measure("Before any load", peak_streaming)

src.load()
measure("After src.load()", peak_streaming)

dump_adapter(src, store, "source_records")
measure("After dump_adapter(src)", peak_streaming)

_release_adapter_store(src)
gc.collect()
measure("After _release(src) + gc", peak_streaming)

dst.load()
measure("After dst.load()", peak_streaming)

dump_adapter(dst, store, "dest_records")
measure("After dump_adapter(dst)", peak_streaming)

_release_adapter_store(dst)
gc.collect()
measure("After _release(dst) + gc", peak_streaming)

differ_stats = StreamingDiffer(store).diff()
measure("After StreamingDiffer.diff()", peak_streaming)

print(f"\n  diff stats: {differ_stats}")
print(f"  SQLite row counts: {store.counts()}")

store.close()
tracemalloc.stop()

# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

print()
print("=" * 72)
print(" COMPARISON — peak resource usage during the diff phase")
print("=" * 72)
print(f"  LEGACY (in-mem Diff tree)  : peak_models={peak_legacy[0]:,}   peak_current={fmt_bytes(peak_legacy[1])}")
print(f"  STREAMING (SQLite)         : peak_models={peak_streaming[0]:,}   peak_current={fmt_bytes(peak_streaming[1])}")
print()
delta_legacy_vs_sql = peak_legacy[1] - peak_streaming[1]
print(f"  legacy → SQLite : {fmt_bytes(delta_legacy_vs_sql)} freed (ratio {peak_legacy[1]/peak_streaming[1]:.2f}×)")
