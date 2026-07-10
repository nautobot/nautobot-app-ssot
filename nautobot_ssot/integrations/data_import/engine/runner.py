"""Orchestration: document → fetched sources → tables → topo-ordered outputs → summary."""

from typing import Dict, List, Optional

from django.contrib.contenttypes.models import ContentType

from nautobot_ssot.integrations.data_import.engine import normalize, sources
from nautobot_ssot.integrations.data_import.engine.loader import load_output
from nautobot_ssot.integrations.data_import.engine.resolver import FKResolver


class DocumentError(ValueError):
    """Raised when the plan document fails validation."""


def validate_document(document: Dict) -> List[str]:
    """Hand-rolled schema checks. Returns a list of human-readable problems."""
    problems = []
    if not isinstance(document, dict) or not document:
        return ["Document is empty. Configure the plan in the builder first."]

    source_ids = {s.get("id") for s in document.get("sources", [])}
    if not source_ids:
        problems.append("No sources defined.")
    table_ids = set()
    for table in document.get("tables", []):
        table_ids.add(table.get("id"))
        if table.get("from") not in source_ids:
            problems.append(f"Table '{table.get('id')}' references unknown source '{table.get('from')}'.")
        if table.get("expand") and table.get("parent") not in table_ids | {None}:
            # parent may be declared later; check membership at the end instead
            pass

    all_table_ids = {t.get("id") for t in document.get("tables", [])}
    for table in document.get("tables", []):
        if table.get("expand") and table.get("parent") not in all_table_ids:
            problems.append(f"Table '{table.get('id')}' expands with unknown parent '{table.get('parent')}'.")

    outputs = document.get("outputs", [])
    if not outputs:
        problems.append("No outputs (target model mappings) defined.")
    for output in outputs:
        if output.get("table") not in all_table_ids:
            problems.append(f"Output '{output.get('to')}' references unknown table '{output.get('table')}'.")
        if not output.get("to") or "." not in str(output.get("to")):
            problems.append(f"Output has invalid target model '{output.get('to')}'.")
        if not output.get("identifiers"):
            problems.append(f"Output '{output.get('to')}' has no identifier field(s).")
    return problems


def get_content_type(label: str) -> Optional[ContentType]:
    """'dcim.device' → ContentType, or None."""
    try:
        app_label, model = label.split(".", maxsplit=1)
        return ContentType.objects.get(app_label=app_label, model=model)
    except (ValueError, ContentType.DoesNotExist):
        return None


def order_outputs(document: Dict) -> List[Dict]:
    """Topologically sort outputs so dependencies import first.

    Edges: (a) child table's parent output, (b) FK fields whose related model
    is another output's target. Kahn's algorithm; falls back to declared
    order when a cycle is detected.
    """
    outputs = document.get("outputs", [])
    if len(outputs) <= 1:
        return outputs

    table_cfgs = {t["id"]: t for t in document.get("tables", [])}
    output_by_table = {o.get("table"): i for i, o in enumerate(outputs)}
    output_by_target = {str(o.get("to", "")).lower(): i for i, o in enumerate(outputs)}

    deps: Dict[int, set] = {i: set() for i in range(len(outputs))}

    for index, output in enumerate(outputs):
        # (a) expanded table depends on its parent table's output
        table_cfg = table_cfgs.get(output.get("table")) or {}
        parent_table = table_cfg.get("parent")
        if parent_table is not None and parent_table in output_by_table:
            deps[index].add(output_by_table[parent_table])

        # (b) FK fields targeting another output's model
        content_type = get_content_type(str(output.get("to", "")))
        model_class = content_type.model_class() if content_type else None
        if model_class is None:
            continue
        for field_name in output.get("fields") or {}:
            try:
                field = model_class._meta.get_field(field_name)
            except Exception:  # pylint: disable=broad-exception-caught
                continue
            if not field.is_relation or field.related_model is None:
                continue
            related_label = f"{field.related_model._meta.app_label}.{field.related_model._meta.model_name}"
            other = output_by_target.get(related_label)
            if other is not None and other != index:
                deps[index].add(other)

    in_degree = {i: len(d) for i, d in deps.items()}
    adjacency: Dict[int, List[int]] = {i: [] for i in deps}
    for node, dep_set in deps.items():
        for dep in dep_set:
            adjacency[dep].append(node)

    queue = sorted(i for i, deg in in_degree.items() if deg == 0)
    ordered: List[int] = []
    while queue:
        node = queue.pop(0)
        ordered.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(outputs):  # cycle — keep declared order
        return outputs
    return [outputs[i] for i in ordered]


def fetch_all_sources(plan, document: Dict, limit: Optional[int] = None, logger=None) -> Dict[str, List[Dict]]:
    """Fetch/parse every source into raw record lists keyed by source id."""
    records_by_source: Dict[str, List[Dict]] = {}
    for source in document.get("sources", []):
        source_id = source.get("id")
        source_type = source.get("type", "api")
        if source_type == "csv":
            text = (plan.csv_data or {}).get(source_id, "")
            records_by_source[source_id] = sources.parse_csv(text, limit=limit) if text else []
            if not text and logger:
                logger.warning("CSV source '%s' has no uploaded data.", source_id)
        else:
            if plan.integration is None:
                raise DocumentError(f"API source '{source_id}' requires an External Integration on the plan.")
            records_by_source[source_id] = sources.fetch_api_records(
                plan.integration, source, limit=limit, logger=logger
            )
        if logger:
            logger.info("Source '%s': %d records.", source_id, len(records_by_source[source_id]))
    return records_by_source


def run_plan(plan, dry_run: bool = True, limit: Optional[int] = None, logger=None) -> Dict:
    """Execute an ImportPlan end to end. Returns the aggregate summary."""
    document = plan.document or {}
    problems = validate_document(document)
    if problems:
        raise DocumentError("; ".join(problems))

    records_by_source = fetch_all_sources(plan, document, limit=limit, logger=logger)
    tables = normalize.build_tables(document, records_by_source, logger=logger)

    resolver = FKResolver(dry_run=dry_run, logger=logger)
    defaults = document.get("defaults") or {}
    on_record_error = defaults.get("on_record_error", "continue")

    summaries = []
    for output in order_outputs(document):
        content_type = get_content_type(str(output.get("to", "")))
        model_class = content_type.model_class() if content_type else None
        if model_class is None:
            summaries.append({"target": output.get("to"), "errors": ["Unknown target model."]})
            continue
        rows = tables.get(output.get("table"), [])
        if logger:
            logger.info("Importing %d rows → %s", len(rows), output.get("to"))
        summaries.append(
            load_output(
                model_class,
                output,
                rows,
                resolver,
                dry_run=dry_run,
                logger=logger,
                on_record_error=on_record_error,
            )
        )

    return {
        "dry_run": dry_run,
        "outputs": summaries,
        "auto_created_related": list(dict.fromkeys(f"{label}: {value}" for label, value in resolver.created_related)),
        "totals": {
            "created": sum(s.get("created", 0) for s in summaries),
            "updated": sum(s.get("updated", 0) for s in summaries),
            "unchanged": sum(s.get("unchanged", 0) for s in summaries),
            "skipped": sum(s.get("skipped", 0) for s in summaries),
            "errors": sum(len(s.get("errors", [])) for s in summaries),
        },
    }
