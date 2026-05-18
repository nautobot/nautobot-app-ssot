"""Reusable Pydantic validators for DiffSync models — strictly opt-in.

Mix into a DiffSync model subclass to enable shape validation at instance
construction time (i.e. during `adapter.load()` or any time `cls.create()`
runs). Validators only fire on fields the subclass actually declares, so
applying the mixin to a model that doesn't have e.g. a `vid` field is safe
— `check_fields=False` keeps Pydantic from complaining at class-creation.

Usage
-----
    from nautobot_ssot.utils.diffsync_validators import IPAMShapeValidationMixin

    class StrictInfobloxNetwork(IPAMShapeValidationMixin, InfobloxNetwork):
        '''Same fields, plus shape validators on network/prefix_length.'''

The base integration models are intentionally NOT modified — projects choose
to opt in by inheriting (or by keeping the unvalidated default).
"""

from __future__ import annotations

import ipaddress
import re

from pydantic import field_validator

# ---------------------------------------------------------------------------
# Field-level validators
# ---------------------------------------------------------------------------


def _validate_cidr(value):
    """CIDR-format check. Returns the input unchanged on success."""
    if value is None or value == "":
        return value
    ipaddress.ip_network(value, strict=False)
    return value


def _validate_ip_address(value):
    """IP-address check; accepts an optional /prefixlen suffix and ignores it."""
    if value is None or value == "":
        return value
    head = value.split("/", 1)[0]
    ipaddress.ip_address(head)
    return value


def _validate_prefix_length(value):
    if value is None:
        return value
    if not 0 <= value <= 128:
        raise ValueError(f"prefix_length must be 0..128, got {value!r}")
    return value


def _validate_vid(value):
    if value is None:
        return value
    if not 1 <= value <= 4094:
        raise ValueError(f"vid must be 1..4094, got {value!r}")
    return value


_DNS_NAME_RE = re.compile(
    r"^(?=.{1,253}$)([A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?)(\.[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?)*$"
)


def _validate_dns_name(value):
    if value is None or value == "":
        return value
    if not _DNS_NAME_RE.match(value):
        raise ValueError(f"dns_name {value!r} is not a valid hostname")
    return value


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------


class IPAMShapeValidationMixin:
    """Pydantic validators for IPAM-shaped DiffSync models.

    Apply by listing it FIRST in the bases of your DiffSync model subclass:

        class StrictNetwork(IPAMShapeValidationMixin, Network):
            pass

    Validators are a strict superset of what the unvalidated parent model
    enforces (Pydantic still type-checks fields). Failure raises
    `pydantic.ValidationError` at construction time.

    Validated fields (when present on the subclass):
        * network          — must parse as an IPv4/IPv6 network
        * prefix           — must parse as an IPv4/IPv6 network
        * address          — must parse as an IPv4/IPv6 address
        * prefix_length    — must be in [0, 128]
        * vid              — must be in [1, 4094]
        * dns_name         — must match a permissive DNS hostname pattern
    """

    @field_validator("network", check_fields=False)
    @classmethod
    def _vmix_network(cls, v):
        return _validate_cidr(v)

    @field_validator("prefix", check_fields=False)
    @classmethod
    def _vmix_prefix(cls, v):
        return _validate_cidr(v)

    @field_validator("address", check_fields=False)
    @classmethod
    def _vmix_address(cls, v):
        return _validate_ip_address(v)

    @field_validator("prefix_length", check_fields=False)
    @classmethod
    def _vmix_prefix_length(cls, v):
        return _validate_prefix_length(v)

    @field_validator("vid", check_fields=False)
    @classmethod
    def _vmix_vid(cls, v):
        return _validate_vid(v)

    @field_validator("dns_name", check_fields=False)
    @classmethod
    def _vmix_dns_name(cls, v):
        return _validate_dns_name(v)
