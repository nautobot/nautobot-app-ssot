"""Base Job classes for sync workers."""

from collections import namedtuple
from datetime import datetime
import tracemalloc
from typing import Iterable, Optional

from django.db.utils import OperationalError
from django.templatetags.static import static
from django.utils import timezone
from django.utils.functional import classproperty

# pylint-django doesn't understand classproperty, and complains unnecessarily. We disable this specific warning:
# pylint: disable=no-self-argument

from diffsync.enum import DiffSyncFlags
import structlog

from nautobot.extras.jobs import DryRunVar, Job, BooleanVar

from nautobot_ssot.choices import SyncLogEntryActionChoices
from nautobot_ssot.models import BaseModel, Sync, SyncLogEntry


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


class DataSyncBaseJob(Job):  # pylint: disable=too-many-instance-attributes
    """Common base class for data synchronization jobs.

    Works mostly as per the BaseJob API, with the following changes:

    - Concrete subclasses are responsible for implementing `self.sync_data()` (or related hooks), **not** `self.run()`.
    - Subclasses may optionally define any Meta field supported by Jobs, as well as the following:
      - `dryrun_default` - defaults to True if unspecified
      - `data_source` and `data_target` as labels (by default, will use the `name` and/or "Nautobot" as appropriate)
      - `data_source_icon` and `data_target_icon`
    """

    dryrun = DryRunVar(description="Perform a dry-run, making no actual changes to Nautobot data.", default=True)
    memory_profiling = BooleanVar(description="Perform a memory profiling analysis.", default=False)

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`.

        Relevant available instance attributes include:

        - self.job_result (as per Job API)
        """
        raise NotImplementedError

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`.

        Relevant available instance attributes include:

        - self.job_result (as per Job API)
        """
        raise NotImplementedError

    def calculate_diff(self):
        """Method to calculate the difference from SOURCE to TARGET adapter and store in `self.diff`.

        This is a generic implementation that you could overwrite completely in your custom logic.
        """
        if self.source_adapter is not None and self.target_adapter is not None:
            self.diff = self.source_adapter.diff_to(self.target_adapter, flags=self.diffsync_flags)
            self.sync.diff = {}
            self.sync.summary = self.diff.summary()
            self.sync.save()
            try:
                self.sync.diff = self.diff.dict()
                self.sync.save()
            except OperationalError:
                self.logger.warning("Unable to save JSON diff to the database; likely the diff is too large.")
                self.sync.refresh_from_db()
            self.logger.info(self.diff.summary())
        else:
            self.logger.warning("Not both adapters were properly initialized prior to diff calculation.")

    def execute_sync(self):
        """Method to synchronize the difference from `self.diff`, from SOURCE to TARGET adapter.

        This is a generic implementation that you could overwrite completely in your custom logic.
        """
        if self.source_adapter is not None and self.target_adapter is not None:
            self.source_adapter.sync_to(self.target_adapter, flags=self.diffsync_flags)
        else:
            self.logger.warning("Not both adapters were properly initialized prior to synchronization.")

    def sync_data(self, memory_profiling):
        """Method to load data from adapters, calculate diffs and sync (if not dry-run).

        It is composed by 4 methods:
        - self.load_source_adapter: instantiates the source adapter (self.source_adapter) and loads its data
        - self.load_target_adapter: instantiates the target adapter (self.target_adapter) and loads its data
        - self.calculate_diff: generates the diff from source to target adapter and stores it in self.diff
        - self.execute_sync: if not dry-run, uses the self.diff to synchronize from source to target

        This is a generic implementation that you could overwrite completely in you custom logic.
        Available instance attributes include:

        - self.sync       (Sync instance tracking this job execution)
        - self.job_result (as per Job API)
        """

        def record_memory_trace(step: str):
            """Helper function to record memory usage and reset tracemalloc stats."""
            memory_final, memory_peak = tracemalloc.get_traced_memory()
            setattr(self.sync, f"{step}_memory_final", memory_final)
            setattr(self.sync, f"{step}_memory_peak", memory_peak)
            self.sync.save()
            self.logger.info("Traced memory for %s (Final, Peak): %s bytes, %s bytes", step, memory_final, memory_peak)
            tracemalloc.clear_traces()

        if not self.sync:
            return

        if memory_profiling:
            tracemalloc.start()

        start_time = datetime.now()

        self.logger.info("Loading current data from source adapter...")
        self.load_source_adapter()
        load_source_adapter_time = datetime.now()
        self.sync.source_load_time = load_source_adapter_time - start_time
        self.sync.save()
        self.logger.info("Source Load Time from %s: %s", self.source_adapter, self.sync.source_load_time)
        if memory_profiling:
            record_memory_trace("source_load")

        self.logger.info("Loading current data from target adapter...")
        self.load_target_adapter()
        load_target_adapter_time = datetime.now()
        self.sync.target_load_time = load_target_adapter_time - load_source_adapter_time
        self.sync.save()
        self.logger.info("Target Load Time from %s: %s", self.target_adapter, self.sync.target_load_time)
        if memory_profiling:
            record_memory_trace("target_load")

        self.logger.info("Calculating diffs...")
        self.calculate_diff()
        calculate_diff_time = datetime.now()
        self.sync.diff_time = calculate_diff_time - load_target_adapter_time
        self.sync.save()
        self.logger.info("Diff Calculation Time: %s", self.sync.diff_time)
        if memory_profiling:
            record_memory_trace("diff")

        if self.dryrun:
            self.logger.info("As `dryrun` is set, skipping the actual data sync.")
        else:
            self.logger.info("Syncing from %s to %s...", self.source_adapter, self.target_adapter)
            self.execute_sync()
            execute_sync_time = datetime.now()
            self.sync.sync_time = execute_sync_time - calculate_diff_time
            self.sync.save()
            self.logger.info("Sync complete")
            self.logger.info("Sync Time: %s", self.sync.sync_time)
            if memory_profiling:
                record_memory_trace("sync")

    def lookup_object(self, model_name, unique_id) -> Optional[BaseModel]:  # pylint: disable=unused-argument
        """Look up the Nautobot record, if any, identified by the args.

        Optional helper method used to build more detailed/accurate SyncLogEntry records from DiffSync logs.

        Args:
            model_name (str): DiffSyncModel class name or similar class/model label.
            unique_id (str): DiffSyncModel unique_id or similar unique identifier.

        Returns:
            Optional[BaseModel]: Nautobot model instance, or None
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
        """Extend Job._get_vars to include `dryrun` variable.

        Workaround for https://github.com/netbox-community/netbox/issues/5529
        """
        got_vars = super()._get_vars()
        if hasattr(cls, "dryrun"):
            got_vars["dryrun"] = cls.dryrun

        if hasattr(cls, "memory_profiling"):
            got_vars["memory_profiling"] = cls.memory_profiling
        return got_vars

    def __init__(self):
        """Initialize a Job."""
        super().__init__()
        self.sync = None
        self.diff = None
        self.source_adapter = None
        self.target_adapter = None
        # Default diffsync flags. You can overwrite them at any time.
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE | DiffSyncFlags.LOG_UNCHANGED_RECORDS

    @classmethod
    def as_form(cls, data=None, files=None, initial=None, approval_view=False):
        """Render this instance as a Django form for user inputs, including a "Dry run" field."""
        form = super().as_form(data=data, files=files, initial=initial, approval_view=approval_view)
        # Set the "dryrun" widget's initial value based on our Meta attribute, if any
        form.fields["dryrun"].initial = getattr(cls.Meta, "dryrun_default", True)
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

    def run(self, dryrun, memory_profiling, *args, **kwargs):  # pylint:disable=arguments-differ
        """Job entry point from Nautobot - do not override!"""
        self.sync = Sync.objects.create(
            source=self.data_source,
            target=self.data_target,
            dry_run=dryrun,
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
        self.sync_data(memory_profiling)


# pylint: disable=abstract-method
class DataSource(DataSyncBaseJob):
    """Base class for Jobs that sync data **from** another data source **to** Nautobot."""

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

    @classproperty
    def data_source(cls):
        """For a DataTarget this is always Nautobot."""
        return "Nautobot"

    @classproperty
    def data_source_icon(cls):
        """For a DataTarget this is always the Nautobot logo."""
        return static("img/nautobot_logo.png")
