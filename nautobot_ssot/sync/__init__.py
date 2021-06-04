"""Worker code for executing DataSyncWorkers."""

import logging

import pkg_resources

from django.utils import timezone

from django_rq import job
import structlog

from nautobot.extras.choices import JobResultStatusChoices, LogLevelChoices

from nautobot_ssot.choices import SyncLogEntryActionChoices


logger = logging.getLogger("rq.worker")


def log_to_log_entry(_logger, _log_method, event_dict):
    """Capture certain structlog messages from DiffSync into the Nautobot database."""
    # TODO rework this
    from nautobot_ssot.models import SyncLogEntry
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

def get_data_sources():
    """Get a list of registered sync worker data sources."""
    return sorted(
        [
            entrypoint.load() for entrypoint in pkg_resources.iter_entry_points("nautobot_ssot.data_sources")
        ],
        key=lambda worker: worker.name,
    )

def get_data_targets():
    """Get a list of registered sync worker data targets."""
    return sorted(
        [
            entrypoint.load() for entrypoint in pkg_resources.iter_entry_points("nautobot_ssot.data_targets")
        ],
        key=lambda worker: worker.name,
    )

def get_data_source(name=None, slug=None):
    """Look up the specified data source class."""
    for data_source in get_data_sources():
        if name and data_source.name != name:
            continue
        if slug and data_source.slug != slug:
            continue
        return data_source
    raise KeyError(f'No data source "{name or slug}" found!')

def get_data_target(name=None, slug=None):
    """Look up the specified data target class."""
    for data_target in get_data_targets():
        if name and data_target.name != name:
            continue
        if slug and data_target.slug != slug:
            continue
        return data_target
    raise KeyError(f'No data target "{name or slug}" found!')

@job("default")
def sync(sync_id, data):
    """Perform a requested sync."""
    # TODO rework this
    from nautobot_ssot.models import Sync
    sync = Sync.objects.get(id=sync_id)

    sync.job_result.log(
        f"START: data synchronization {sync}", grouping="sync", level_choice=LogLevelChoices.LOG_INFO, logger=logger
    )
    sync.job_result.set_status(JobResultStatusChoices.STATUS_RUNNING)
    sync.job_result.save()
    sync.start_time = timezone.now()
    sync.save()

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

        if sync.source != "Nautobot":
            sync_worker = get_data_source(name=sync.source)(sync=sync, data=data)
        else:
            sync_worker = get_data_target(name=sync.target)(sync=sync, data=data)

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
