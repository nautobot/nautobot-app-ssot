"""Base Job classes for sync workers."""

from django.forms import HiddenInput
from django.utils import timezone

import structlog

from nautobot.extras.jobs import BaseJob, BooleanVar

from nautobot_ssot.choices import SyncLogEntryActionChoices
from nautobot_ssot.models import Sync, SyncLogEntry


class DataSyncBaseJob(BaseJob):
    """Common base class for data synchronization jobs.

    Works mostly as per the BaseJob API, with the following changes:

    - Concrete subclasses are responsible for implementing `self.sync_data()`, **not** `self.run()`.
    - Additional Meta field `dry_run_default` is available to be defined if desired.
    - Meta fields `data_source` and `data_target` can be defined for lookup purposes
    """

    dry_run = BooleanVar()

    def sync_data(self):
        """Method to be implemented by data sync concrete Job implementations.

        Available instance attributes include:

        - self.kwargs     (corresponds to the Job's `data` input, including 'dry_run' option)
        - self.commit     (should generally be True)
        - self.sync       (Sync instance tracking this job execution)
        - self.job_result (as per Job API)
        """
        pass

    def lookup_object(self, model_name, unique_id):
        """Look up the Nautobot record and associated ObjectChange, if any, identified by the args.

        Optional helper method used to build more detailed/accurate SyncLogEntry records from DiffSync logs.

        Args:
            model_name (str): DiffSyncModel class name or similar class/model label.
            unique_id (str): DiffSyncModel unique_id or similar unique identifier.

        Returns:
            tuple: (nautobot_record, nautobot_objectchange_record). Either or both may be None.
        """
        return (None, None)

    def sync_log(
        self,
        action,
        status,
        message="",
        diff=None,
        synced_object=None,
        object_repr=None,
        object_change=None,
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
            object_change=object_change,
        )

    def _structlog_to_sync_log_entry(self, _logger, _log_method, event_dict):
        """Capture certain structlog messages from DiffSync into the Nautobot database."""
        if all(key in event_dict for key in ("src", "dst", "action", "model", "unique_id", "diffs", "status")):
            # The DiffSync log gives us a model name (string) and unique_id (string).
            # Try to look up the actual Nautobot object that this describes.
            synced_object, object_change = self.lookup_object(event_dict["model"], event_dict["unique_id"])
            self.sync_log(
                action=event_dict["action"] or SyncLogEntryActionChoices.ACTION_NO_CHANGE,
                diff=event_dict["diffs"] if event_dict["action"] else None,
                status=event_dict["status"],
                message=event_dict["event"],
                synced_object=synced_object,
                object_change=object_change,
            )

        return event_dict

    @classmethod
    def _get_vars(cls):
        """Extend Job._get_vars() to include `dry_run` variable.

        Workaround for https://github.com/netbox-community/netbox/issues/5529
        """
        vars = super()._get_vars()
        if hasattr(cls, "dry_run"):
            vars['dry_run'] = cls.dry_run
        return vars

    def as_form(self, data=None, files=None, initial=None):
        """Render this instance as a Django form for user inputs, including a "Dry run" field."""
        form = super().as_form(data=data, files=files, initial=initial)
        # Set the "dry_run" widget's initial value based on our Meta attribute, if any
        form.fields["dry_run"].initial = getattr(self.Meta, "dry_run_default", True)
        # Hide the "commit" widget to reduce user confusion
        form.fields["_commit"].widget = HiddenInput()
        return form

    @property
    def data_source(self):
        """The system or data source providing input data for this sync."""
        return getattr(self.Meta, "data_source", self.name)

    @property
    def data_target(self):
        """The system or data source being modified by this sync."""
        return getattr(self.Meta, "data_target", self.name)

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

        self.sync_data()


class DataSource(DataSyncBaseJob):
    """Base class for Jobs that sync data **from** another data source **to** Nautobot."""

    dry_run = BooleanVar(description="Perform a dry-run, making no actual changes to Nautobot data.")

    @property
    def data_target(self):
        return "Nautobot"


class DataTarget(DataSyncBaseJob):
    """Base class for Jobs that sync data **to** another data target **from** Nautobot."""

    dry_run = BooleanVar(description="Perform a dry-run, making no actual changes to the remote system.")

    @property
    def data_source(self):
        return "Nautobot"
