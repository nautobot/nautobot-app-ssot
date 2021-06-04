import logging

from diffsync.enum import DiffSyncFlags

from nautobot.extras.jobs import StringVar

from nautobot_ssot.sync.base import DataSyncWorker

from .diffsync.adapter_nautobot import NautobotDiffSync
from .diffsync.adapter_servicenow import ServiceNowDiffSync
from .servicenow import ServiceNowClient


class ServiceNowExportDataSyncWorker(DataSyncWorker):
    """Worker class to handle data sync to ServiceNow."""

    snow_instance = StringVar(
        label="ServiceNow instance",
        description='&lt;instance&gt;.servicenow.com, such as "dev12345"'
    )
    snow_username = StringVar(
        label="ServiceNow username",
    )
    snow_password = StringVar(
        label="ServiceNow password",
        # TODO widget=...
    )
    snow_app_prefix = StringVar(
        label="ServiceNow app prefix",
        description="(if any)",
        default="",
        required=False,
    )

    class Meta:
        name = "ServiceNow"
        slug = "service-now"
        description = "Synchronize data from Nautobot into ServiceNow."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snc = ServiceNowClient(
            instance=self.data["snow_instance"],
            username=self.data["snow_username"],
            password=self.data["snow_password"],
            app_prefix=self.data["snow_app_prefix"],
            worker=self,
        )
        self.servicenow_diffsync = ServiceNowDiffSync(client=self.snc, worker=self)
        self.nautobot_diffsync = NautobotDiffSync()

    def execute(self):
        """Sync a slew of Nautobot data into ServiceNow."""
        self.servicenow_diffsync.load()
        self.nautobot_diffsync.load()

        diff = self.servicenow_diffsync.diff_from(self.nautobot_diffsync)
        self.sync.diff = diff.dict()
        self.sync.save()
        if not self.dry_run:
            self.servicenow_diffsync.sync_from(
                self.nautobot_diffsync,
                flags=DiffSyncFlags.CONTINUE_ON_FAILURE |
                DiffSyncFlags.LOG_UNCHANGED_RECORDS |
                DiffSyncFlags.SKIP_UNMATCHED_DST,
            )
