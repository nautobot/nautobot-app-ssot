"""Jobs for the Data Import integration."""

import json

from nautobot.apps.jobs import BooleanVar, ObjectVar
from nautobot.core.celery import register_jobs
from nautobot.extras.jobs import Job

from nautobot_ssot.integrations.data_import.engine.runner import DocumentError, run_plan
from nautobot_ssot.integrations.data_import.models import ImportPlan
from nautobot_ssot.integrations.data_import.sync_history import create_sync_record, finalize_sync_record

name = "Data Import"  # pylint: disable=invalid-name


class RunImportPlan(Job):
    """Execute a saved Import Plan against Nautobot."""

    import_plan = ObjectVar(
        model=ImportPlan,
        queryset=ImportPlan.objects.filter(enabled=True),
        display_field="name",
        required=True,
        label="Import Plan",
        description="The Import Plan to execute (build one under Plugins > SSoT > Import Plans).",
    )
    dry_run = BooleanVar(
        default=True,
        label="Dry run",
        description="Report what would be created/updated without writing to the database.",
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta for RunImportPlan."""

        name = "Run Import Plan"
        description = "Import data from external APIs or CSV files into Nautobot using a saved Import Plan."
        has_sensitive_variables = False

    def run(self, import_plan, dry_run=True, **kwargs):  # pylint: disable=arguments-differ
        """Run the plan and log a per-output summary."""
        self.logger.info(
            "Running Import Plan '%s' (%s).",
            import_plan.name,
            "dry-run" if dry_run else "LIVE",
        )
        sync = create_sync_record(import_plan, dry_run, self.job_result)
        try:
            summary = run_plan(import_plan, dry_run=dry_run, logger=self.logger)
        except DocumentError as exc:
            self.logger.error("Import Plan configuration problem: %s", exc)
            raise
        finalize_sync_record(sync, summary)
        self.logger.info(
            "Per-record results: [Sync detail view](%s)",
            sync.get_absolute_url(),
        )

        for output_summary in summary["outputs"]:
            self.logger.info(
                "%s → created: %s, updated: %s, unchanged: %s, skipped: %s, errors: %s",
                output_summary.get("target"),
                output_summary.get("created", 0),
                output_summary.get("updated", 0),
                output_summary.get("unchanged", 0),
                output_summary.get("skipped", 0),
                len(output_summary.get("errors", [])),
            )
            for error in output_summary.get("errors", [])[:20]:
                self.logger.warning("%s: %s", output_summary.get("target"), error)
            skip_reasons: dict = {}
            for record in output_summary.get("records", []):
                if record.get("action") == "skip":
                    reason = record.get("reason", "unknown")
                    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            for reason, count in sorted(skip_reasons.items(), key=lambda item: -item[1])[:10]:
                self.logger.warning(
                    "%s: skipped %d record(s) — %s",
                    output_summary.get("target"),
                    count,
                    reason,
                )

        if summary["auto_created_related"]:
            self.logger.info("Auto-created related objects: %s", ", ".join(summary["auto_created_related"][:50]))

        totals = summary["totals"]
        self.logger.info(
            "Totals%s — created: %s, updated: %s, unchanged: %s, skipped: %s, errors: %s",
            " (dry-run, nothing written)" if dry_run else "",
            totals["created"],
            totals["updated"],
            totals["unchanged"],
            totals["skipped"],
            totals["errors"],
        )
        self.create_file("import_summary.json", json.dumps(summary, indent=2, default=str))
        return totals


jobs = [RunImportPlan]
register_jobs(*jobs)
