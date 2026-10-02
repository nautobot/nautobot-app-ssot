"""Helpers for preparing Nautobot Job models in tests."""

from datetime import datetime

from nautobot.apps.utils import refresh_job_model_from_job_class
from nautobot.core.celery import register_jobs
from nautobot.extras.models import Job, JobQueue, JobResult

from nautobot_ssot.models import Sync


def get_test_job_model(job_class):
    """Ensure a Job class is registered and has a corresponding Job model row."""
    register_jobs(job_class)
    job_model, _ = refresh_job_model_from_job_class(Job, job_class, JobQueue)
    return job_model


def create_example_sync(source="Example Data Source", target="Nautobot", job_result=None, **overrides):
    """Create a Sync (and a backing JobResult if not supplied) for tests.

    Args:
        source (str): Sync source label.
        target (str): Sync target label.
        job_result (JobResult): Existing JobResult to attach; one is created if omitted.
        **overrides: Additional Sync field values (e.g. ``diff``, ``summary``, timing fields).
    """
    if job_result is None:
        job_result = JobResult.objects.create(name="ExampleDataSource", task_name="example", worker="default")
    fields = {"source": source, "target": target, "start_time": datetime.now(), "dry_run": False, "diff": {}}
    fields.update(overrides)
    return Sync.objects.create(job_result=job_result, **fields)
