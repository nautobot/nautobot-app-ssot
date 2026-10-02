"""Tests for the framework-level Prometheus metric generators."""

import datetime
from unittest.mock import patch

from django.utils import timezone
from nautobot.apps.testing import TestCase
from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import JobResult

from nautobot_ssot.jobs.examples import ExampleDataSource
from nautobot_ssot.metrics import (
    metric_memory_usage,
    metric_ssot_jobs,
    metric_sync_operations,
    metric_syncs,
)
from nautobot_ssot.models import Sync
from nautobot_ssot.tests.utils.job_helpers import get_test_job_model


class TestSSoTMetrics(TestCase):
    """Exercise the SSoT metric generators against a fully populated Sync."""

    def setUp(self):
        """Create an SSoT Job model and a Sync with every timing/memory field populated."""
        self.job_model = get_test_job_model(ExampleDataSource)
        self.job_result = JobResult.objects.create(
            name="ExampleDataSource",
            job_model=self.job_model,
            task_name="nautobot_ssot.jobs.examples.ExampleDataSource",
            worker="default",
        )
        self.job_result.set_status(JobResultStatusChoices.STATUS_SUCCESS)
        if not self.job_result.date_done:
            self.job_result.date_done = timezone.now()
        self.job_result.save()
        self.sync = Sync.objects.create(
            source="Example Data Source",
            target="Nautobot",
            start_time=timezone.now() - datetime.timedelta(seconds=5),
            dry_run=False,
            diff={},
            summary={"create": 1, "update": 2, "delete": 0},
            job_result=self.job_result,
            source_load_time=datetime.timedelta(seconds=1),
            target_load_time=datetime.timedelta(seconds=2),
            diff_time=datetime.timedelta(seconds=1),
            sync_time=datetime.timedelta(seconds=3),
            source_load_memory_final=1024,
            source_load_memory_peak=2048,
        )

    def test_metric_ssot_jobs_emits_each_phase(self):
        """metric_ssot_jobs emits a gauge sample for every populated timing field."""
        families = list(metric_ssot_jobs())
        self.assertEqual(len(families), 1)
        phases = {sample.labels["phase"] for sample in families[0].samples}
        self.assertEqual(
            phases,
            {"source_load_time", "target_load_time", "diff_time", "sync_time", "sync_duration"},
        )

    def test_metric_syncs_counts_totals(self):
        """metric_syncs emits a total-syncs sample plus one per JobResult status."""
        families = list(metric_syncs())
        self.assertEqual(len(families), 1)
        sync_types = {sample.labels["sync_type"] for sample in families[0].samples}
        self.assertIn("total_syncs", sync_types)

    def test_metric_sync_operations_emits_summary(self):
        """metric_sync_operations emits a sample per diff-summary operation."""
        families = list(metric_sync_operations())
        operations = {sample.labels["operation"] for sample in families[0].samples}
        self.assertIn("create", operations)
        self.assertIn("update", operations)

    @patch("nautobot_ssot.metrics.get_data_jobs", return_value=([], []))
    def test_metric_sync_operations_no_data_jobs(self, _mock_get_data_jobs):
        """When no data jobs exist, a single empty placeholder sample is emitted."""
        families = list(metric_sync_operations())
        samples = list(families[0].samples)
        self.assertTrue(any(sample.labels.get("job") == "" for sample in samples))

    def test_metric_memory_usage_emits_samples(self):
        """metric_memory_usage emits a sample per summary entry for memory-profiled syncs."""
        families = list(metric_memory_usage())
        self.assertEqual(len(families), 1)
        self.assertTrue(list(families[0].samples))
