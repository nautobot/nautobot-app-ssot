"""Example implementation of a Nautobot Data Sync worker class."""

from django.db import transaction

from nautobot.dcim.models import Site, RackGroup, Rack
from nautobot.extras.jobs import StringVar
from nautobot.utilities.exceptions import AbortTransaction

from nautobot_data_sync.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_data_sync.sync.base import DataSyncWorker


class ExampleSyncWorker(DataSyncWorker):

    site_slug = StringVar(description="Which site's data to synchronize", default="")

    class Meta:
        name = "Example Sync Worker"
        slug = "example-sync-worker"
        description = "An example of how a sync worker might be implemented"

    def execute(self, dry_run=True):
        """Perform a mock data synchronization."""

        # For sake of a simple example, we don't actually use DiffSync here
        try:
            with transaction.atomic():
                site, created = Site.objects.get_or_create(
                    slug=self.data["site_slug"],
                    defaults={"name": self.data["site_slug"]},
                )
                if dry_run:
                    raise AbortTransaction()
        except AbortTransaction:
            self.job_log("Database changes have been reverted automatically.")

        self.sync_log(
            action=SyncLogEntryActionChoices.ACTION_CREATE if created else SyncLogEntryActionChoices.ACTION_UPDATE,
            status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
            changed_object=site,
        )
