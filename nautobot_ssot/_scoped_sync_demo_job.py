"""Demo SSoT job class — uses the Infoblox mock client so the scoped-sync
API can be tested without real Infoblox credentials.

NOT a real production job. Lives here only so `scripts/test_scoped_sync_api.py`
has a stable dotted path it can pass to the API endpoint.
"""

from unittest.mock import Mock

from nautobot.extras.models import Status

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot_bulk import BulkNautobotAdapter
from nautobot_ssot.tests.infoblox.performance.mock_client import MockInfobloxClient
from nautobot_ssot.tests.infoblox.performance.test_infoblox_full_pipeline import _make_config, _make_job


class DemoInfobloxJob:
    """Stand-in for an integration's DataSyncBaseJob subclass.

    The API endpoint resolves a job class by dotted path and calls
    ``load_source_adapter()`` / ``load_target_adapter()`` on it. This
    class is the smallest possible thing that satisfies that contract.
    """

    def __init__(self):
        self.source_adapter = None
        self.target_adapter = None
        self.dryrun = False
        self.flags = None
        self.sync = None
        self.logger = _NoopLogger()

    def load_source_adapter(self):
        client = MockInfobloxClient(num_namespaces=3, prefixes_per_namespace=10, ips_per_prefix=100)
        nv_names = [nv["name"] for nv in client.get_network_views()]
        active = Status.objects.get_or_create(name="Active")[0]
        config = _make_config(nv_names, default_status=active)
        job = _make_job()
        self.source_adapter = InfobloxAdapter(job=job, sync=None, conn=client, config=config)
        self.source_adapter.load()

    def load_target_adapter(self):
        active = Status.objects.get_or_create(name="Active")[0]
        # Construct a config with the same network views the source uses
        client = MockInfobloxClient(num_namespaces=3, prefixes_per_namespace=10, ips_per_prefix=100)
        nv_names = [nv["name"] for nv in client.get_network_views()]
        config = _make_config(nv_names, default_status=active)
        job = _make_job()
        self.target_adapter = BulkNautobotAdapter(job=job, sync=None, config=config)
        self.target_adapter.load()


class _NoopLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def debug(self, *a, **kw): pass
    def exception(self, *a, **kw): pass
