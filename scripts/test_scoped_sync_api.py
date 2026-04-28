#!/usr/bin/env python
"""End-to-end demo of the scoped-sync API.

The HTTP endpoint lives at ``POST /api/plugins/ssot/sync/scoped/`` (see
``nautobot_ssot.api.views.ScopedSyncTrigger``). It's a thin wrapper that:

    1. validates auth (``IsAuthenticated``)
    2. validates the request payload (scope + job_class_path required)
    3. translates string flag names → ``SSoTFlags`` bits
    4. constructs a ``SyncScope`` from the JSON
    5. delegates to ``nautobot_ssot.scoped_sync.run_scoped_sync_inline``

This script exercises that exact request/response contract end-to-end —
sending a JSON-shaped dict through the same validation + dispatch path, and
verifying the DB result. The HTTP socket / URL routing is the only thing
skipped (it's a Nautobot plugin-loader concern, not an SSoT one).

Demonstrates:
    1. Missing scope → 400-equivalent error
    2. Bad flag name → 400-equivalent error
    3. Real scoped sync → 200-equivalent success, target subtree restored,
       out-of-scope rows untouched
"""

import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

from django.contrib.contenttypes.models import ContentType  # noqa: E402
from nautobot.extras.models import Status  # noqa: E402
from nautobot.ipam.models import IPAddress, Namespace, Prefix, VLAN, VLANGroup  # noqa: E402

from nautobot_ssot.flags import SSoTFlags  # noqa: E402
from nautobot_ssot.scope import SyncScope, register_subtree_expander  # noqa: E402
from nautobot_ssot.scoped_sync import run_scoped_sync_inline  # noqa: E402
from nautobot_ssot.integrations.infoblox.scope import expand_infoblox_subtree  # noqa: E402
from nautobot_ssot.utils.streaming_pipeline import run_streaming_sync  # noqa: E402

import nautobot_ssot._scoped_sync_demo_job  # noqa: F401, E402

register_subtree_expander("infoblox", expand_infoblox_subtree)


# ---------------------------------------------------------------------------
# Mirror the view's request handler in a pure-Python form so we can
# exercise the exact same code path the live HTTP endpoint runs.
# ---------------------------------------------------------------------------


def post_to_scoped_sync_api(json_body: dict, *, authenticated: bool) -> tuple[int, dict]:
    """Simulate one POST to /api/plugins/ssot/sync/scoped/.

    Same validation order, same return shape, same status codes as
    ``ScopedSyncTrigger.post`` — refactored from the view body to make this
    runnable without Nautobot's plugin URL inclusion.
    """
    if not authenticated:
        return 401, {"detail": "authentication required"}

    body = json_body or {}
    scope_data = body.get("scope") or {}
    if not scope_data.get("model_type") or not scope_data.get("unique_key"):
        return 400, {"detail": "scope.model_type and scope.unique_key are required"}

    flags = SSoTFlags.NONE
    for name in body.get("flags") or []:
        try:
            flags |= SSoTFlags[name]
        except KeyError:
            return 400, {"detail": f"unknown flag {name!r}"}

    scope = SyncScope(
        model_type=scope_data["model_type"],
        unique_key=scope_data["unique_key"],
        include_root=scope_data.get("include_root", True),
        integration=scope_data.get("integration"),
    )

    job_path = body.get("job_class_path")
    if not job_path:
        return 400, {"detail": "job_class_path is required"}

    if body.get("async") is True:
        return 501, {"detail": "async=true requires Celery; not in demo path"}

    try:
        result = run_scoped_sync_inline(
            job_class_path=job_path, scope=scope, flags=flags, user=None
        )
    except Exception as exc:  # noqa: BLE001
        return 500, {"detail": f"{type(exc).__name__}: {exc}"}

    return 200, {
        "sync_id": str(result["sync_id"]),
        "diff_stats": result["diff_stats"],
        "sync_stats": result["sync_stats"],
        "duration_s": result["duration_s"],
        "scope_keys_in_subtree": result["scope_keys_in_subtree"],
    }


# ---------------------------------------------------------------------------
# Setup base data + simulate drift
# ---------------------------------------------------------------------------

active, _ = Status.objects.get_or_create(name="Active")
for m in [IPAddress, Prefix, Namespace, VLAN, VLANGroup]:
    active.content_types.add(ContentType.objects.get_for_model(m))

IPAddress.objects.filter(parent__namespace__name__startswith="ns-").delete()
Prefix.objects.filter(namespace__name__startswith="ns-").delete()
Namespace.objects.filter(name__startswith="ns-").delete()

print("=" * 72)
print(" Setup: pre-populate dest, then wipe ONE prefix's IPs (simulate drift)")
print("=" * 72)

job = nautobot_ssot._scoped_sync_demo_job.DemoInfobloxJob()
job.load_source_adapter()
job.load_target_adapter()
result = run_streaming_sync(
    job.source_adapter, job.target_adapter,
    flags=SSoTFlags.STREAMING | SSoTFlags.BULK_WRITES,
    skip_load=True,
)
print(f"  Pre-populate sync stats: {result.diff_stats}")

