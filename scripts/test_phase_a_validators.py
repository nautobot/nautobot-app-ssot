#!/usr/bin/env python
"""Verify Phase A validators (Category 3 + Category 4) catch bad data.

Builds a SQLite store with deliberately broken source data and runs each
Phase A validator against it. No DB writes — the validators operate
entirely on the SQLite snapshot.
"""

import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

from nautobot_ssot.utils.sqlite_store import DiffSyncStore  # noqa: E402
from nautobot_ssot.utils.validator_registry import (  # noqa: E402
    Phase,
    ValidatorContext,
    ValidatorRegistry,
)
from nautobot_ssot.utils.validators_ipam import (  # noqa: E402
    IPAddressContainmentValidator,
    VlanVidUniqueValidator,
)


def _insert(store, table, rows):
    """rows: list of (model_type, unique_key, identifiers_dict, attrs_dict)."""
    payloads = [
        (mt, uk, json.dumps(ids), json.dumps(attrs), None, None, 0, 0)
        for mt, uk, ids, attrs in rows
    ]
    store.insert_records(table, payloads)


# ---------------------------------------------------------------------------
# Test 1: IPAddressContainmentValidator
# ---------------------------------------------------------------------------
print("\n=== Test 1: IPAddressContainmentValidator ===\n")

store = DiffSyncStore(path=":memory:")

_insert(
    store,
    "source_records",
    [
        ("prefix", "10.0.0.0/24__ns-a", {"network": "10.0.0.0/24", "namespace": "ns-a"}, {}),
        ("prefix", "10.1.0.0/24__ns-b", {"network": "10.1.0.0/24", "namespace": "ns-b"}, {}),
        # Good: 10.0.0.5 is inside 10.0.0.0/24 in ns-a
        ("ipaddress", "10.0.0.5__ns-a", {"address": "10.0.0.5", "namespace": "ns-a"}, {}),
        # Bad: 192.168.1.1 has no containing prefix in ns-a
        ("ipaddress", "192.168.1.1__ns-a", {"address": "192.168.1.1", "namespace": "ns-a"}, {}),
        # Bad: 10.0.0.5 in ns-c — namespace has no prefixes at all
        ("dnsarecord", "10.0.0.5__ns-c", {"address": "10.0.0.5", "namespace": "ns-c"}, {}),
        # Good: 10.1.0.50 is inside 10.1.0.0/24 in ns-b
        ("dnsptrrecord", "10.1.0.50__ns-b", {"address": "10.1.0.50", "namespace": "ns-b"}, {}),
    ],
)

# Add a dest-side prefix that should also be visible to the validator
_insert(
    store,
    "dest_records",
    [
        ("prefix", "172.16.0.0/16__ns-c", {"network": "172.16.0.0/16", "namespace": "ns-c"}, {}),
    ],
)

# 10.0.0.5 in ns-c is still bad — 172.16.0.0/16 doesn't contain it. But add
# another row to verify dest containment is honored:
_insert(
    store,
    "source_records",
    [
        ("ipaddress", "172.16.5.5__ns-c", {"address": "172.16.5.5", "namespace": "ns-c"}, {}),
    ],
)

ctx = ValidatorContext(store=store)
issues = ValidatorRegistry([IPAddressContainmentValidator()]).run_phase(Phase.A, ctx)
print(f"Found {len(issues)} issues:")
for i, iss in enumerate(issues, 1):
    print(f"  {i}. {iss.model_type} {iss.key} — {iss.detail}")

assert len(issues) == 2, f"expected 2 (192.168.1.1 + 10.0.0.5__ns-c); got {len(issues)}"
keys = {i.key for i in issues}
assert "192.168.1.1__ns-a" in keys, "missing 192.168.1.1 (no containing prefix)"
assert "10.0.0.5__ns-c" in keys, "missing 10.0.0.5 in empty namespace"
store.close()
print("PASS\n")

# ---------------------------------------------------------------------------
# Test 2: VlanVidUniqueValidator
# ---------------------------------------------------------------------------
print("=== Test 2: VlanVidUniqueValidator ===\n")

store = DiffSyncStore(path=":memory:")

_insert(
    store,
    "source_records",
    [
        # Good — different VIDs in same group
        ("vlan", "100__site-a", {"vid": 100, "vlangroup": "site-a", "name": "vlan_a"}, {}),
        ("vlan", "200__site-a", {"vid": 200, "vlangroup": "site-a", "name": "vlan_b"}, {}),
        # Good — same VID in different groups (allowed)
        ("vlan", "100__site-b", {"vid": 100, "vlangroup": "site-b", "name": "vlan_c"}, {}),
        # BAD — duplicate (vid=300, vlangroup=site-a)
        ("vlan", "300__site-a__one", {"vid": 300, "vlangroup": "site-a", "name": "vlan_d"}, {}),
        ("vlan", "300__site-a__two", {"vid": 300, "vlangroup": "site-a", "name": "vlan_e"}, {}),
    ],
)

ctx = ValidatorContext(store=store)
issues = ValidatorRegistry([VlanVidUniqueValidator()]).run_phase(Phase.A, ctx)
print(f"Found {len(issues)} issues:")
for i, iss in enumerate(issues, 1):
    print(f"  {i}. {iss.model_type} {iss.key} — {iss.detail}")

assert len(issues) == 2, f"expected 2 (both rows of vid=300); got {len(issues)}"
keys = {i.key for i in issues}
assert "300__site-a__one" in keys
assert "300__site-a__two" in keys
store.close()
print("PASS\n")

print("ALL CHECKS PASSED")
