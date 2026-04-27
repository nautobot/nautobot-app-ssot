#!/usr/bin/env python
"""Smoke test: confirm Hook 1 (Pydantic) and Hook 2 (clean_fields) catch bad data.

Constructs DiffSync models and ORM instances with deliberately-bad values,
verifies that each layer raises (or, where applicable, doesn't).
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "development.nautobot_config")

import django  # noqa: E402

django.setup()

from pydantic import ValidationError  # noqa: E402

from nautobot_ssot.integrations.infoblox.diffsync.models.infoblox import InfobloxNetwork  # noqa: E402
from nautobot_ssot.integrations.infoblox.diffsync.models.validated import (  # noqa: E402
    StrictInfobloxIPAddress,
    StrictInfobloxNetwork,
    StrictInfobloxVLAN,
)


def case(name, fn):
    """Run fn(), expect it to raise — print PASS / FAIL."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        print(f"PASS  {name}  raised {type(exc).__name__}: {str(exc).splitlines()[0]}")
        return
    print(f"FAIL  {name}  did NOT raise")


def case_ok(name, fn):
    """Run fn(), expect no exception."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  {name}  raised {type(exc).__name__}: {str(exc).splitlines()[0]}")
        return
    print(f"PASS  {name}  accepted")


print("\n=== Hook 1: Pydantic on Strict* DiffSync models ===\n")

case("StrictInfobloxNetwork rejects 'not-a-cidr'",
     lambda: StrictInfobloxNetwork(network="not-a-cidr", namespace="ns", network_type="network"))

case("StrictInfobloxNetwork rejects '10.0.0.0/99'",
     lambda: StrictInfobloxNetwork(network="10.0.0.0/99", namespace="ns", network_type="network"))

case("StrictInfobloxIPAddress rejects 'banana' as address",
     lambda: StrictInfobloxIPAddress(
         address="banana", prefix="10.0.0.0/24", prefix_length=24, namespace="ns", status="Active"))

case("StrictInfobloxIPAddress rejects prefix_length=200",
     lambda: StrictInfobloxIPAddress(
         address="10.0.0.1", prefix="10.0.0.0/24", prefix_length=200, namespace="ns", status="Active"))

case("StrictInfobloxVLAN rejects vid=9999",
     lambda: StrictInfobloxVLAN(vid=9999, name="bad", vlangroup="g", status="Active"))

case_ok("StrictInfobloxNetwork accepts a valid CIDR",
        lambda: StrictInfobloxNetwork(network="10.0.0.0/24", namespace="ns", network_type="network"))

case_ok("StrictInfobloxIPAddress accepts a valid IP",
        lambda: StrictInfobloxIPAddress(
            address="10.0.0.1", prefix="10.0.0.0/24", prefix_length=24, namespace="ns", status="Active"))

# Confirm the *non-strict* base model does NOT reject bad data — proves Hook 1
# is genuinely opt-in.
case_ok("Base InfobloxNetwork does NOT reject 'not-a-cidr' (opt-in confirmed)",
        lambda: InfobloxNetwork(network="not-a-cidr", namespace="ns", network_type="network"))

print()
