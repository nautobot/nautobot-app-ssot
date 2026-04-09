"""Helpers for preparing Nautobot Job models in tests."""

from nautobot.apps.utils import refresh_job_model_from_job_class
from nautobot.core.celery import register_jobs
from nautobot.extras.models import Job, JobQueue


def get_test_job_model(job_class):
    """Ensure a Job class is registered and has a corresponding Job model row."""
    register_jobs(job_class)
    job_model, _ = refresh_job_model_from_job_class(Job, job_class, JobQueue)
    return job_model
