"""Plugin provision of Nautobot Job subclasses."""

from django.conf import settings

from nautobot.extras.jobs import get_jobs

from nautobot_ssot.integrations.utils import each_enabled_integration_module
from nautobot_ssot.utils import logger

from .base import DataSource, DataTarget
from .examples import ExampleDataSource, ExampleDataTarget

if settings.PLUGINS_CONFIG["nautobot_ssot"]["hide_example_jobs"]:
    jobs = []
else:
    jobs = [ExampleDataSource, ExampleDataTarget]


class JobException(Exception):
    """Exception raised when failure loading integration Job."""

    def __init__(self, message):
        """Populate exception information."""
        self.message = message
        super().__init__(self.message)


def _add_integrations():
    for module in each_enabled_integration_module("jobs"):
        for job in module.jobs:
            if job in jobs:
                raise JobException(message=f"Job {job} already exists in jobs list for integration {module.__file__}.")
            logger.debug("Registering job %s from %s", job, module.__file__)
            jobs.append(job)


_add_integrations()


def get_data_jobs():
    """Get all data-source and data-target jobs available."""
    jobs_dict = get_jobs()
    data_sources = []
    data_targets = []
    for modules in jobs_dict.values():
        for module_data in modules.values():
            for job_class in module_data["jobs"].values():
                if issubclass(job_class, DataSource):
                    data_sources.append(job_class)
                if issubclass(job_class, DataTarget):
                    data_targets.append(job_class)

    return (data_sources, data_targets)
