"""Plugin provision of Nautobot Job subclasses."""

from django.conf import settings

from nautobot.extras.jobs import get_jobs

from .base import DataSource, DataTarget
from .examples import ExampleDataSource, ExampleDataTarget

if settings.PLUGINS_CONFIG["nautobot_ssot"]["hide_example_jobs"]:
    jobs = []
else:
    jobs = [ExampleDataSource, ExampleDataTarget]


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
