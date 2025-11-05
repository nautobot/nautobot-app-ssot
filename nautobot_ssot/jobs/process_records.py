"""Job to process SyncRecords."""

from typing import List

import structlog
from diffsync.diff import Diff, DiffElement
from diffsync.helpers import DiffSyncSyncer
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from nautobot.apps.jobs import BooleanVar, Job, MultiObjectVar
from nautobot.extras.models import Status

from nautobot_ssot.models import SyncRecord
from nautobot_ssot.utils import import_from_dotted_path

name = "Process Records Job"  # pylint: disable=invalid-name


STATUS_MAP = {"success": "Successful", "error": "Error", "failed": "Failed"}


class ProcessRecordsJob(Job):
    """Job to process SyncRecords."""

    records = MultiObjectVar(
        model=SyncRecord,
        required=True,
        queryset=SyncRecord.objects.all(),
        query_params={"status": "pending"},
        label="Sync Records",
        description="The Sync Records to process.",
    )
    include_children = BooleanVar(default=False, description="Include children SyncRecords when processing.")

    class Meta:
        """Meta attributes of ProcessRecordsJob."""

        name = "Process Sync Records"
        description = "Process SyncRecords that are in a pending state."
        commit_default = False
        has_sensitive_variables = False

    def __init__(self):
        """Initialize ProcessRecordsJob."""
        self.source_adapter = None
        self.target_adapter = None
        self.diff = Diff()
        super().__init__()

    def run(self, **kwargs):
        """Run the job."""
        self.records = kwargs.get("records", [])
        if not self.records:
            self.logger.error("No records specified so unable to continue Job.")
            return

        self.include_children = kwargs.get("include_children", False)
        self.logger.info("Running Process Records Job.")

        self.load_sync_records(records=self.records)

        # recreate adapters
        source_adapter_cls = import_from_dotted_path(f"{self.records[0].module}.{self.records[0].source_adapter}")
        target_adapter_cls = import_from_dotted_path(f"{self.records[0].module}.{self.records[0].target_adapter}")

        self.source_adapter = source_adapter_cls(job=self, **self.records[0].source_kwargs)
        self.target_adapter = target_adapter_cls(job=self, **self.records[0].target_kwargs)

        self.logger.info("Performing synchronization of selected records.")
        structlog.configure(
            processors=[
                self._structlog_to_sync_record,
                structlog.stdlib.render_to_log_kwargs,
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        syncer = DiffSyncSyncer(
            diff=self.diff,
            src_diffsync=self.source_adapter,
            dst_diffsync=self.target_adapter,
            flags=self.records[0].diffsync_flags,
        )
        result = syncer.perform_sync()
        if result:
            self.logger.info("Sync was a success!")
        else:
            self.logger.warning("Sync failed!")

    def load_sync_records(self, records: List[SyncRecord], parent: DiffElement = None):
        """Recursive function to load SyncRecords into DiffElements.

        Args:
            records (List[dict]): List of SyncRecords to be loaded into DiffElements.
            parent (DiffElement, optional): Parent DiffElement to assign child DiffElements to. Defaults to None.
        """
        for record in records:
            self.logger.info("Processing record %s.", record.obj_name)
            diff_element = DiffElement(
                obj_type=record.obj_type,
                name=record.obj_name,
                keys=record.obj_keys,
                source_name=record.source_adapter,
                dest_name=record.target_adapter,
            )
            diff_element.source_attrs = record.source_attrs
            diff_element.dest_attrs = record.target_attrs
            self.diff.add(diff_element)
            if parent:
                parent.add_child(diff_element)
            if self.include_children and len(record.children.all()) > 0:
                self.load_sync_records(records=record.children.all(), parent=diff_element)

    def _structlog_to_sync_record(self, _logger, _log_method, event_dict):
        """Update status of SyncRecord and associate to synced object if found."""
        if all(key in event_dict for key in ("src", "dst", "action", "event", "model", "unique_id", "diffs", "status")):
            # The DiffSync log gives us a model name (string) and unique_id (string).
            # Try to look up the actual Nautobot object that this describes.
            job_model = self.records[0].sync.job_result.job_model
            job_cls = import_from_dotted_path(f"{job_model.module_name}.{job_model.job_class_name}")
            job = job_cls()
            synced_object = job.lookup_object(  # pylint: disable=assignment-from-none
                event_dict["model"], event_dict["unique_id"]
            )
            try:
                record = SyncRecord.objects.get(
                    obj_type=event_dict["model"], obj_name=event_dict["unique_id"], sync=self.records[0].sync
                )
                record.status = Status.objects.get(name=STATUS_MAP[event_dict["status"]])
                record.message = event_dict["event"] if event_dict.get("event") else ""
                if synced_object:
                    record.synced_object_id = synced_object.id
                    record.synced_object_type = ContentType.objects.get_for_model(synced_object)
                record.validated_save()
            except SyncRecord.DoesNotExist as err:
                self.logger.error(
                    "Unable to find SyncRecord for %s %s. %s", event_dict["model"], event_dict["unique_id"], err
                )
            except ValidationError as err:
                self.logger.error("Error saving SyncRecord: %s", err)

        return event_dict