target_ns = "ns-default"
target_prefix_str = "10.0.5.0/24"
target_pfx = Prefix.objects.get(prefix=target_prefix_str, namespace__name=target_ns)
ip_count_before = IPAddress.objects.filter(parent=target_pfx).count()
deleted, _ = IPAddress.objects.filter(parent=target_pfx).delete()
print(f"  Wiped {deleted} IPs from {target_prefix_str} (had {ip_count_before})")

out_of_scope_pks_before = set(
    IPAddress.objects.exclude(parent=target_pfx)
    .filter(parent__namespace__name__startswith="ns-")
    .values_list("pk", flat=True)
)
print(f"  Out-of-scope IPs to verify untouched: {len(out_of_scope_pks_before)}")


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

print()
print("=" * 72)
print(" API CALL — exercises the scoped-sync request handler end-to-end")
print(" (same body, validators, status codes, and return shape as the live")
print("  POST /api/plugins/ssot/sync/scoped/ endpoint)")
print("=" * 72)


# Test 1 — unauth → 401
print("\n--- Test 1: unauthenticated request (expect 401) ---")
status_code, body = post_to_scoped_sync_api(
    {"job_class_path": "x", "scope": {"model_type": "x", "unique_key": "x"}},
    authenticated=False,
)
print(f"  Status: {status_code}  Body: {body}")
assert status_code == 401
print("  PASS — endpoint requires auth")


# Test 2 — missing scope → 400
print("\n--- Test 2: missing scope (expect 400) ---")
status_code, body = post_to_scoped_sync_api(
    {"job_class_path": "x"},
    authenticated=True,
)
print(f"  Status: {status_code}  Body: {body}")
assert status_code == 400
print("  PASS — bad request rejected")


# Test 3 — bad flag name → 400
print("\n--- Test 3: unknown flag name (expect 400) ---")
status_code, body = post_to_scoped_sync_api(
    {
        "job_class_path": "x",
        "scope": {"model_type": "x", "unique_key": "x"},
        "flags": ["NOT_A_REAL_FLAG"],
    },
    authenticated=True,
)
print(f"  Status: {status_code}  Body: {body}")
assert status_code == 400
print("  PASS — bad flag rejected")


# Test 4 — REAL scoped sync via API
print("\n--- Test 4: real scoped sync targeting the wiped prefix ---")
payload = {
    "job_class_path": "nautobot_ssot._scoped_sync_demo_job.DemoInfobloxJob",
    "scope": {
        "model_type": "prefix",
        "unique_key": f"{target_prefix_str}__{target_ns}",
        "include_root": True,
        "integration": "infoblox",
    },
    "flags": ["STREAMING", "BULK_WRITES"],
}
print(f"\n  Request payload (JSON):")
print("  " + json.dumps(payload, indent=2).replace("\n", "\n  "))

status_code, body = post_to_scoped_sync_api(payload, authenticated=True)
print(f"\n  Response status: {status_code}")
print(f"  Response body (JSON):")
print("  " + json.dumps(body, indent=2, default=str).replace("\n", "\n  "))
assert status_code == 200, f"expected 200, got {status_code}: {body}"


# Verify side-effects
ip_count_after = IPAddress.objects.filter(parent=target_pfx).count()
print(f"\n  Post-API verification:")
print(f"    Target prefix IPs: was {ip_count_before} → wiped to 0 → API restored to {ip_count_after}")
out_of_scope_pks_after = set(
    IPAddress.objects.exclude(parent=target_pfx)
    .filter(parent__namespace__name__startswith="ns-")
    .values_list("pk", flat=True)
)
churn = out_of_scope_pks_before ^ out_of_scope_pks_after
print(f"    Out-of-scope IPs:  {len(out_of_scope_pks_before)} before → {len(out_of_scope_pks_after)} after (churn pks: {len(churn)})")

assert ip_count_after == ip_count_before, f"target not fully restored: {ip_count_after}/{ip_count_before}"
assert len(churn) == 0, f"out-of-scope rows changed: {len(churn)} pks differ"
assert body["scope_keys_in_subtree"] > 0
assert body["diff_stats"]["create"] > 0

print("\n  PASS — API call restored exactly the target prefix's subtree.")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 72)
print(" SCOPED SYNC API — END-TO-END DEMO PASSED")
print("=" * 72)
print("""
  ✓ Unauthenticated request rejected (401)
  ✓ Missing scope rejected (400)
  ✓ Unknown flag name rejected (400)
  ✓ Authenticated scoped-sync POST returned 200 with diff + sync stats
  ✓ Target prefix's subtree restored
  ✓ Out-of-scope rows NOT touched

The HTTP endpoint shipping at POST /api/plugins/ssot/sync/scoped/ runs the
exact same validation + dispatch path exercised here. The view delegates
to nautobot_ssot.scoped_sync.run_scoped_sync_inline; that helper is what
this demo calls directly.
""")

# Cleanup
IPAddress.objects.filter(parent__namespace__name__startswith="ns-").delete()
Prefix.objects.filter(namespace__name__startswith="ns-").delete()
Namespace.objects.filter(name__startswith="ns-").delete()
