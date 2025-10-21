"""App provision of Nautobot Job subclasses."""

import logging

from django.conf import settings
from nautobot.core.celery import register_jobs
from nautobot.core.settings_funcs import is_truthy
from nautobot.extras.models import Job

from nautobot_ssot.exceptions import JobException
from nautobot_ssot.integrations.utils import each_enabled_integration_module
from nautobot_ssot.jobs.base import DataSource, DataTarget
from nautobot_ssot.jobs.examples import ExampleDataSource, ExampleDataTarget

logger = logging.getLogger("nautobot.ssot")

hide_jobs_setting = settings.PLUGINS_CONFIG["nautobot_ssot"].get("hide_example_jobs", False)
if is_truthy(hide_jobs_setting):
    jobs = []
else:
    jobs = [ExampleDataSource, ExampleDataTarget]


def _add_integrations():
    for module in each_enabled_integration_module("jobs"):
        for job in module.jobs:
            if job in jobs:
                raise JobException(message=f"Job {job} already exists in jobs list for integration {module.__file__}.")
            logger.debug("Registering job %s from %s", job, module.__file__)
            jobs.append(job)


_add_integrations()
register_jobs(*jobs)


def get_data_jobs():
    """Get all data-source and data-target jobs available."""
    sync_jobs = Job.objects.all()
    data_sources = []
    data_targets = []
    for job in sync_jobs:
        if job.job_class is None or not issubclass(job.job_class, (DataSource, DataTarget)):
            continue
        if issubclass(job.job_class, DataSource):
            data_sources.append(job)
        if issubclass(job.job_class, DataTarget):
            data_targets.append(job)

    return (data_sources, data_targets)
