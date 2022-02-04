"""Base Job classes for sync workers."""
from collections import namedtuple
from datetime import datetime
import traceback
import tracemalloc
from typing import Iterable

from django.forms import HiddenInput
from django.templatetags.static import static
from django.utils import timezone
from django.utils.functional import classproperty

# pylint-django doesn't understand classproperty, and complains unnecessarily. We disable this specific warning:
# pylint: disable=no-self-argument

from diffsync.enum import DiffSyncFlags
import structlog

from nautobot.extras.jobs import BaseJob, BooleanVar

from nautobot_ssot.choices import SyncLogEntryActionChoices
from nautobot_ssot.models import Sync, SyncLogEntry


DataMapping = namedtuple("DataMapping", ["source_name", "source_url", "target_name", "target_url"])
"""Entry in the list returned by a job's data_mappings() API.

The idea here is to provide insight into how various classes of data are mapped between Nautobot
and the other system acting as data source/target.

* source_name: Name of a data class (device, location, vlan, etc.) provided by the data source.
* source_url: URL (if any) to hyperlink for this source_name in the UI.
              Can be used, for example, to link to the Nautobot list view for this data class.
* target_name: Name of a data class on the data target that corresponds to the source data.
* target_url: URL (if any) to hyperlink the target_name.
"""


