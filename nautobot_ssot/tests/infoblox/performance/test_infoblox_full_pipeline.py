"""Full pipeline baseline performance test for the Infoblox SSoT integration.

Runs the complete 4-phase sync against a real (test) Nautobot database:

    Phase 1 — InfobloxAdapter.load()     reads from mock Infoblox client
    Phase 2 — NautobotAdapter.load()     reads existing Nautobot DB (starts empty)
    Phase 3 — src.diff_to(dst)           builds the in-memory diff tree
    Phase 4 — src.sync_to(dst)           writes creates/updates/deletes to Nautobot DB
                                          ↑ this is where validated_save() fires per object

Uses TransactionTestCase so commits actually hit the DB — TestCase wraps
everything in a rolled-back transaction which would hide the real write cost.

Run all scales:
    invoke unittest --label nautobot_ssot.tests.infoblox.performance --verbose

Run one scale:
    invoke unittest --pattern TestInfobloxFullPipelineMedium --verbose
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
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter

from .mock_client import MockInfobloxClient

# ---------------------------------------------------------------------------
# Scale definitions
# ---------------------------------------------------------------------------
#
#  tiny   — 1 NS × 3 prefixes × 20 IPs  →   ~80 objects  (quick iteration)
#  small  — 1 NS × 5 prefixes × 50 IPs  →  ~325 objects
#  medium — 3 NS × 10 prefixes × 100 IPs → ~3,300 objects (clearly painful)
#
SCALES = {
    "tiny": dict(num_namespaces=1, prefixes_per_namespace=3, ips_per_prefix=20),
    "small": dict(num_namespaces=1, prefixes_per_namespace=5, ips_per_prefix=50),
    "medium": dict(num_namespaces=3, prefixes_per_namespace=10, ips_per_prefix=100),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(network_views: list, default_status) -> Mock:
    """Build a mock SSOTInfobloxConfig suitable for a full sync pipeline."""
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


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------


class _InfobloxFullPipelineBase(TransactionTestCase):
    """Base class — do not run directly."""

    SCALE = None  # subclasses set this

    def setUp(self):
        """Create the minimum Nautobot base data required for the sync."""
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        for model in [IPAddress, Prefix, VLAN, VLANGroup, Namespace]:
            self.status_active.content_types.add(ContentType.objects.get_for_model(model))

    def _run_pipeline(self):
        client = MockInfobloxClient(**SCALES[self.SCALE])
        expected = client.expected_counts
        nv_names = [nv["name"] for nv in client.get_network_views()]
        config = _make_config(nv_names, default_status=self.status_active)
        job = _make_job()

        # ------------------------------------------------------------------
        # Phase 1: Load from Infoblox (mock client, no DB)
        # ------------------------------------------------------------------
        tracemalloc.start()
        t0 = time.perf_counter()
        src = InfobloxAdapter(job=job, sync=None, conn=client, config=config)
        src.load()
        t_src = time.perf_counter() - t0
        _, peak_src_mb = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # ------------------------------------------------------------------
        # Phase 2: Load from Nautobot (real DB, starts empty)
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        dst = NautobotAdapter(job=job, sync=None, config=config)
        dst.load()
        t_dst = time.perf_counter() - t0

        src_objects = sum(len(v) for v in src.dict().values())
        dst_objects = sum(len(v) for v in dst.dict().values())

        # ------------------------------------------------------------------
        # Phase 3: Diff (builds in-memory diff tree)
        # ------------------------------------------------------------------
        tracemalloc.start()
        t0 = time.perf_counter()
        diff = src.diff_to(dst)
        t_diff = time.perf_counter() - t0
        _, peak_diff_mb = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        diff_summary = diff.dict()
        creates = sum(len(v.get("+", {})) for v in diff_summary.values())

        # ------------------------------------------------------------------
        # Phase 4: Sync (writes to Nautobot DB — validated_save() per object)
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        src.sync_to(dst)
        t_sync = time.perf_counter() - t0

        total = t_src + t_dst + t_diff + t_sync

        print(
            f"\n{'='*62}\n"
            f"  SCALE : {self.SCALE.upper()}\n"
            f"{'='*62}\n"
            f"  Expected objects   : {expected['total']:,}\n"
            f"  Source loaded      : {src_objects:,}\n"
            f"  Target loaded      : {dst_objects:,}  (DB was empty)\n"
            f"  Diff creates       : {creates:,}\n"
            f"\n"
            f"  Phase 1 src load   : {t_src:.3f}s   (peak {peak_src_mb/1024/1024:.1f} MB)\n"
            f"  Phase 2 dst load   : {t_dst:.3f}s\n"
            f"  Phase 3 diff       : {t_diff:.3f}s   (peak {peak_diff_mb/1024/1024:.1f} MB)\n"
            f"  Phase 4 sync→DB    : {t_sync:.3f}s   ← validated_save() × {creates:,}\n"
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


# ---------------------------------------------------------------------------
# One class per scale so they can be filtered individually
# ---------------------------------------------------------------------------


class TestInfobloxFullPipelineTiny(_InfobloxFullPipelineBase):
    """1 NS × 3 prefixes × 20 IPs  ≈ 80 objects. Quick sanity check."""

    SCALE = "tiny"


class TestInfobloxFullPipelineSmall(_InfobloxFullPipelineBase):
    """1 NS × 5 prefixes × 50 IPs  ≈ 325 objects."""

    SCALE = "small"


class TestInfobloxFullPipelineMedium(_InfobloxFullPipelineBase):
    """3 NS × 10 prefixes × 100 IPs  ≈ 3,300 objects. Clearly shows the per-save cost."""

    SCALE = "medium"
