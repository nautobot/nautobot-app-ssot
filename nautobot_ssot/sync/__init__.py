"""Worker code for executing DataSyncWorkers."""

import logging

import pkg_resources

from django.utils import timezone

from django_rq import job
import structlog

from nautobot.extras.choices import JobResultStatusChoices, LogLevelChoices

from nautobot_ssot.choices import SyncLogEntryActionChoices
from nautobot_ssot.models import Sync, SyncLogEntry


logger = logging.getLogger("rq.worker")


def log_to_log_entry(_logger, _log_method, event_dict):
    """Capture certain structlog messages from DiffSync into the Nautobot database."""
    if all(key in event_dict for key in ("src", "dst", "action", "model", "unique_id", "diffs", "status")):
        sync = event_dict["src"].sync
        sync_worker = event_dict["src"].sync_worker
        object_repr = event_dict["unique_id"]
        # The DiffSync log gives us a model name (string) and unique_id (string).
        # Try to look up the actual Nautobot object that this describes.
        changed_object, object_change = sync_worker.lookup_object(event_dict["model"], event_dict["unique_id"])
        if changed_object:
            object_repr = repr(changed_object)
        SyncLogEntry.objects.create(
            sync=sync,
            action=event_dict["action"] or SyncLogEntryActionChoices.ACTION_NO_CHANGE,
            diff=event_dict["diffs"],
            status=event_dict["status"],
            message=event_dict["event"],
            changed_object=changed_object,
            object_change=object_change,
            object_repr=object_repr,
        )
    return event_dict


def get_sync_worker_classes():
    return [
        entrypoint.load() for entrypoint in pkg_resources.iter_entry_points("nautobot_ssot.sync_worker_classes")
    ]


def get_sync_worker_class(name=None, slug=None):
    """Look up the specified sync worker class."""
    for entrypoint in pkg_resources.iter_entry_points("nautobot_ssot.sync_worker_classes"):
        sync_worker_class = entrypoint.load()
        if name and sync_worker_class.name == name:
            return sync_worker_class
        if slug and sync_worker_class.slug == slug:
            return sync_worker_class
    else:
        raise KeyError(f'No registered sync worker "{name or slug}" found!')


@job("default")
def sync(sync_id, data):
    """Perform a requested sync."""
    sync = Sync.objects.get(id=sync_id)

    sync.job_result.log(
        f"START: data synchronization {sync}", grouping="sync", level_choice=LogLevelChoices.LOG_INFO, logger=logger
    )
    sync.job_result.set_status(JobResultStatusChoices.STATUS_RUNNING)
    sync.job_result.save()

    try:
        structlog.configure(
            processors=[
                log_to_log_entry,
                structlog.stdlib.render_to_log_kwargs,
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        sync_worker = get_sync_worker_class(name=sync.job_result.name)(sync=sync, data=data)

        sync_worker.execute()

    except Exception as exc:
        sync.job_result.log(
            f"Exception occurred during {sync}: {exc}",
            grouping="sync",
            level_choice=LogLevelChoices.LOG_FAILURE,
            logger=logger,
        )
        sync.job_result.set_status(JobResultStatusChoices.STATUS_FAILED)
    else:
        sync.job_result.log(
            f"FINISH: data synchronization {sync}",
            grouping="sync",
            level_choice=LogLevelChoices.LOG_INFO,
            logger=logger,
        )
        sync.job_result.set_status(JobResultStatusChoices.STATUS_COMPLETED)
    finally:
        sync.job_result.completed = timezone.now()
        sync.job_result.save()

    return {"ok": sync.job_result.status == JobResultStatusChoices.STATUS_COMPLETED}
