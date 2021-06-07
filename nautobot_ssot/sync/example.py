"""Example implementation of a Nautobot Data Sync worker class."""

from django.db import transaction

from nautobot.dcim.models import Site
from nautobot.extras.jobs import StringVar
from nautobot.utilities.exceptions import AbortTransaction

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.sync.worker import DataSyncWorker


class ExampleSyncWorker(DataSyncWorker):

    site_slug = StringVar(description="Which site's data to synchronize", default="")

    class Meta:
        name = "Example Sync Worker"
        slug = "example-sync-worker"
        description = "An example of how a sync worker might be implemented."

    def execute(self):
        """Perform a mock data synchronization."""

        # For sake of a simple example, we don't actually use DiffSync here
        self.job_log(f"Beginning execution, dry_run = {self.dry_run}")
        try:
            with transaction.atomic():
                site, created = Site.objects.get_or_create(
                    slug=self.data["site_slug"],
                    defaults={"name": self.data["site_slug"]},
                )
                action = SyncLogEntryActionChoices.ACTION_CREATE if created else SyncLogEntryActionChoices.ACTION_UPDATE
                self.sync_log(
                    action=action,
                    status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
                    changed_object=site,
                )
                if self.dry_run:
                    # Note that this is not an ideal way to implement dry-run behavior;
                    # most notably it will also revert any JobResult changes or SyncLogEntry records created above!
                    raise AbortTransaction()
        except AbortTransaction:
            self.job_log("Database changes have been reverted automatically.")
