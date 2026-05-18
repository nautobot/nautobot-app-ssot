"""Baseline performance tests for the Infoblox SSoT adapter.

These tests measure the current (unoptimized) performance of
InfobloxAdapter.load() at three scales: small, medium, and large.
They make no assertions about speed — the printed output IS the point.

Run all three scales:
    invoke unittest --label nautobot_ssot.tests.infoblox.performance --verbose

Run a single scale (e.g. large only):
    invoke unittest --pattern TestInfobloxBaselineLarge --verbose
"""

import time
import tracemalloc
import unittest
from unittest.mock import Mock

from nautobot_ssot.integrations.infoblox.choices import FixedAddressTypeChoices
from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter

from .mock_client import MockInfobloxClient

# ---------------------------------------------------------------------------
# Scale definitions
# ---------------------------------------------------------------------------
#
#  small  — 1 NS × 5 prefixes × 50 IPs   → ~325 total objects
#  medium — 3 NS × 10 prefixes × 100 IPs → ~3,300 total objects
#  large  — 5 NS × 20 prefixes × 200 IPs → ~22,000 total objects
#
SCALES = {
    "small": dict(num_namespaces=1, prefixes_per_namespace=5, ips_per_prefix=50),
    "medium": dict(num_namespaces=3, prefixes_per_namespace=10, ips_per_prefix=100),
    "large": dict(num_namespaces=5, prefixes_per_namespace=20, ips_per_prefix=200),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(network_views: list) -> Mock:
    """Minimal mock of SSOTInfobloxConfig used by InfobloxAdapter."""
    cfg = Mock()
    cfg.import_ipv4 = True
    cfg.import_ipv6 = False
    cfg.import_subnets = True
    cfg.import_ip_addresses = True
    cfg.import_vlan_views = False
    cfg.import_vlans = False
    cfg.cf_fields_ignore = {"extensible_attributes": []}
    cfg.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
    cfg.infoblox_sync_filters = [{"network_view": nv} for nv in network_views]
    cfg.infoblox_network_view_to_namespace_map = {nv: f"ns-{nv}" for nv in network_views}
    return cfg


def _make_job() -> Mock:
    job = Mock()
    job.debug = False
    return job


def _run_load(scale: str) -> dict:
    """Instantiate the adapter with mock data and time adapter.load()."""
    client = MockInfobloxClient(**SCALES[scale])
    expected = client.expected_counts
    nv_names = [nv["name"] for nv in client.get_network_views()]

    adapter = InfobloxAdapter(
        job=_make_job(),
        sync=Mock(),
        conn=client,
        config=_make_config(nv_names),
    )

    tracemalloc.start()
    t0 = time.perf_counter()
    adapter.load()
    elapsed = time.perf_counter() - t0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    loaded_by_type = {k: len(v) for k, v in adapter.dict().items()}
    total_loaded = sum(loaded_by_type.values())

    print(
        f"\n{'='*60}\n"
        f"  SCALE: {scale.upper()}\n"
        f"{'='*60}\n"
        f"  Expected objects : {expected['total']:,}\n"
        f"  Loaded objects   : {total_loaded:,}\n"
        f"  Breakdown        : {loaded_by_type}\n"
        f"  Load time        : {elapsed:.3f}s\n"
        f"  Peak memory      : {peak_bytes / 1024 / 1024:.1f} MB\n"
    )

    return {
        "elapsed": elapsed,
        "peak_mb": peak_bytes / 1024 / 1024,
        "total_loaded": total_loaded,
        "by_type": loaded_by_type,
    }


# ---------------------------------------------------------------------------
# Test classes — one per scale so they can be run independently
# ---------------------------------------------------------------------------


class TestInfobloxBaselineSmall(unittest.TestCase):
    """1 namespace × 5 prefixes × 50 IPs  ≈ 325 total objects."""

    def test_load(self):
        result = _run_load("small")
        self.assertGreater(result["total_loaded"], 0)


class TestInfobloxBaselineMedium(unittest.TestCase):
    """3 namespaces × 10 prefixes × 100 IPs  ≈ 3,300 total objects."""

    def test_load(self):
        result = _run_load("medium")
        self.assertGreater(result["total_loaded"], 0)


class TestInfobloxBaselineLarge(unittest.TestCase):
    """5 namespaces × 20 prefixes × 200 IPs  ≈ 22,000 total objects."""

    def test_load(self):
        result = _run_load("large")
        self.assertGreater(result["total_loaded"], 0)
