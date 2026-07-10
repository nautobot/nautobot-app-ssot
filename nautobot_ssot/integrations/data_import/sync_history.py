"""Write Data Import results into the SSoT Sync / SyncLogEntry history models.

This gives Import Plan runs the same sync detail view as DiffSync-based SSoT
jobs: per-record create/update/no-change rows, filterable, with links to the
synced objects and per-record skip/error messages.
"""

import json
from typing import Dict, Optional

from django.utils import timezone

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.integrations.data_import.engine.runner import get_content_type
from nautobot_ssot.models import Sync, SyncLogEntry

# summary["records"] action → (SyncLogEntry action, status)
_RECORD_MAP = {
    "create": (SyncLogEntryActionChoices.ACTION_CREATE, SyncLogEntryStatusChoices.STATUS_SUCCESS),
    "update": (SyncLogEntryActionChoices.ACTION_UPDATE, SyncLogEntryStatusChoices.STATUS_SUCCESS),
    "unchanged": (SyncLogEntryActionChoices.ACTION_NO_CHANGE, SyncLogEntryStatusChoices.STATUS_SUCCESS),
    "skip": (SyncLogEntryActionChoices.ACTION_NO_CHANGE, SyncLogEntryStatusChoices.STATUS_FAILURE),
    "error": (SyncLogEntryActionChoices.ACTION_NO_CHANGE, SyncLogEntryStatusChoices.STATUS_ERROR),
}

BULK_BATCH = 500


def create_sync_record(plan, dry_run: bool, job_result) -> Sync:
    """Create the Sync envelope for one Import Plan run."""
    source = plan.integration.name if plan.integration else "CSV upload"
    return Sync.objects.create(
        source=source[:64],
        target="Nautobot",
        dry_run=dry_run,
        job_result=job_result,
        start_time=timezone.now(),
        diff={},
    )


def finalize_sync_record(sync: Sync, summary: Dict) -> None:
    """Write per-record SyncLogEntry rows and the roll-up summary."""
    entries = []
    for output in summary.get("outputs", []):
        content_type = get_content_type(str(output.get("target", "")))
        for record in output.get("records", []):
            entry = _entry_for_record(sync, record, content_type, output)
            if entry is not None:
                entries.append(entry)
            if len(entries) >= BULK_BATCH:
                SyncLogEntry.objects.bulk_create(entries)
                entries = []
    if entries:
        SyncLogEntry.objects.bulk_create(entries)

    totals = summary.get("totals", {})
    sync.summary = {
        "create": totals.get("created", 0),
        "update": totals.get("updated", 0),
        "delete": 0,
        "no-change": totals.get("unchanged", 0) + totals.get("skipped", 0),
    }
    sync.diff = {"totals": totals, "note": "Data Import run — see log entries for per-record detail."}
    sync.save()


def _entry_for_record(sync: Sync, record: Dict, content_type, output) -> Optional[SyncLogEntry]:
    action_status = _RECORD_MAP.get(record.get("action"))
    if action_status is None:
        return None
    action, status = action_status

    message = record.get("reason", "")
    diff = None
    if record.get("values"):
        diff = {"+": record["values"]}
    elif record.get("changes"):
        diff = {"+": record["changes"]}
    if not message and diff:
        message = json.dumps(diff["+"], default=str)[:500]

    synced_object_id = None
    synced_object_type = None
    if record.get("pk") and content_type is not None:
        synced_object_id = record["pk"]
        synced_object_type = content_type

    object_repr = str(record.get("identifier") or record.get("row") or "")
    if content_type is not None:
        object_repr = f"{output.get('target')}: {object_repr}"

    return SyncLogEntry(
        sync=sync,
        action=action,
        status=status,
        message=message,
        diff=diff,
        synced_object_type=synced_object_type,
        synced_object_id=synced_object_id,
        object_repr=object_repr,
    )
