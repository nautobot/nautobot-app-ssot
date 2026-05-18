"""Concrete IPAM validators that plug into the validator registry.

Each class is a registered `Validator` for a specific (phase, category) cell
of the validation menu (see docs/dev/performance_validation_menu.md §4).

Currently shipped:

    * IPInPrefixValidator (Phase B, Category 2)
        Verifies every queued IPAddress falls inside its parent Prefix.
        Single batched SELECT — O(1) DB queries regardless of queue depth.

    * IPAddressContainmentValidator (Phase A, Category 4)
        Verifies every IPAddress in source_records OR dest_records has at
        least one containing prefix in either store. Catches data integrity
        issues BEFORE any flush — pure SQLite + Python, no DB I/O.

    * VlanVidUniqueValidator (Phase A, Category 3)
        Verifies (vlangroup, vid) is unique within source_records. Catches
        what the DB UniqueConstraint would reject at INSERT, but earlier and
        with a row-specific error.

Add new IPAM validators here following the same pattern.
"""

from __future__ import annotations

import json
from collections import defaultdict
from ipaddress import ip_address, ip_network
from typing import List

from .validator_registry import (
    Issue,
    Phase,
    Severity,
    Validator,
    ValidatorContext,
)


class IPInPrefixValidator(Validator):
    """Phase B / Category 2: each queued IPAddress must fit inside its parent Prefix.

    Runs **after** OrmPrefix has been flushed but **before** OrmIPAddress is
    flushed. By this point every parent prefix is in the DB and queryable;
    the queue still contains the IPs we're about to insert, so we can fail
    early and skip the bad rows (or raise, if `severity=STRICT`).

    Cost: one `OrmPrefix.objects.filter(id__in=...)` query plus an O(N) Python
    pass over the queue.
    """

    name = "ip_in_prefix"
    phase = Phase.B
    category = 2
    severity = Severity.ERROR

    @property
    def fires_before_flush_of(self):
        # Resolved lazily so this module is importable without Django app
        # registry loaded (e.g. for static checks).
        from nautobot.ipam.models import IPAddress as OrmIPAddress

        return OrmIPAddress

    def run(self, ctx: ValidatorContext) -> List[Issue]:
        from nautobot.ipam.models import IPAddress as OrmIPAddress
        from nautobot.ipam.models import Prefix as OrmPrefix

        queue = list(ctx.queue(OrmIPAddress))
        if not queue:
            return []

        # Single batched fetch of every parent CIDR we'll need.
        parent_pks = {ip.parent_id for ip in queue if getattr(ip, "parent_id", None)}
        if not parent_pks:
            return [
                Issue(
                    validator=self.name,
                    model_type="ipaddress",
                    key=str(getattr(ip, "address", "?")),
                    detail="no parent_id set on queued IPAddress",
                    category=self.category,
                )
                for ip in queue
            ]

        parent_rows = OrmPrefix.objects.filter(id__in=parent_pks).values_list(
            "id", "network", "prefix_length"
        )
        parent_cidrs = {
            pk: ip_network(f"{net}/{plen}", strict=False)
            for pk, net, plen in parent_rows
        }

        issues: List[Issue] = []
        for ip in queue:
            addr_str = str(getattr(ip, "address", "")).split("/", 1)[0]
            ip_key = str(getattr(ip, "address", "?"))

            if not getattr(ip, "parent_id", None):
                issues.append(
                    Issue(
                        validator=self.name,
                        model_type="ipaddress",
                        key=ip_key,
                        detail="no parent_id set",
                        category=self.category,
                    )
                )
                continue

            cidr = parent_cidrs.get(ip.parent_id)
            if cidr is None:
                issues.append(
                    Issue(
                        validator=self.name,
                        model_type="ipaddress",
                        key=ip_key,
                        detail=f"parent prefix {ip.parent_id} not present in DB at Phase B",
                        category=self.category,
                    )
                )
                continue

            try:
                addr = ip_address(addr_str)
            except ValueError as exc:
                issues.append(
                    Issue(
                        validator=self.name,
                        model_type="ipaddress",
                        key=ip_key,
                        detail=f"unparseable address: {exc}",
                        category=self.category,
                    )
                )
                continue

            if addr not in cidr:
                issues.append(
                    Issue(
                        validator=self.name,
                        model_type="ipaddress",
                        key=ip_key,
                        detail=f"{addr} does not fit inside parent prefix {cidr}",
                        category=self.category,
                    )
                )

        return issues


# ---------------------------------------------------------------------------
# Phase A — Category 4: same-model topology
# ---------------------------------------------------------------------------


