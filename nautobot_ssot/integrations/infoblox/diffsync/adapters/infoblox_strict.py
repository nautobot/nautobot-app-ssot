"""Drop-in InfobloxAdapter that uses the strict (validated) source models.

Identical to `InfobloxAdapter` except every model class attribute points to
its `Strict*` variant. This means every `MyModel(...)` instantiation that
happens during `load_*()` runs Pydantic shape validators — bad CIDRs, bad
VIDs, malformed DNS names raise immediately rather than slipping into the
SQLite store and failing later at INSERT time.

Use this when you want fail-fast input validation on the source side.
"""

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.models.validated import (
    StrictInfobloxDnsARecord,
    StrictInfobloxDnsHostRecord,
    StrictInfobloxDnsPTRRecord,
    StrictInfobloxIPAddress,
    StrictInfobloxNamespace,
    StrictInfobloxNetwork,
    StrictInfobloxVLAN,
    StrictInfobloxVLANView,
)


class StrictInfobloxAdapter(InfobloxAdapter):
    """InfobloxAdapter wired to use validated DiffSync models on the source side."""

    namespace = StrictInfobloxNamespace
    prefix = StrictInfobloxNetwork
    ipaddress = StrictInfobloxIPAddress
    vlangroup = StrictInfobloxVLANView
    vlan = StrictInfobloxVLAN
    dnshostrecord = StrictInfobloxDnsHostRecord
    dnsarecord = StrictInfobloxDnsARecord
    dnsptrrecord = StrictInfobloxDnsPTRRecord
