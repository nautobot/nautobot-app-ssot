"""Streaming, SQLite-backed DiffSync diff computation.

Replaces the in-memory Diff tree with row-by-row comparison driven directly
off the SQLite store. Memory footprint is one src row + one dst row + the
recursion stack — independent of total dataset size.

Pipeline
--------
1. dump_adapter(src, store, "source_records") — flatten src.dict() into rows
2. dump_adapter(dst, store, "dest_records")   — same for dst
3. StreamingDiffer(store, src.top_level, model_class_map).diff()
   - walk source_records in (type_order, tree_depth) order
   - look up matching dest by (model_type, unique_key)
   - emit CREATE / UPDATE / no-op into diff_results
   - mark dest as visited
4. After the walk, find unvisited dest rows → DELETE actions

Generic — no per-integration code. The model class map (`{modelname: class}`)
is reachable from the adapter; we only use it to inspect `_children` for
hierarchy traversal.

Note on Infoblox: it doesn't use `_children`; FK relationships are encoded
in `_identifiers`. The streaming differ still works — every model is
top-level and `tree_depth` stays at 0.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

from .sqlite_store import DiffSyncStore, encode

logger = logging.getLogger(__name__)


def _adapter_class_map(adapter) -> Dict[str, Any]:
    """Return {modelname: DiffSyncModel class} from the adapter's class attrs.

    Adapters expose model classes as class attributes named after the modelname
    (e.g. `class InfobloxAdapter: namespace = InfobloxNamespace`).
    """
    out = {}
    for attr in adapter.top_level:
        cls = getattr(type(adapter), attr, None)
        if cls is None:
            continue
        out[cls._modelname] = cls
    return out


def dump_adapter(
    adapter,
    store: DiffSyncStore,
    table: str,
    *,
    orm_resolver=None,
    strict: bool = False,
) -> int:
    """Flatten `adapter.dict()` into rows and bulk-insert into `table`.

    Walks `top_level` (and nested `_children`) so each row carries
    parent_type/parent_key plus tree_depth. Returns total rows inserted.

    Memory note: `adapter.dict()` does materialize a dict of all in-memory
    DiffSync models — that's fine because the caller is expected to release
    the adapter immediately after this returns. The win is that we do NOT
    keep two adapters live concurrently nor build a Diff tree on top of them.

    Hook 2 — opt-in ORM validation
    ------------------------------
    When `orm_resolver` is provided, every row is also validated by building
    a transient ORM instance and running `full_clean(validate_unique=False,
    validate_constraints=False)` on it. This catches Nautobot-level domain
    errors (custom-field schema, model `clean()` rules, value ranges enforced
    by Django validators) WITHOUT any DB round-trip.

    `orm_resolver` must implement
        `to_orm_kwargs(model_type, ids, attrs) -> (OrmClass, kwargs, exclude)`
    (typically the destination adapter, e.g. `BulkNautobotAdapter`).

    `strict=False` (default): validation failures are logged and the row is
    still dumped. `strict=True`: failures raise `pydantic.ValidationError`.
    """
    class_map = _adapter_class_map(adapter)
    type_order = {modelname: idx for idx, modelname in enumerate(adapter.top_level)}

    # Flatten the adapter into rows. We honor _children: a child's
    # parent_type/parent_key are filled from the parent that referenced it.
    rows = []
    seen_keys = set()  # (modelname, unique_key) to avoid duplicates from cycles
    validation_errors: list = []  # Hook 2 errors collected here when strict=False

    snapshot = adapter.dict()  # {modelname: {unique_id: {field: value}}}

    def _validate_row(modelname: str, ids_dict: dict, attrs_dict: dict) -> None:
        """Hook 2: build a transient ORM and run clean_fields(exclude=FKs).

        We deliberately call clean_fields() rather than full_clean() because
        model-level clean() methods (e.g. IPAddress.clean) do queryset lookups
        for FK targets that may not exist yet at dump time. clean_fields()
        runs every per-field validator (custom regexes, choices, number ranges,
        IP/CIDR validators, custom-field schema) — which is what Hook 2 is
        meant to catch — without the relational dependency.

        Relational/uniqueness/check enforcement is left to the database at
        INSERT time.
        """
        if orm_resolver is None:
            return
        resolver = getattr(orm_resolver, "to_orm_kwargs", None)
        if not callable(resolver):
            return
        spec = resolver(modelname, ids_dict, attrs_dict)
        if spec is None:
            return
        OrmCls, orm_kwargs, exclude_fields = spec
        try:
            instance = OrmCls(**orm_kwargs)
            instance.clean_fields(exclude=exclude_fields)
        except Exception as exc:  # noqa: BLE001 — Django ValidationError is fine here
            err = (modelname, ids_dict, str(exc))
            if strict:
                raise
            validation_errors.append(err)
            logger.warning("Hook 2 validation failed: %s ids=%s err=%s", modelname, ids_dict, exc)

    def _walk(modelname: str, unique_id: str, parent_type: Optional[str],
              parent_key: Optional[str], depth: int):
        if (modelname, unique_id) in seen_keys:
            return
        seen_keys.add((modelname, unique_id))
        cls = class_map.get(modelname)
        if cls is None:
            return
        record = snapshot.get(modelname, {}).get(unique_id)
        if record is None:
            return

        ids_dict = {f: record.get(f) for f in cls._identifiers if f in record}
        attrs_dict = {f: record.get(f) for f in cls._attributes if f in record}

        _validate_row(modelname, ids_dict, attrs_dict)

        rows.append(
            (
                modelname,
                unique_id,
                encode(ids_dict),
                encode(attrs_dict),
                parent_type,
                parent_key,
                depth,
                type_order.get(modelname, len(type_order)),
            )
        )

        # Recurse into _children if defined
        for child_modelname, child_field in (cls._children or {}).items():
            child_keys = record.get(child_field) or []
            for child_key in child_keys:
                _walk(child_modelname, child_key, modelname, unique_id, depth + 1)

    for modelname in adapter.top_level:
        for unique_id in snapshot.get(modelname, {}):
            _walk(modelname, unique_id, None, None, 0)

    # Also pick up any rows that exist in snapshot but weren't reached via
    # top_level (rare; a defensive pass for adapters that hold floating models).
    for modelname, by_id in snapshot.items():
        for unique_id in by_id:
            if (modelname, unique_id) in seen_keys:
                continue
            _walk(modelname, unique_id, None, None, 0)

    if validation_errors:
        logger.info(
            "dump_adapter: %d validation error(s) collected during dump (strict=%s)",
            len(validation_errors),
            strict,
        )
    if not rows:
        return 0
    return store.insert_records(table, rows)


class StreamingDiffer:
    """Walks the SQLite source/dest tables and writes CREATE/UPDATE/DELETE rows.

    Does NOT build a DiffSync `Diff` object. Memory peak is one row pair plus
    the small bookkeeping dicts inside this class.
    """

    def __init__(self, store: DiffSyncStore):
        self.store = store
        self.stats = {"create": 0, "update": 0, "delete": 0, "no_op": 0}

    def diff(self) -> Dict[str, int]:
        """Compute the diff. Idempotent — runs only against rows in `store`.

        Returns the {action: count} stats dict.
        """
        # Wrap inserts in a single transaction. SQLite without an explicit
        # transaction commits per-statement; this is the difference between
        # "fast" and "agonizing" on row counts in the 10k+ range.
        with self.store.conn:
            for src_row in self.store.fetch_source_in_order():
                self._process_source(src_row)

            for dst_row in self.store.fetch_unvisited_dest():
                self._emit_delete(dst_row)
        return dict(self.stats)

    # ------------------------------------------------------------------

    def _process_source(self, src_row: tuple) -> None:
        (model_type, unique_key, ids_json, attrs_json,
         _parent_type, _parent_key, tree_depth, type_order) = src_row
        dst_row = self.store.fetch_dest(model_type, unique_key)
        if dst_row is None:
            self.store.insert_diff(
                (model_type, unique_key, "create", ids_json,
                 attrs_json, None, tree_depth, type_order)
            )
            self.stats["create"] += 1
            return

        # Compare attrs; skip if identical.
        dst_attrs_json = dst_row[3]
        if attrs_json == dst_attrs_json:
            self.store.mark_visited(model_type, unique_key)
            self.stats["no_op"] += 1
            return
        self.store.insert_diff(
            (model_type, unique_key, "update", ids_json,
             attrs_json, dst_attrs_json, tree_depth, type_order)
        )
        self.store.mark_visited(model_type, unique_key)
        self.stats["update"] += 1

    def _emit_delete(self, dst_row: tuple) -> None:
        (model_type, unique_key, ids_json, attrs_json,
         _parent_type, _parent_key, tree_depth, type_order) = dst_row
        self.store.insert_diff(
            (model_type, unique_key, "delete", ids_json,
             None, attrs_json, tree_depth, type_order)
        )
        self.stats["delete"] += 1


def run_streaming_diff(src_adapter, dst_adapter, store: DiffSyncStore) -> Dict[str, int]:
    """Convenience: dump both adapters and run the diff. Returns stats."""
    dump_adapter(src_adapter, store, "source_records")
    dump_adapter(dst_adapter, store, "dest_records")
    differ = StreamingDiffer(store)
    return differ.diff()
