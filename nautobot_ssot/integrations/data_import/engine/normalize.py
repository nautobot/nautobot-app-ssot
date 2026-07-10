"""Normalization: flatten raw records into flat tables and derive child tables.

Every source (API or CSV) is reduced to tables of rows × columns. Nested
dicts become dot-path columns; nested lists of dicts are left intact so a
``tables`` entry with ``expand`` can derive a child table from them.
"""

from typing import Any, Dict, List

# Reserved column injected on expanded child tables, carrying the parent
# row's identifier value.
PARENT_KEY_COLUMN = "_parent_key"

MAX_FLATTEN_DEPTH = 3


def flatten_record(record: Dict, max_depth: int = MAX_FLATTEN_DEPTH) -> Dict[str, Any]:
    """Flatten nested dicts into dot-path keys.

    - ``{"a": {"b": 1}}`` → ``{"a.b": 1}``
    - Lists of dicts are preserved under their key (for later expansion).
    - Lists of scalars are preserved as-is (loader may join them).
    """
    flat: Dict[str, Any] = {}

    def _walk(obj: Dict, prefix: str, depth: int):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict) and depth < max_depth:
                _walk(value, path, depth + 1)
            else:
                flat[path] = value

    if isinstance(record, dict):
        _walk(record, "", 0)
    return flat


def list_of_dict_columns(rows: List[Dict]) -> List[str]:
    """Return column names whose values are lists of dicts (expandable arrays)."""
    columns = set()
    for row in rows[:20]:
        for key, value in row.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                columns.add(key)
    return sorted(columns)


def build_tables(
    document: Dict,
    raw_records_by_source: Dict[str, List[Dict]],
    logger=None,
) -> Dict[str, List[Dict]]:
    """Build all flat tables declared in the document.

    Root tables flatten the source records directly. Expanded tables iterate
    parent rows, emit one row per element of the named array column, and
    inject ``_parent_key`` with the parent's identifier value.
    """
    tables: Dict[str, List[Dict]] = {}
    table_cfgs = {t["id"]: t for t in document.get("tables", [])}

    # Identifier column per table (used to stamp _parent_key on children):
    # the first identifier column of the output that consumes the table.
    ident_col_by_table: Dict[str, str] = {}
    for output in document.get("outputs", []):
        identifiers = output.get("identifiers") or {}
        for spec in identifiers.values():
            if isinstance(spec, dict) and spec.get("column"):
                ident_col_by_table.setdefault(output["table"], spec["column"])
                break

    # Pass 1: root tables.
    for cfg in document.get("tables", []):
        if cfg.get("expand"):
            continue
        records = raw_records_by_source.get(cfg.get("from"), [])
        tables[cfg["id"]] = [flatten_record(rec) for rec in records]

    # Pass 2: expanded child tables (parents are all root in MVP).
    for cfg in document.get("tables", []):
        expand_col = cfg.get("expand")
        if not expand_col:
            continue
        parent_id = cfg.get("parent")
        parent_cfg = table_cfgs.get(parent_id)
        if not parent_cfg:
            if logger:
                logger.warning("Table %s: parent table %s not found; skipping.", cfg["id"], parent_id)
            tables[cfg["id"]] = []
            continue

        parent_rows = tables.get(parent_id, [])
        ident_col = ident_col_by_table.get(parent_id)
        child_rows: List[Dict] = []
        for parent_row in parent_rows:
            array_value = parent_row.get(expand_col)
            if not isinstance(array_value, list):
                continue
            parent_key = parent_row.get(ident_col) if ident_col else None
            for element in array_value:
                if not isinstance(element, dict):
                    continue
                child_row = flatten_record(element)
                child_row[PARENT_KEY_COLUMN] = parent_key
                child_rows.append(child_row)
        tables[cfg["id"]] = child_rows

    return tables


def table_preview(rows: List[Dict], max_rows: int = 50) -> Dict[str, Any]:
    """Summarize a table for caching/UI: column list + capped sample rows."""
    columns: List[str] = []
    seen = set()
    for row in rows[:200]:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)

    def _display(value):
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                return f"[{len(value)} nested records]"
            return ", ".join(str(v) for v in value[:5])
        if isinstance(value, dict):
            return "{…}"
        return value

    sample = [{col: _display(row.get(col)) for col in columns} for row in rows[:max_rows]]
    return {
        "columns": columns,
        "rows": sample,
        "row_count": len(rows),
        "expandable_columns": list_of_dict_columns(rows),
    }
