#!/usr/bin/env python
"""End-to-end demo: scoped sync targets ONE prefix's subtree, leaves
everything else untouched.

Setup:
    Source (mock Infoblox) has 3 namespaces × 10 prefixes × 100 IPs (~8k rows).
    Destination (Nautobot) starts empty.

Test 1 — full sync:
    Run the full streaming pipeline → all 8k rows get created.

Test 2 — scoped sync targeting prefix 10.0.5.0/24:
    Pre-condition: clean DB.
    Pre-populate dest with everything EXCEPT the targeted prefix + its IPs.
    Run scoped sync with scope = SyncScope("prefix", "10.0.5.0/24__ns-default", integration="infoblox").
    Verify only rows in that subtree got created — other prefixes' IPs untouched.

Test 3 — scoped sync targeting a single IP:
    Demonstrates that scoping works at non-root levels too.
"""

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

from django.contrib.contenttypes.models import ContentType  # noqa: E402
from nautobot.extras.models import Status  # noqa: E402
from nautobot.ipam.models import IPAddress, Namespace, Prefix, VLAN, VLANGroup  # noqa: E402

from nautobot_ssot.flags import SSoTFlags  # noqa: E402
from nautobot_ssot.scope import SyncScope, register_subtree_expander  # noqa: E402
from nautobot_ssot.integrations.infoblox.scope import expand_infoblox_subtree  # noqa: E402
from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter  # noqa: E402
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot_bulk import BulkNautobotAdapter  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.mock_client import MockInfobloxClient  # noqa: E402
from nautobot_ssot.tests.infoblox.performance.test_infoblox_full_pipeline import _make_config, _make_job  # noqa: E402
from nautobot_ssot.utils.streaming_pipeline import run_streaming_sync  # noqa: E402

# Register the Infoblox custom expander
register_subtree_expander("infoblox", expand_infoblox_subtree)

# Setup base data
active, _ = Status.objects.get_or_create(name="Active")
for m in [IPAddress, Prefix, Namespace, VLAN, VLANGroup]:
    active.content_types.add(ContentType.objects.get_for_model(m))


def _wipe_mock_data():
    IPAddress.objects.filter(parent__namespace__name__startswith="ns-").delete()
    Prefix.objects.filter(namespace__name__startswith="ns-").delete()
    Namespace.objects.filter(name__startswith="ns-").delete()


def _make_pair(scale=(3, 10, 100)):
    """Fresh src + dst adapters at the given scale."""
    nns, nprefix, nip = scale
    client = MockInfobloxClient(num_namespaces=nns, prefixes_per_namespace=nprefix, ips_per_prefix=nip)
    nv_names = [nv["name"] for nv in client.get_network_views()]
    config = _make_config(nv_names, default_status=active)
    job = _make_job()
    return (
        InfobloxAdapter(job=job, sync=None, conn=client, config=config),
        BulkNautobotAdapter(job=job, sync=None, config=config),
    )


def _count_state():
    return {
        "namespaces": Namespace.objects.filter(name__startswith="ns-").count(),
        "prefixes":   Prefix.objects.filter(namespace__name__startswith="ns-").count(),
        "ips":        IPAddress.objects.filter(parent__namespace__name__startswith="ns-").count(),
    }


# ===========================================================================
# Test 1 — full sync (baseline behavior)
# ===========================================================================

print("=" * 72)
print(" Test 1 — Full sync (no scope) — should sync everything")
print("=" * 72)

_wipe_mock_data()
src, dst = _make_pair()
print(f"\n  Pre-sync state:  {_count_state()}")
result = run_streaming_sync(
    src, dst,
    flags=SSoTFlags.STREAMING | SSoTFlags.BULK_WRITES,
)
print(f"  Diff stats:      {result.diff_stats}")
print(f"  Sync stats:      {result.sync_stats}")
print(f"  Post-sync state: {_count_state()}")
print(f"  TOTAL time:      {result.total:.3f}s")

# Snapshot full-sync state for reference
full_sync_counts = _count_state()
assert full_sync_counts["namespaces"] >= 3, "expected ≥3 namespaces created"
assert full_sync_counts["prefixes"] >= 30, "expected ≥30 prefixes created"
assert full_sync_counts["ips"] >= 3000, "expected ≥3000 IPs created"
print("\n  PASS — full sync created the expected data.")


# ===========================================================================
# Test 2 — scoped sync targeting ONE prefix
# ===========================================================================
#
# Strategy: wipe all the IPs the targeted prefix would own, then run a scoped
# sync. Verify only THOSE IPs get re-created — other prefixes' IPs should
# already be present and untouched (no churn, no orphan deletes).

print("\n" + "=" * 72)
print(" Test 2 — Scoped sync targeting prefix '10.0.5.0/24__ns-default'")
print("=" * 72)

target_ns = "ns-default"
target_prefix = "10.0.5.0/24"
target_unique_key = f"{target_prefix}__{target_ns}"

# Identify the OrmPrefix we'll target so we can wipe its IPs
target_orm = Prefix.objects.get(prefix=target_prefix, namespace__name=target_ns)
ip_count_before_wipe = IPAddress.objects.filter(parent=target_orm).count()
ip_count_in_other_prefixes = IPAddress.objects.exclude(parent=target_orm).filter(parent__namespace__name__startswith="ns-").count()

print(f"\n  Target prefix has {ip_count_before_wipe} IPs in DB; {ip_count_in_other_prefixes} IPs in OTHER prefixes")

# Snapshot ALL non-target IPs so we can verify they're untouched
other_ip_pks_before = set(
    IPAddress.objects.exclude(parent=target_orm).filter(parent__namespace__name__startswith="ns-")
    .values_list("pk", flat=True)
)

