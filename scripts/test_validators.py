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

print("\n=== Hook 2: clean_fields() via to_orm_kwargs ===\n")

# Hook 2 uses BulkNautobotAdapter.to_orm_kwargs to build a transient ORM and
# call clean_fields(). Test directly without running the full pipeline.
from nautobot.ipam.choices import IPAddressTypeChoices  # noqa: E402
from nautobot.ipam.models import IPAddress as OrmIPAddress  # noqa: E402
from nautobot.ipam.models import Prefix as OrmPrefix  # noqa: E402
from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: E402


def _clean_ip(addr, ip_type="host"):
    inst = OrmIPAddress(address=addr, type=ip_type, dns_name="", description="")
    inst.clean_fields(exclude=["parent", "status"])


def _clean_prefix(prefix):
    inst = OrmPrefix(prefix=prefix, type="network", description="")
    inst.clean_fields(exclude=["namespace", "status"])


case("OrmIPAddress.clean_fields rejects malformed address '10.0.0.999/24'",
     lambda: _clean_ip("10.0.0.999/24"))

case("OrmIPAddress.clean_fields rejects type='banana'",
     lambda: _clean_ip("10.0.0.1/24", ip_type="banana"))

case_ok("OrmIPAddress.clean_fields accepts '10.0.0.1/24', type='host'",
        lambda: _clean_ip("10.0.0.1/24"))

case("OrmPrefix.clean_fields rejects 'garbage'",
     lambda: _clean_prefix("garbage"))

case_ok("OrmPrefix.clean_fields accepts '10.0.0.0/24'",
        lambda: _clean_prefix("10.0.0.0/24"))

print()
