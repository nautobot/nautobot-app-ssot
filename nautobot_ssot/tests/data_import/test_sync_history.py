"""Tests for writing Import Plan results into Sync / SyncLogEntry history."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.integrations.data_import.engine.runner import run_plan
from nautobot_ssot.integrations.data_import.models import ImportPlan
from nautobot_ssot.integrations.data_import.sync_history import create_sync_record, finalize_sync_record
from nautobot_ssot.models import SyncLogEntry

SITES_CSV = "site_name,kind\nSH-DC1,SH Site\nSH-DC2,SH Site\n"


def _document():
    return {
        "version": 2,
        "sources": [{"id": "sites", "type": "csv"}],
        "tables": [{"id": "sites", "from": "sites"}],
        "outputs": [
            {
                "table": "sites",
                "to": "dcim.location",
                "identifiers": {"name": {"column": "site_name"}},
                "fields": {
                    "location_type": {"column": "kind", "fk": {"on_missing": "create", "lookup_field": "name"}},
                    "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                },
            }
        ],
        "defaults": {"on_record_error": "continue"},
    }


class SyncHistoryTests(TestCase):
    """Import runs produce Sync + per-record SyncLogEntry rows."""

    def _run(self, dry_run=False):
        plan = ImportPlan.objects.create(name="sync-history", document=_document(), csv_data={"sites": SITES_CSV})
        sync = create_sync_record(plan, dry_run=dry_run, job_result=None)
        summary = run_plan(plan, dry_run=dry_run)
        finalize_sync_record(sync, summary)
        return sync, summary

    def test_live_run_creates_log_entries_with_objects(self):
        from nautobot.dcim.models import Location  # pylint: disable=import-outside-toplevel

        sync, _ = self._run(dry_run=False)
        creates = SyncLogEntry.objects.filter(sync=sync, action=SyncLogEntryActionChoices.ACTION_CREATE)
        self.assertEqual(creates.count(), 2)
        entry = creates.first()
        self.assertEqual(entry.status, SyncLogEntryStatusChoices.STATUS_SUCCESS)
        # Generic FK links to the real Location.
        self.assertIsInstance(entry.synced_object, Location)
        self.assertIn("dcim.location", entry.object_repr)
        # Roll-up summary matches DiffSync's shape.
        self.assertEqual(sync.summary["create"], 2)
        self.assertEqual(sync.summary["delete"], 0)

    def test_second_run_logs_no_change(self):
        plan = ImportPlan.objects.create(name="sync-history-2", document=_document(), csv_data={"sites": SITES_CSV})
        run_plan(plan, dry_run=False)
        sync = create_sync_record(plan, dry_run=False, job_result=None)
        summary = run_plan(plan, dry_run=False)
        finalize_sync_record(sync, summary)
        no_change = SyncLogEntry.objects.filter(
            sync=sync,
            action=SyncLogEntryActionChoices.ACTION_NO_CHANGE,
            status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
        )
        self.assertEqual(no_change.count(), 2)

    def test_skips_logged_as_failures_with_reason(self):
        document = _document()
        document["outputs"][0]["fields"]["location_type"]["fk"]["on_missing"] = "skip_record"
        plan = ImportPlan.objects.create(name="sync-history-3", document=document, csv_data={"sites": SITES_CSV})
        sync = create_sync_record(plan, dry_run=False, job_result=None)
        summary = run_plan(plan, dry_run=False)
        finalize_sync_record(sync, summary)
        failures = SyncLogEntry.objects.filter(sync=sync, status=SyncLogEntryStatusChoices.STATUS_FAILURE)
        self.assertEqual(failures.count(), 2)
        self.assertIn("unresolved location_type", failures.first().message)

    def test_sync_detail_page_renders(self):
        sync, _ = self._run(dry_run=False)
        User = get_user_model()
        user = User.objects.create(username="sync-history-admin", is_superuser=True)
        self.client.force_login(user)
        response = self.client.get(sync.get_absolute_url())
        self.assertEqual(response.status_code, 200)
