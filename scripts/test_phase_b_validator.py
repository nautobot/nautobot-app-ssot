#!/usr/bin/env python
"""Verify IPInPrefixValidator catches a deliberately misrouted IP.

Builds a tiny in-memory pipeline state where one queued IP claims a parent
prefix it doesn't fit into, then runs the validator and inspects the issue
list.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

import uuid  # noqa: E402

from django.contrib.contenttypes.models import ContentType  # noqa: E402
from nautobot.extras.models import Status  # noqa: E402
from nautobot.ipam.choices import IPAddressTypeChoices  # noqa: E402
from nautobot.ipam.models import IPAddress as OrmIPAddress  # noqa: E402
from nautobot.ipam.models import Namespace as OrmNamespace  # noqa: E402
from nautobot.ipam.models import Prefix as OrmPrefix  # noqa: E402

from nautobot_ssot.utils.validator_registry import (  # noqa: E402
    Phase,
    ValidatorContext,
    ValidatorRegistry,
)
from nautobot_ssot.utils.validators_ipam import IPInPrefixValidator  # noqa: E402


# ---------------------------------------------------------------------------
# Set up minimal DB state — a Namespace and one Prefix the IPs will claim.
# ---------------------------------------------------------------------------

active, _ = Status.objects.get_or_create(name="Active")
for model in [OrmIPAddress, OrmPrefix, OrmNamespace]:
    active.content_types.add(ContentType.objects.get_for_model(model))

OrmIPAddress.objects.filter(parent__namespace__name="ns-validator-test").delete()
OrmPrefix.objects.filter(namespace__name="ns-validator-test").delete()
OrmNamespace.objects.filter(name="ns-validator-test").delete()

ns = OrmNamespace.objects.create(name="ns-validator-test")
prefix = OrmPrefix.objects.create(
    prefix="10.0.0.0/24", namespace=ns, type="network", status=active
)

# ---------------------------------------------------------------------------
# Two queued IPs: one fits (10.0.0.5/32), one doesn't (192.168.99.1/32).
# Both claim the same parent prefix.
# ---------------------------------------------------------------------------

good_ip = OrmIPAddress(
    address="10.0.0.5/32",
    type=IPAddressTypeChoices.TYPE_HOST,
    status=active,
    parent_id=prefix.pk,
)
bad_ip = OrmIPAddress(
    address="192.168.99.1/32",
    type=IPAddressTypeChoices.TYPE_HOST,
    status=active,
    parent_id=prefix.pk,
)
orphan_ip = OrmIPAddress(
    address="172.16.0.1/32",
    type=IPAddressTypeChoices.TYPE_HOST,
    status=active,
    parent_id=None,
)

# ---------------------------------------------------------------------------
# Run the validator directly via the registry.
# ---------------------------------------------------------------------------

registry = ValidatorRegistry([IPInPrefixValidator()])
ctx = ValidatorContext(
    pending_queues={OrmIPAddress: [good_ip, bad_ip, orphan_ip]},
)
issues = registry.run_phase(Phase.B, ctx)
# Phase B's "before flush" form is what the BulkSyncer uses; both invocations
# work — for a Phase-B-only validator, run_phase(B) is fine.
issues_via_before = registry.run_before_flush(OrmIPAddress, ctx)

print(f"\nrun_phase(Phase.B):       {len(issues)} issue(s)")
print(f"run_before_flush(IPAddr): {len(issues_via_before)} issue(s)\n")

for i, issue in enumerate(issues, 1):
    print(f"  {i}. {issue.validator}: {issue.model_type} {issue.key} — {issue.detail}")

# Cleanup
OrmPrefix.objects.filter(namespace=ns).delete()
ns.delete()

assert len(issues) == 2, f"expected 2 issues (bad_ip + orphan_ip), got {len(issues)}"
assert any("192.168.99.1" in i.key for i in issues), "missing 192.168.99.1 issue"
assert any("172.16.0.1" in i.key for i in issues), "missing orphan 172.16.0.1 issue"
print("\nALL CHECKS PASSED")
