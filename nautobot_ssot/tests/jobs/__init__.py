from nautobot_ssot.jobs import DataSource as _DataSource, DataTarget as _DataTarget
from nautobot_ssot.jobs.base import DataSyncBaseJob as _DataSyncBaseJob
from nautobot.extras.jobs import Job


class DataSyncBaseJob(_DataSyncBaseJob, Job):
    pass


class DataSource(_DataSource, Job):
    pass


class DataTarget(_DataTarget, Job):
    pass
