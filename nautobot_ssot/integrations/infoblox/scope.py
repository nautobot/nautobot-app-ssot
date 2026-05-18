"""Infoblox-specific subtree expander for scoped sync.

Infoblox doesn't use DiffSync's `_children` metadata — its parent/child
relationships are encoded in `_identifiers` (a child carries enough fields
in its identifier to identify its parent). So the default SQLite walker
(which reads `parent_type` / `parent_key`) returns just the root.

This expander reads identifiers and walks the implicit hierarchy:

    namespace --→ prefix    (child.namespace == parent.name)
              --→ ipaddress
              --→ dnsarecord
              --→ dnshostrecord
              --→ dnsptrrecord
              --→ vlan

    prefix    --→ ipaddress  (child.prefix == parent.network AND child.namespace == parent.namespace)
              --→ dnsarecord
              --→ dnshostrecord
              --→ dnsptrrecord

Models below `ipaddress` (host records etc.) are leaves — no further descent.

Register at app startup via:

    from nautobot_ssot.scope import register_subtree_expander
    from nautobot_ssot.integrations.infoblox.scope import expand_infoblox_subtree
    register_subtree_expander("infoblox", expand_infoblox_subtree)
"""

from __future__ import annotations

import json
from typing import Set, Tuple

from nautobot_ssot.scope import SyncScope, lookup_record_identifiers


# Each entry: parent_model_type → list of (child_model_type, {child_field: parent_field})
# An identifier match on ALL listed fields qualifies the row as a child.
#
# Note on `ipaddress` siblings: in the Infoblox integration, the actual
# Nautobot IPAddress row is created via the `dnsarecord` model (when
# `fixed_address_type=DONT_CREATE_RECORD`, which is the default). The
# `ipaddress`, `dnsarecord`, `dnshostrecord`, and `dnsptrrecord` source
# models share the same `_identifiers` (address, prefix, prefix_length,
# namespace). For scoped sync to do the right thing when a user says
# "resync IP X," all four siblings must be included — otherwise the
# sync runs but no row gets created. We treat them as a logical unit.
_SIBLING_KEYS = {"address": "address", "prefix": "prefix",
                 "prefix_length": "prefix_length", "namespace": "namespace"}

_HIERARCHY = {
    "namespace": [
        ("prefix",        {"namespace": "name"}),
        ("ipaddress",     {"namespace": "name"}),
        ("dnsarecord",    {"namespace": "name"}),
        ("dnshostrecord", {"namespace": "name"}),
        ("dnsptrrecord",  {"namespace": "name"}),
        ("vlan",          {"namespace": "name"}),
    ],
    "prefix": [
        ("ipaddress",     {"prefix": "network", "namespace": "namespace"}),
        ("dnsarecord",    {"prefix": "network", "namespace": "namespace"}),
        ("dnshostrecord", {"prefix": "network", "namespace": "namespace"}),
        ("dnsptrrecord",  {"prefix": "network", "namespace": "namespace"}),
    ],
    "vlangroup": [
        ("vlan", {"vlangroup": "name"}),
    ],
    # Sibling DNS records — same identifiers, but split across model types
    # in the integration's data model. Scope expansion follows the siblings
    # so scoping by any one pulls in the others.
    "ipaddress": [
        ("dnsarecord",    _SIBLING_KEYS),
        ("dnshostrecord", _SIBLING_KEYS),
        ("dnsptrrecord",  _SIBLING_KEYS),
    ],
    "dnsarecord": [
        ("ipaddress",     _SIBLING_KEYS),
        ("dnshostrecord", _SIBLING_KEYS),
        ("dnsptrrecord",  _SIBLING_KEYS),
    ],
    "dnshostrecord": [
        ("ipaddress",     _SIBLING_KEYS),
        ("dnsarecord",    _SIBLING_KEYS),
        ("dnsptrrecord",  _SIBLING_KEYS),
    ],
    "dnsptrrecord": [
        ("ipaddress",     _SIBLING_KEYS),
        ("dnsarecord",    _SIBLING_KEYS),
        ("dnshostrecord", _SIBLING_KEYS),
    ],
    # Leaves with no further descendants: vlan
}


def expand_infoblox_subtree(scope: SyncScope, store) -> Set[Tuple[str, str]]:
    """Walk the Infoblox identifier-encoded hierarchy from `scope` root.

    Returns the set of (model_type, unique_key) pairs in the subtree
    across BOTH source_records and dest_records, so a scoped sync correctly
    handles orphaned dest rows that fall within the subtree.
    """
    keys: Set[Tuple[str, str]] = set()
    if scope.include_root:
        keys.add((scope.model_type, scope.unique_key))

    queue = [(scope.model_type, scope.unique_key)]
    while queue:
        parent_type, parent_key = queue.pop()
        rules = _HIERARCHY.get(parent_type)
        if not rules:
            continue  # leaf model — no descendants

        parent_ids = lookup_record_identifiers(store, parent_type, parent_key)
        if not parent_ids:
            # Parent doesn't exist in either store — can't expand. Caller
            # may still want to process the root row (e.g., dest-only delete).
            continue

        for child_type, field_map in rules:
            # Pull every row of this child type from both stores; filter in Python.
            # SQLite can do this in SQL via json_extract too, but the row counts
            # are bounded by adapter size so keeping it simple is fine.
            for table in ("source_records", "dest_records"):
                cur = store.conn.execute(
                    f"SELECT model_type, unique_key, identifiers FROM {table} "
                    f"WHERE model_type = ?",
                    (child_type,),
                )
                for child_mt, child_uk, child_ids_json in cur:
                    child_ids = json.loads(child_ids_json or "{}")
                    if all(
                        child_ids.get(child_field) == parent_ids.get(parent_field)
                        for child_field, parent_field in field_map.items()
                    ):
                        new_key = (child_mt, child_uk)
                        if new_key not in keys:
                            keys.add(new_key)
                            queue.append(new_key)

    return keys
