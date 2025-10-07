"""Job to process SyncRecords."""

from diffsync.diff import Diff, DiffElement
from diffsync.helpers import DiffSyncSyncer
from nautobot.apps.jobs import BooleanVar, Job, JobButtonReceiver, MultiObjectVar
from nautobot.extras.models import JobResult

from nautobot_ssot.models import SyncRecord
from nautobot_ssot.utils import import_from_dotted_path

name = "Process Records Job"  # pylint: disable=invalid-name


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
    include_children = BooleanVar(default=False)

    class Meta:
        """Meta attributes of ProcessRecordsJob."""

        name = "Process Records Job"
        description = "Process SyncRecords that are in a pending state."
        commit_default = False
        has_sensitive_variables = False

    def __init__(self):
        """Initialize ProcessRecordsJob."""
        self.source_adapter = None
        self.target_adapter = None
        super().__init__()

    def run(self, *args, **kwargs):
        """Run the job."""
        self.records = kwargs.get("records", [])
        self.include_children = kwargs.get("include_children", False)
        self.logger.info("Running Process Records Job.")

        self.load_sync_records(records=self.records)

        # recreate adapters
        source_adapter_cls = import_from_dotted_path(self.records[0].source)
        target_adapter_cls = import_from_dotted_path(self.records[0].target)

        try:
            source_adapter = source_adapter_cls(job=self, **self.records[0].source_kwargs)
            target_adapter = target_adapter_cls(job=self, **self.records[0].target_kwargs)
        except Exception as err:
            self.logger.error(err)
            return None

        self.logger.info("Performing synchronization of selected records.")
        syncer = DiffSyncSyncer(
            diff=diff,
            src_diffsync=source_adapter,
            dst_diffsync=target_adapter,
            flags=record.diffsync_flags,
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
                source_name=record.source,
                dest_name=record.target,
            )
            diff_element.source_attrs = record.source_attrs
            diff_element.dest_attrs = record.target_attrs
            self.diff.add(diff_element)
            if parent:
                parent.add_child(diff_element)
            if self.include_children and len(record.children.all()) > 0:
                self.load_sync_records(records=record.children.all(), parent=diff_element)


class ProcessRecordsJobButtonReceiver(JobButtonReceiver):
    """Job button receiver for SyncRecords."""

    class Meta:
        """Meta attributes of ProcessRecordsJobButtonReceiver."""

        name = "Process SyncRecords Button Receiver"
        has_sensitive_variables = False

    def __init__(self, *args, **kwargs):
        """Initialize the Job."""
        super().__init__(*args, **kwargs)
        self.data = {}

    def receive_job_button(self, obj):
        """Function to execute the job button receiver."""
        self.logger.info("Running Job Button Receiver.", extra={"object": obj})
        user = self.user
        JobResult.enqueue_job(ProcessRecordsJob, user=user, profile=False, data={"records": [obj.id]})
