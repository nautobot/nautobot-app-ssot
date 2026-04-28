"""Strict variants of the Infoblox source-side DiffSync models — opt-in.

Applies `IPAMShapeValidationMixin` to each Infoblox model so that
construction-time Pydantic validation enforces:
    * network / prefix          — must be a valid CIDR
    * address                   — must be a valid IP address
    * prefix_length             — must be 0..128
    * vid                       — must be 1..4094
    * dns_name                  — must be a permissive DNS hostname

These are drop-in replacements: same `_modelname`, same `_identifiers`, same
`_attributes`. Use `StrictInfobloxAdapter` (or wire the strict classes onto
your own adapter) to enable them. The base unvalidated models remain
unchanged so existing integrations are unaffected.
"""

from nautobot_ssot.integrations.infoblox.diffsync.models.infoblox import (
    InfobloxDnsARecord,
    InfobloxDnsHostRecord,
    InfobloxDnsPTRRecord,
    InfobloxIPAddress,
    InfobloxNamespace,
    InfobloxNetwork,
    InfobloxVLAN,
    InfobloxVLANView,
)
from nautobot_ssot.utils.diffsync_validators import IPAMShapeValidationMixin


class StrictInfobloxNamespace(IPAMShapeValidationMixin, InfobloxNamespace):
    """InfobloxNamespace with shape validators."""


class StrictInfobloxNetwork(IPAMShapeValidationMixin, InfobloxNetwork):
    """InfobloxNetwork with shape validators."""


class StrictInfobloxVLANView(IPAMShapeValidationMixin, InfobloxVLANView):
    """InfobloxVLANView with shape validators."""


class StrictInfobloxVLAN(IPAMShapeValidationMixin, InfobloxVLAN):
    """InfobloxVLAN with shape validators (notably vid range check)."""


class StrictInfobloxIPAddress(IPAMShapeValidationMixin, InfobloxIPAddress):
    """InfobloxIPAddress with shape validators."""


class StrictInfobloxDnsARecord(IPAMShapeValidationMixin, InfobloxDnsARecord):
    """InfobloxDnsARecord with shape validators."""


class StrictInfobloxDnsHostRecord(IPAMShapeValidationMixin, InfobloxDnsHostRecord):
    """InfobloxDnsHostRecord with shape validators."""


class StrictInfobloxDnsPTRRecord(IPAMShapeValidationMixin, InfobloxDnsPTRRecord):
    """InfobloxDnsPTRRecord with shape validators."""