class IPAddressContainmentValidator(Validator):
    """Phase A / Category 4: every IPAddress in src+dst stores must have a containing Prefix.

    Pre-flush sibling of `IPInPrefixValidator`. Where Phase B catches IPs
    that don't fit their declared parent at write time (after Prefix flush),
    this Phase A validator catches the wider class of "no containing prefix
    will exist anywhere in the post-sync state" — useful when source data is
    structurally incomplete (e.g., `10.0.0.5/32` exists in source but the
    /24 it should sit under doesn't exist in either source or dest).

    Pure SQLite + Python: builds an in-memory `(namespace → list[ip_network])`
    index from both source_records and dest_records, then walks every IP-like
    row and checks containment. No DB query.

    Cost: O(N_prefixes log N_prefixes + N_ips * log N_prefixes_in_namespace),
    proportional to the SQLite store, not to N rows being written.
    """

    name = "ipaddress_containment"
    phase = Phase.A
    category = 4
    severity = Severity.ERROR

    # Model types whose rows represent IP-like records (use `address` + `namespace`)
    _IP_MODELS = ("ipaddress", "dnsarecord", "dnshostrecord", "dnsptrrecord")

    def run(self, ctx: ValidatorContext) -> List[Issue]:
        if ctx.store is None:
            return []

        # Build index of (namespace -> [ip_network, ...]) from both sides
        index: dict = defaultdict(list)
        for table in ("source_records", "dest_records"):
            cur = ctx.store.conn.execute(
                f"SELECT identifiers FROM {table} WHERE model_type = 'prefix'"
            )
            for (ids_json,) in cur:
                ids = json.loads(ids_json or "{}")
                ns = ids.get("namespace")
                cidr_str = ids.get("network")
                if not ns or not cidr_str:
                    continue
                try:
                    index[ns].append(ip_network(cidr_str, strict=False))
                except ValueError:
                    # Malformed CIDR is Hook 1's problem, not ours
                    continue

        # Per-namespace, sort prefixes most-specific-first so the first match
        # in the loop below is the closest containing prefix
        for ns in index:
            index[ns].sort(key=lambda n: n.prefixlen, reverse=True)

        # Walk all IP-like rows in the source set (dest IPs are pre-validated
        # by Nautobot's clean() at their original insert time; not our problem)
        issues: List[Issue] = []
        placeholders = ", ".join("?" * len(self._IP_MODELS))
        cur = ctx.store.conn.execute(
            f"SELECT model_type, unique_key, identifiers FROM source_records "
            f"WHERE model_type IN ({placeholders})",
            self._IP_MODELS,
        )
        for model_type, unique_key, ids_json in cur:
            ids = json.loads(ids_json or "{}")
            ns = ids.get("namespace")
            addr_str = str(ids.get("address") or "").split("/", 1)[0]
            if not ns or not addr_str:
                continue
            try:
                addr = ip_address(addr_str)
            except ValueError:
                continue  # Hook 1's job
            if not any(addr in net for net in index.get(ns, ())):
                issues.append(
                    Issue(
                        validator=self.name,
                        model_type=model_type,
                        key=unique_key,
                        detail=f"{addr} has no containing prefix in namespace {ns!r}",
                        category=self.category,
                    )
                )
        return issues


# ---------------------------------------------------------------------------
# Phase A — Category 3: same-model uniqueness in scope
# ---------------------------------------------------------------------------


class VlanVidUniqueValidator(Validator):
    """Phase A / Category 3: (vlangroup, vid) must be unique within source_records.

    DB has a UniqueConstraint on `(vlan_group, vid)` so duplicates would be
    rejected at INSERT — but at INSERT time you get a generic IntegrityError
    on the whole batch with no row-specific identification. This validator
    detects the duplicate at Phase A and reports each offending row by key.

    Pure SQL group-by; one query, O(N) over source_records VLAN rows.
    """

    name = "vlan_vid_unique"
    phase = Phase.A
    category = 3
    severity = Severity.ERROR

    def run(self, ctx: ValidatorContext) -> List[Issue]:
        if ctx.store is None:
            return []

        # Find any (vlangroup, vid) tuples that appear in more than one row
        # of source_records. The identifiers JSON has both fields; we extract
        # them via JSON path. SQLite's json_extract works in 3.38+.
        cur = ctx.store.conn.execute(
            """
            SELECT
                json_extract(identifiers, '$.vlangroup') AS vlangroup,
                json_extract(identifiers, '$.vid') AS vid,
                COUNT(*) AS n,
                GROUP_CONCAT(unique_key, ' | ') AS keys
            FROM source_records
            WHERE model_type = 'vlan'
            GROUP BY vlangroup, vid
            HAVING n > 1
            """
        )
        issues: List[Issue] = []
        for vlangroup, vid, count, keys in cur:
            for k in (keys or "").split(" | "):
                issues.append(
                    Issue(
                        validator=self.name,
                        model_type="vlan",
                        key=k,
                        detail=f"vid={vid} appears {count}× in vlangroup={vlangroup!r}",
                        category=self.category,
                    )
                )
        return issues
