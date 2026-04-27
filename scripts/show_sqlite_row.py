#!/usr/bin/env python
"""Tiny demo: dump one prefix from src + dst into SQLite and show the rows.

Seeds the destination DB with the SAME prefix the mock Infoblox produces but
with a different description, so source/dest disagree on one attribute.
Demonstrates what dump_adapter writes and what the differ sees.
"""

import json
import os
import sqlite3
from unittest.mock import Mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

from django.contrib.contenttypes.models import ContentType  # noqa: E402
from nautobot.extras.models import Status  # noqa: E402
from nautobot.ipam.models import IPAddress, Namespace, Prefix  # noqa: E402

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter  # noqa: E402
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.mock_client import MockInfobloxClient  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.test_infoblox_full_pipeline import _make_config, _make_job  # noqa: E402
from nautobot_ssot.utils.sqlite_store import DiffSyncStore  # noqa: E402
from nautobot_ssot.utils.streaming_differ import dump_adapter  # noqa: E402

# ---------------------------------------------------------------------------
# Seed: ensure Active status exists, then create one prefix in Nautobot
# whose description differs from what the mock Infoblox returns.
# ---------------------------------------------------------------------------

status_active, _ = Status.objects.get_or_create(name="Active")
for model in [IPAddress, Prefix, Namespace]:
    status_active.content_types.add(ContentType.objects.get_for_model(model))

# Wipe prior demo state.
IPAddress.objects.filter(parent__namespace__name__startswith="ns-").delete()
Prefix.objects.filter(namespace__name__startswith="ns-").delete()
Namespace.objects.filter(name__startswith="ns-").delete()

# Mock Infoblox (tiny scale): nv name="default", prefix 10.0.0.0/24, description=""
client = MockInfobloxClient(num_namespaces=1, prefixes_per_namespace=1, ips_per_prefix=2)

# Seed Nautobot with the matching prefix but a DIFFERENT description.
ns = Namespace.objects.create(name="ns-default")
Prefix.objects.create(
    prefix="10.0.0.0/24",
    namespace=ns,
    type="network",
    status=status_active,
    description="this description came from Nautobot, not Infoblox",
)

# ---------------------------------------------------------------------------
# Build adapters and dump both into a SQLite *file* so we can read it back.
# ---------------------------------------------------------------------------

config = _make_config(["default"], default_status=status_active)
src = InfobloxAdapter(job=_make_job(), sync=None, conn=client, config=config)
dst = NautobotAdapter(job=_make_job(), sync=None, config=config)

src.load()
dst.load()

store = DiffSyncStore(path="/tmp/demo_diff.sqlite")
dump_adapter(src, store, "source_records")
dump_adapter(dst, store, "dest_records")
store.close()

# ---------------------------------------------------------------------------
# Read it back and print the rows side-by-side.
# ---------------------------------------------------------------------------

con = sqlite3.connect("/tmp/demo_diff.sqlite")
con.row_factory = sqlite3.Row


def fetch(table, model_type, unique_key):
    cur = con.execute(
        f"""
        SELECT model_type, unique_key, parent_type, parent_key,
               tree_depth, type_order, identifiers, attrs
        FROM {table}
        WHERE model_type = ? AND unique_key = ?
        """,
        (model_type, unique_key),
    )
    return cur.fetchone()


def show(label, row):
    if row is None:
        print(f"\n--- {label} ---  (no row)\n")
        return
    print(f"\n--- {label} ---")
    print(f"  model_type   : {row['model_type']}")
    print(f"  unique_key   : {row['unique_key']}")
    print(f"  parent_type  : {row['parent_type']}")
    print(f"  parent_key   : {row['parent_key']}")
    print(f"  tree_depth   : {row['tree_depth']}")
    print(f"  type_order   : {row['type_order']}")
    print(f"  identifiers  : {json.dumps(json.loads(row['identifiers']), indent=2)}")
    print(f"  attrs        : {json.dumps(json.loads(row['attrs']), indent=2)}")


# Same prefix, two sides
target_unique_key = "10.0.0.0/24__ns-default"  # InfobloxNetwork.unique_id format
src_row = fetch("source_records", "prefix", target_unique_key)
dst_row = fetch("dest_records", "prefix", target_unique_key)

print(f"\n{'='*60}")
print(f"  prefix unique_key={target_unique_key!r}")
print(f"{'='*60}")
show("SOURCE (Infoblox)", src_row)
show("DEST (Nautobot)", dst_row)

print("\nByte-equal attrs?", (src_row and dst_row and src_row["attrs"] == dst_row["attrs"]))
con.close()

# ---------------------------------------------------------------------------
# Now run the StreamingDiffer against the same store and show diff_results.
# ---------------------------------------------------------------------------

from nautobot_ssot.utils.streaming_differ import StreamingDiffer  # noqa: E402

store = DiffSyncStore(path="/tmp/demo_diff.sqlite")
stats = StreamingDiffer(store).diff()
print(f"\n{'='*60}\n  diff stats: {stats}\n{'='*60}")

print("\n--- diff_results rows for the same prefix ---")
for row in store.conn.execute(
    """
    SELECT action, model_type, unique_key, identifiers, new_attrs, old_attrs
    FROM diff_results WHERE model_type = 'prefix' AND unique_key = ?
    """,
    (target_unique_key,),
):
    action, mt, uk, ids, new_a, old_a = row
    print(f"\n  action      : {action}")
    print(f"  model_type  : {mt}")
    print(f"  unique_key  : {uk}")
    print(f"  identifiers : {ids}")
    print(f"  new_attrs   : {new_a}")
    print(f"  old_attrs   : {old_a}")

store.close()
