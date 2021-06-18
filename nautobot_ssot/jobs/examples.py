from django.urls import reverse

from nautobot.dcim.models import Site
from nautobot.extras.jobs import StringVar, Job

from nautobot_ssot.choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget


class ExampleDataSource(DataSource, Job):
    """An example data-source Job for loading data into Nautobot."""

    site_slug = StringVar(description="Site to create or update", default="")

    class Meta:
        name = "Example Data Source"
        description = "An example of a 'data source' Job for loading data into Nautobot from elsewhere."
        data_source = "Dummy Data"

    @classmethod
    def data_mappings(cls):
        return (DataMapping("site slug", None, "Site", reverse("dcim:site_list")),)

    def sync_data(self):
        """Perform data sync into Nautobot."""
        # For sake of a simple example, we don't actually use DiffSync here.
        site, created = Site.objects.get_or_create(
            slug=self.kwargs["site_slug"],
            defaults={"name": self.kwargs["site_slug"]},
        )
        action = SyncLogEntryActionChoices.ACTION_CREATE if created else SyncLogEntryActionChoices.ACTION_UPDATE
        self.sync_log(
            action=action,
            status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
            synced_object=site,
        )


class ExampleDataTarget(DataTarget, Job):
    """An example data-target Job for loading data from Nautobot into another system."""

    site_slug = StringVar(description="Site to sync to an imaginary data target", default="")

    class Meta:
        name = "Example Data Target"
        description = "An example of a 'data target' Job for loading data from Nautobot into elsewhere."
        data_target = "Dummy Data"

    @classmethod
    def data_mappings(cls):
        return (DataMapping("Site", reverse("dcim:site_list"), "site slug", None),)

    def sync_data(self):
        """Perform data sync from Nautobot."""
        # For sake of a simple example, we don't actually use DiffSync here.
        site = Site.objects.get(slug=self.kwargs["site_slug"])

        self.sync_log(
            action=SyncLogEntryActionChoices.ACTION_UPDATE,
            status=SyncLogEntryStatusChoices.STATUS_SUCCESS,
            synced_object=site,
        )
