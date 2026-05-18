"""Bulk-write pipeline benchmark for the Infoblox SSoT integration.

Runs the same 4-phase pipeline as test_infoblox_full_pipeline.py but
uses BulkNautobotAdapter (bulk_create / bulk_update) instead of the
per-object validated_save() path.

Meant to be run alongside the baseline to measure the improvement:

    invoke unittest --pattern "TestInfobloxFullPipelineMedium|TestInfobloxBulkPipelineMedium" --verbose

Phase 4 timing is where the difference appears:
    baseline:  validated_save() × N  — N DB round-trips
    bulk:      bulk_create() × ceil(N/250)  — far fewer round-trips
"""

import time
import tracemalloc

from django.contrib.contenttypes.models import ContentType
from django.test import TransactionTestCase
from nautobot.extras.models import Status
from nautobot.ipam.models import VLAN, IPAddress, Namespace, Prefix, VLANGroup
from unittest.mock import Mock

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices, FixedAddressTypeChoices
from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot_bulk import BulkNautobotAdapter

from .mock_client import MockInfobloxClient

SCALES = {
    "tiny": dict(num_namespaces=1, prefixes_per_namespace=3, ips_per_prefix=20),
    "small": dict(num_namespaces=1, prefixes_per_namespace=5, ips_per_prefix=50),
    "medium": dict(num_namespaces=3, prefixes_per_namespace=10, ips_per_prefix=100),
}


def _make_config(network_views: list, default_status) -> Mock:
    cfg = Mock()
    cfg.import_ipv4 = True
    cfg.import_ipv6 = False
    cfg.import_subnets = True
    cfg.import_ip_addresses = True
    cfg.import_vlan_views = False
    cfg.import_vlans = False
    cfg.cf_fields_ignore = {"extensible_attributes": [], "custom_fields": []}
    cfg.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
    cfg.dns_record_type = DNSRecordTypeChoices.A_RECORD
    cfg.nautobot_deletable_models = []
    cfg.default_status = default_status
    cfg.enable_sync_to_infoblox = False
    cfg.infoblox_sync_filters = [{"network_view": nv} for nv in network_views]
    cfg.infoblox_network_view_to_namespace_map = {nv: f"ns-{nv}" for nv in network_views}
    return cfg


def _make_job() -> Mock:
    job = Mock()
    job.debug = False
    return job


class _InfobloxBulkPipelineBase(TransactionTestCase):
    """Base class — do not run directly."""

    SCALE = None

    def setUp(self):
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        for model in [IPAddress, Prefix, VLAN, VLANGroup, Namespace]:
            self.status_active.content_types.add(ContentType.objects.get_for_model(model))

    def _run_pipeline(self):
        client = MockInfobloxClient(**SCALES[self.SCALE])
        expected = client.expected_counts
        nv_names = [nv["name"] for nv in client.get_network_views()]
        config = _make_config(nv_names, default_status=self.status_active)
        job = _make_job()

        # Phase 1: Load from Infoblox (mock)
        tracemalloc.start()
        t0 = time.perf_counter()
        src = InfobloxAdapter(job=job, sync=None, conn=client, config=config)
        src.load()
        t_src = time.perf_counter() - t0
        _, peak_src_mb = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Phase 2: Load from Nautobot (empty DB)
        t0 = time.perf_counter()
        dst = BulkNautobotAdapter(job=job, sync=None, config=config)
        dst.load()
        t_dst = time.perf_counter() - t0

        src_objects = sum(len(v) for v in src.dict().values())

        # Phase 3: Diff
        tracemalloc.start()
        t0 = time.perf_counter()
        diff = src.diff_to(dst)
        t_diff = time.perf_counter() - t0
        _, peak_diff_mb = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        diff_summary = diff.dict()
        creates = sum(len(v.get("+", {})) for v in diff_summary.values())

        # Phase 4: Sync (bulk_create / bulk_update — far fewer round-trips)
        t0 = time.perf_counter()
        src.sync_to(dst)
        t_sync = time.perf_counter() - t0

        total = t_src + t_dst + t_diff + t_sync

        print(
            f"\n{'='*62}\n"
            f"  SCALE : {self.SCALE.upper()}  [BULK]\n"
            f"{'='*62}\n"
            f"  Expected objects   : {expected['total']:,}\n"
            f"  Source loaded      : {src_objects:,}\n"
            f"  Diff creates       : {creates:,}\n"
            f"\n"
            f"  Phase 1 src load   : {t_src:.3f}s   (peak {peak_src_mb/1024/1024:.1f} MB)\n"
            f"  Phase 2 dst load   : {t_dst:.3f}s\n"
            f"  Phase 3 diff       : {t_diff:.3f}s   (peak {peak_diff_mb/1024/1024:.1f} MB)\n"
            f"  Phase 4 sync→DB    : {t_sync:.3f}s   ← bulk_create() batches\n"
            f"  ──────────────────────────────────────\n"
            f"  TOTAL              : {total:.3f}s\n"
        )

        return {
            "t_src": t_src,
            "t_dst": t_dst,
            "t_diff": t_diff,
            "t_sync": t_sync,
            "creates": creates,
            "src_objects": src_objects,
        }

    def test_full_pipeline(self):
        result = self._run_pipeline()
        self.assertGreater(result["creates"], 0)
        self.assertGreater(result["src_objects"], 0)


class TestInfobloxBulkPipelineTiny(_InfobloxBulkPipelineBase):
    """1 NS × 3 prefixes × 20 IPs  ≈ 80 objects."""

    SCALE = "tiny"


class TestInfobloxBulkPipelineSmall(_InfobloxBulkPipelineBase):
    """1 NS × 5 prefixes × 50 IPs  ≈ 325 objects."""

    SCALE = "small"


class TestInfobloxBulkPipelineMedium(_InfobloxBulkPipelineBase):
    """3 NS × 10 prefixes × 100 IPs  ≈ 3,300 objects."""

    SCALE = "medium"