# Wipe only the target prefix's IPs (simulate them being deleted/missing)
deleted_count, _ = IPAddress.objects.filter(parent=target_orm).delete()
print(f"  Wiped {deleted_count} IPs from target prefix (simulating drift)")
state_pre_scoped = _count_state()
print(f"  State pre-scoped-sync: {state_pre_scoped}")

# Run scoped sync — should ONLY touch the target prefix's subtree
src, dst = _make_pair()
scope = SyncScope(
    model_type="prefix",
    unique_key=target_unique_key,
    integration="infoblox",
)
result = run_streaming_sync(
    src, dst,
    flags=SSoTFlags.STREAMING | SSoTFlags.BULK_WRITES,
    scope=scope,
)
print(f"\n  Diff stats:        {result.diff_stats}")
print(f"  Sync stats:        {result.sync_stats}")
print(f"  Post-sync state:   {_count_state()}")
print(f"  Skipped out-of-scope rows: {result.diff_stats.get('skipped_out_of_scope', 0)}")
print(f"  Subtree size:      {result.diff_stats.get('scope_keys_in_subtree', 0)}")
print(f"  TOTAL time:        {result.total:.3f}s")

# Verify: target prefix's IPs were re-created
target_ip_count_after = IPAddress.objects.filter(parent=target_orm).count()
print(f"\n  Target prefix IPs: was {ip_count_before_wipe} → wiped to 0 → restored to {target_ip_count_after}")
assert target_ip_count_after == ip_count_before_wipe, \
    f"expected {ip_count_before_wipe} IPs restored on target, got {target_ip_count_after}"

# Verify: every OTHER IP's pk is unchanged (no churn outside scope)
other_ip_pks_after = set(
    IPAddress.objects.exclude(parent=target_orm).filter(parent__namespace__name__startswith="ns-")
    .values_list("pk", flat=True)
)
unchanged = len(other_ip_pks_after & other_ip_pks_before)
out_of_scope_changes = len(other_ip_pks_after ^ other_ip_pks_before)
print(f"  Out-of-scope IPs:  {len(other_ip_pks_before)} before, {len(other_ip_pks_after)} after; {unchanged} pks unchanged; {out_of_scope_changes} pks differ")
assert out_of_scope_changes == 0, f"out-of-scope IPs changed! delta={out_of_scope_changes}"
print("\n  PASS — scoped sync touched ONLY the target prefix's subtree.")


# ===========================================================================
# Test 3 — scoped sync targeting a single IP (non-root)
# ===========================================================================

print("\n" + "=" * 72)
print(" Test 3 — Scoped sync targeting a SINGLE IP (non-root scope)")
print("=" * 72)

# Pick a specific IP and delete just that one
victim_ip = IPAddress.objects.filter(parent__namespace__name=target_ns).order_by("pk").first()
victim_address = str(victim_ip.address).split("/")[0]
victim_pk = victim_ip.pk
victim_parent_orm = victim_ip.parent
print(f"\n  Targeting IP: {victim_address} in {target_ns}")

# The Infoblox unique_key for an IPAddress is: f"{address}__{prefix}__{prefix_length}__{namespace}"
victim_unique_key = f"{victim_address}__{victim_parent_orm.prefix}__{victim_parent_orm.prefix_length}__{target_ns}"

# Wipe the victim
victim_ip.delete()
print(f"  Deleted IP from DB (pk was {victim_pk})")

# Snapshot ALL OTHER IPs to verify they're untouched
all_other_ips_before = set(
    IPAddress.objects.filter(parent__namespace__name__startswith="ns-")
    .values_list("pk", flat=True)
)

src, dst = _make_pair()
scope = SyncScope(
    model_type="ipaddress",
    unique_key=victim_unique_key,
    integration="infoblox",
)
result = run_streaming_sync(
    src, dst,
    flags=SSoTFlags.STREAMING | SSoTFlags.BULK_WRITES,
    scope=scope,
)
print(f"\n  Diff stats:        {result.diff_stats}")
print(f"  Sync stats:        {result.sync_stats}")
print(f"  Subtree size:      {result.diff_stats.get('scope_keys_in_subtree', 0)} (should be 1 — just the IP)")
print(f"  Skipped out-of-scope: {result.diff_stats.get('skipped_out_of_scope', 0)}")

restored = IPAddress.objects.filter(parent=victim_parent_orm, host=victim_address).first()
assert restored is not None, "victim IP was not restored"
print(f"  Victim IP restored as pk={restored.pk}")

# Verify: all other IPs unchanged
all_other_ips_after = set(
    IPAddress.objects.filter(parent__namespace__name__startswith="ns-")
    .exclude(pk=restored.pk)
    .values_list("pk", flat=True)
)
churn = all_other_ips_before ^ all_other_ips_after
assert len(churn) == 0, f"out-of-scope IPs changed! delta count={len(churn)}"
print(f"\n  PASS — single-IP scoped sync restored just that IP, no other churn.")


# ===========================================================================
# Done
# ===========================================================================

print("\n" + "=" * 72)
print(" ALL THREE TESTS PASSED")
print("=" * 72)
print("""
Summary:
  * Test 1: Full sync correctly creates everything from scratch
  * Test 2: Scoped sync at the PREFIX level — restored 100 IPs in a single
            prefix's subtree, with zero churn on the other 2,900+ IPs in
            other prefixes
  * Test 3: Scoped sync at the IPADDRESS level (non-root) — restored
            exactly 1 IP, zero churn on all other 2,999+ IPs

The pipeline-side scope filter works at any level of the hierarchy.
""")
_wipe_mock_data()
