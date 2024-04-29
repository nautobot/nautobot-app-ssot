"""Override of classes."""

from nautobot.extras.jobs import Job
from nautobot_ssot.jobs import DataSource as _DataSource, DataTarget as _DataTarget
from nautobot_ssot.jobs.base import DataSyncBaseJob as _DataSyncBaseJob


class DataSyncBaseJob(_DataSyncBaseJob, Job):  # pylint: disable=abstract-method
    """DataSyncBaseJob import of the sync base job and Nautobot Job."""


class DataSource(_DataSource, Job):  # pylint: disable=abstract-method
    """DataSource import of the DataSource job and Nautobot Job."""


class DataTarget(_DataTarget, Job):  # pylint: disable=abstract-method
    """DataSyncBaseJob import of the DataTarget job and Nautobot Job."""