class DataSyncBaseJob(BaseJob):  # pylint: disable=too-many-instance-attributes
    """Common base class for data synchronization jobs.

    Works mostly as per the BaseJob API, with the following changes:

    - Concrete subclasses are responsible for implementing `self.sync_data()` (or related hooks), **not** `self.run()`.
    - Subclasses may optionally define any Meta field supported by Jobs, as well as the following:
      - `dry_run_default` - defaults to True if unspecified
      - `data_source` and `data_target` as labels (by default, will use the `name` and/or "Nautobot" as appropriate)
      - `data_source_icon` and `data_target_icon`
    """

    dry_run = BooleanVar()
    memory_profiling = BooleanVar(description="Perform a memory profiling analysis.", default=False)

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`.

        Relevant available instance attributes include:

        - self.kwargs     (corresponds to the Job's `data` input, including 'dry_run' option)
        - self.job_result (as per Job API)
        """
        raise NotImplementedError

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`.

        Relevant available instance attributes include:

        - self.kwargs     (corresponds to the Job's `data` input, including 'dry_run' option)
        - self.job_result (as per Job API)
        """
        raise NotImplementedError

    def calculate_diff(self):
        """Method to calculate the difference from SOURCE to TARGET adapter and store in `self.diff`.

        This is a generic implementation that you could overwrite completely in your custom logic.
        """
        if self.source_adapter is not None and self.target_adapter is not None:
            self.diff = self.source_adapter.diff_to(self.target_adapter, flags=self.diffsync_flags)
            self.sync.diff = self.diff.dict()
            self.sync.save()
        else:
            self.log_warning(message="Not both adapters were properly initialized prior to diff calculation.")

    def execute_sync(self):
        """Method to synchronize the difference from `self.diff`, from SOURCE to TARGET adapter.

        This is a generic implementation that you could overwrite completely in your custom logic.
        """
        if self.source_adapter is not None and self.target_adapter is not None:
            self.source_adapter.sync_to(self.target_adapter, flags=self.diffsync_flags)
        else:
            self.log_warning(message="Not both adapters were properly initialized prior to synchronization.")

    def sync_data(self):
        """Method to load data from adapters, calculate diffs and sync (if not dry-run).

        It is composed by 4 methods:
        - self.load_source_adapter: instantiates the source adapter (self.source_adapter) and loads its data
        - self.load_target_adapter: instantiates the target adapter (self.target_adapter) and loads its data
        - self.calculate_diff: generates the diff from source to target adapter and stores it in self.diff
        - self.execute_sync: if not dry-run, uses the self.diff to synchronize from source to target

        This is a generic implementation that you could overwrite completely in you custom logic.
        Available instance attributes include:

        - self.kwargs     (corresponds to the Job's `data` input, including 'dry_run' option)
        - self.commit     (should generally be True)
        - self.sync       (Sync instance tracking this job execution)
        - self.job_result (as per Job API)
        """

        def record_memory_trace(step: str):
            """Helper function to record memory usage and reset tracemalloc stats."""
            memory_final, memory_peak = tracemalloc.get_traced_memory()
            setattr(self.sync, f"{step}_memory_final", memory_final)
            setattr(self.sync, f"{step}_memory_peak", memory_peak)
            self.sync.save()
            self.log_info(
                message=(f"Traced memory for {step} (Final, Peak): {memory_final} bytes, {memory_peak} bytes")
            )
            tracemalloc.clear_traces()

        if not self.sync:
            return

        if self.kwargs["memory_profiling"]:
            tracemalloc.start()

        start_time = datetime.now()

        self.log_info(message="Loading current data from source adapter...")
        self.load_source_adapter()
        load_source_adapter_time = datetime.now()
        self.sync.source_load_time = load_source_adapter_time - start_time
        self.sync.save()
        self.log_info(message=f"Source Load Time from {self.source_adapter}: {self.sync.source_load_time}")
        if self.kwargs["memory_profiling"]:
            record_memory_trace("source_load")

        self.log_info(message="Loading current data from target adapter...")
        self.load_target_adapter()
        load_target_adapter_time = datetime.now()
        self.sync.target_load_time = load_target_adapter_time - load_source_adapter_time
        self.sync.save()
        self.log_info(message=f"Target Load Time from {self.target_adapter}: {self.sync.target_load_time}")
        if self.kwargs["memory_profiling"]:
            record_memory_trace("target_load")

        self.log_info(message="Calculating diffs...")
        self.calculate_diff()
        calculate_diff_time = datetime.now()
        self.sync.diff_time = calculate_diff_time - load_target_adapter_time
        self.sync.save()
        self.log_info(message=f"Diff Calculation Time: {self.sync.diff_time}")
        if self.kwargs["memory_profiling"]:
            record_memory_trace("diff")

        if self.kwargs["dry_run"]:
            self.log_info("As `dry_run` is set, skipping the actual data sync.")
        else:
            self.log_info(message=f"Syncing from {self.source_adapter} to {self.target_adapter}...")
            self.execute_sync()
            execute_sync_time = datetime.now()
            self.sync.sync_time = execute_sync_time - calculate_diff_time
            self.sync.save()
            self.log_info(message="Sync complete")
            self.log_info(message=f"Sync Time: {self.sync.sync_time}")
            if self.kwargs["memory_profiling"]:
                record_memory_trace("sync")

    def lookup_object(self, model_name, unique_id):  # pylint: disable=no-self-use,unused-argument
        """Look up the Nautobot record, if any, identified by the args.

        Optional helper method used to build more detailed/accurate SyncLogEntry records from DiffSync logs.

        Args:
            model_name (str): DiffSyncModel class name or similar class/model label.
            unique_id (str): DiffSyncModel unique_id or similar unique identifier.

        Returns:
            models.Model: Nautobot model instance, or None
        """
        return None

    @classmethod
    def data_mappings(cls) -> Iterable[DataMapping]:
        """List the data mappings involved in this sync job."""
        return []

    @classmethod
    def config_information(cls):
        """Return a dict of user-facing configuration information {property: value}.

        Note that this will be rendered 'as-is' in the UI, so as a general practice this
        should NOT include sensitive information such as passwords!
        """
        return {}

    def sync_log(  # pylint: disable=too-many-arguments
        self,
        action,
        status,
        message="",
        diff=None,
        synced_object=None,
        object_repr="",
    ):
        """Log a action message as a SyncLogEntry."""
        if synced_object and not object_repr:
            object_repr = repr(synced_object)

        SyncLogEntry.objects.create(
            sync=self.sync,
            action=action,
            status=status,
            message=message,
            diff=diff,
            synced_object=synced_object,
            object_repr=object_repr,
        )

    def _structlog_to_sync_log_entry(self, _logger, _log_method, event_dict):
        """Capture certain structlog messages from DiffSync into the Nautobot database."""
        if all(key in event_dict for key in ("src", "dst", "action", "model", "unique_id", "diffs", "status")):
            # The DiffSync log gives us a model name (string) and unique_id (string).
            # Try to look up the actual Nautobot object that this describes.
            synced_object = self.lookup_object(  # pylint: disable=assignment-from-none
                event_dict["model"], event_dict["unique_id"]
            )
            object_repr = repr(synced_object) if synced_object else f"{event_dict['model']} {event_dict['unique_id']}"
            self.sync_log(
                action=event_dict["action"] or SyncLogEntryActionChoices.ACTION_NO_CHANGE,
                diff=event_dict["diffs"] if event_dict["action"] else None,
                status=event_dict["status"],
                message=event_dict["event"],
                synced_object=synced_object,
                object_repr=object_repr,
            )

        return event_dict

    @classmethod
    def _get_vars(cls):
        """Extend Job._get_vars to include `dry_run` variable.

        Workaround for https://github.com/netbox-community/netbox/issues/5529
        """
        got_vars = super()._get_vars()
        if hasattr(cls, "dry_run"):
            got_vars["dry_run"] = cls.dry_run

        if hasattr(cls, "memory_profiling"):
            got_vars["memory_profiling"] = cls.memory_profiling
        return got_vars

    def __init__(self):
        """Initialize a Job."""
        super().__init__()
        self.sync = None
        self.kwargs = {}
        self.commit = False
        self.diff = None
        self.source_adapter = None
        self.target_adapter = None
        # Default diffsync flags. You can overwrite them at any time.
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE | DiffSyncFlags.LOG_UNCHANGED_RECORDS

    def as_form(self, data=None, files=None, initial=None):
        """Render this instance as a Django form for user inputs, including a "Dry run" field."""
        form = super().as_form(data=data, files=files, initial=initial)
        # Set the "dry_run" widget's initial value based on our Meta attribute, if any
        form.fields["dry_run"].initial = getattr(self.Meta, "dry_run_default", True)
        # Hide the "commit" widget to reduce user confusion
        form.fields["_commit"].widget = HiddenInput()
        return form

    @classproperty
    def data_source(cls):
        """The system or data source providing input data for this sync."""
        return getattr(cls.Meta, "data_source", cls.name)

    @classproperty
    def data_target(cls):
        """The system or data source being modified by this sync."""
        return getattr(cls.Meta, "data_target", cls.name)

    @classproperty
    def data_source_icon(cls):
        """Icon corresponding to the data_source."""
        return getattr(cls.Meta, "data_source_icon", None)

    @classproperty
    def data_target_icon(cls):
        """Icon corresponding to the data_target."""
        return getattr(cls.Meta, "data_target_icon", None)

    def run(self, data, commit):
        """Job entry point from Nautobot - do not override!"""
        self.sync = Sync.objects.create(
            source=self.data_source,
            target=self.data_target,
            dry_run=data["dry_run"],
            job_result=self.job_result,
            start_time=timezone.now(),
            diff={},
        )

        # Add _structlog_to_sync_log_entry as a processor for structlog calls from DiffSync
        structlog.configure(
            processors=[self._structlog_to_sync_log_entry, structlog.stdlib.render_to_log_kwargs],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        self.kwargs = data
        self.commit = commit

        # We need to catch exceptions and handle them, because if they aren't caught here,
        # they'll be caught by the Nautobot core run_job() function, which will trigger a database
        # rollback, which will delete our above created Sync record!
        try:
            self.sync_data()
        except Exception as exc:  # pylint: disable=broad-except
            stacktrace = traceback.format_exc()
            self.log_failure(message=f"An exception occurred: `{type(exc).__name__}: {exc}`\n```\n{stacktrace}\n```")


# pylint: disable=abstract-method
class DataSource(DataSyncBaseJob):
    """Base class for Jobs that sync data **from** another data source **to** Nautobot."""

    dry_run = BooleanVar(description="Perform a dry-run, making no actual changes to Nautobot data.")

    @classproperty
    def data_target(cls):
        """For a DataSource this is always Nautobot."""
        return "Nautobot"

    @classproperty
    def data_target_icon(cls):
        """For a DataSource this is always the Nautobot logo."""
        return static("img/nautobot_logo.png")


class DataTarget(DataSyncBaseJob):
    """Base class for Jobs that sync data **to** another data target **from** Nautobot."""

    dry_run = BooleanVar(description="Perform a dry-run, making no actual changes to the remote system.")

    @classproperty
    def data_source(cls):
        """For a DataTarget this is always Nautobot."""
        return "Nautobot"

    @classproperty
    def data_source_icon(cls):
        """For a DataTarget this is always the Nautobot logo."""
        return static("img/nautobot_logo.png")
