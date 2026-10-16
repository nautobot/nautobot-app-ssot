"""Shared helpers for the LibreNMS consolidation phases.

Kept separate from the platform and manufacturer modules so both can use them without a circular
import.
"""

import csv
import io

from django.apps import apps

# Planned actions, as reported in the CSV.
ACTION_NONE = "none"
ACTION_REPAIR_DRIVER = "repair-driver"
ACTION_RENAME = "rename"
ACTION_MERGE_INTO = "merge-into"
ACTION_MERGE_SURVIVOR = "merge-survivor"
ACTION_DELETE = "delete"

# Past this, swap per-object validated_save() for bulk_update, giving up per-object ObjectChanges.
BULK_UPDATE_THRESHOLD = 500


def get_model_or_none(label: str):
    """Model for `label`, or None when the app providing it is not installed."""
    try:
        return apps.get_model(label)
    except LookupError:
        return None


def get_object_permission_model():
    """ObjectPermission model, or None if absent."""
    return get_model_or_none("users.ObjectPermission")


def name_references(name: str) -> list:
    """Config referring to an object by name rather than primary key."""
    # Renaming keeps the PK, so FKs are safe; saved filters, permission constraints and
    # scheduled job kwargs store the name as a string and would go stale.
    references = []

    permission_model = get_object_permission_model()
    if permission_model is not None:
        for permission in permission_model.objects.all():
            if name in str(permission.constraints or ""):
                references.append(f"ObjectPermission:{permission.name}")

    for label, attribute, prefix in [
        ("extras.DynamicGroup", "filter", "DynamicGroup"),
        ("extras.SavedView", "config", "SavedView"),
        ("extras.ScheduledJob", "kwargs", "ScheduledJob"),
    ]:
        model = get_model_or_none(label)
        if model is None:
            continue
        for obj in model.objects.all():
            if name in str(getattr(obj, attribute, None) or ""):
                references.append(f"{prefix}:{obj.name}")

    return references


def permission_references(references: list) -> list:
    """References that are ObjectPermission constraints."""
    return [reference for reference in references if reference.startswith("ObjectPermission:")]


def build_csv(plans, columns) -> str:
    """Render plan rows as CSV."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for plan in plans:
        writer.writerow(plan.as_csv_row())
    return buffer.getvalue()


def build_diff_dict(platform_plans, manufacturer_plans) -> dict:
    """Render the plan in SSoT's diff format, for `Sync.diff`.

    `render_diff` walks a plain nested dict rather than a DiffSync object, so the consolidation
    plan can reuse SSoT's own diff view and history without pretending to be a two-system sync.
    Shape is `{record_type: {object: {"-": {...}, "+": {...}}}}`.
    """
    diff = {}
    for plan in platform_plans:
        entry = _plan_diff_entry(plan)
        if entry:
            diff.setdefault("dcim.platform", {})[plan.name] = entry
    for plan in manufacturer_plans:
        entry = _plan_diff_entry(plan)
        if entry:
            diff.setdefault("dcim.manufacturer", {})[plan.name] = entry
    return diff


def _plan_diff_entry(plan) -> dict:
    """Before/after pair for one plan row, or {} when nothing is planned."""
    if plan.refusal_reason:
        # No +/- keys, so render_diff styles it as unchanged; the reason explains why.
        return {"refused": {"reason": plan.refusal_reason}}

    removed, added = {}, {}
    row = plan.as_csv_row()
    intended_driver = row.get("intended_driver")
    if ACTION_REPAIR_DRIVER in plan.actions and intended_driver:
        removed["network_driver"] = row.get("network_driver") or "(blank)"
        added["network_driver"] = intended_driver
    if ACTION_RENAME in plan.actions:
        target = getattr(plan, "target_name", "") or row.get("intended_name", "")
        if target:
            removed["name"] = plan.name
            added["name"] = target
    if ACTION_MERGE_INTO in plan.actions:
        removed["merged_away"] = plan.name
        added["merged_into"] = getattr(plan, "survivor_name", "") or row.get("intended_name", "")
    if ACTION_DELETE in plan.actions:
        removed["deleted"] = plan.name

    if not removed and not added:
        return {}
    return {"-": removed, "+": added}


def build_markdown_table(plans, columns) -> str:
    """Render plan rows as a markdown table.

    Nautobot's job log renders messages as markdown, so this shows up as a real table in the job
    result rather than as an attachment the operator has to download.
    """
    if not plans:
        return ""
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for plan in plans:
        row = plan.as_csv_row()
        cells = [str(row.get(column, "") or "").replace("|", "\\|") for column in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
