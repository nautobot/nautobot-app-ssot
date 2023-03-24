"""Nautobot SSoT framework level metrics."""
from django.conf import settings
from prometheus_client.core import GaugeMetricFamily
from nautobot.extras.models.jobs import Job
from nautobot_ssot.models import Sync

PLUGIN_SETTINGS = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})


def metric_ssot_jobs():
    """Extracts duration of latest SSoT Job run.

    Yields:
        GaugeMetricFamily: Prometheus Metrics
    """
    ssot_job_durations = GaugeMetricFamily(
        "nautobot_ssot_duration_seconds",
        "Nautobot SSoT Job Phase Duration in microseconds",
        labels=["phase", "job"],
    )

    for job in Job.objects.filter(slug__icontains="ssot"):
        ssot_job_durations.add_metric(
            labels=["source_load_time", job.slug],
            value=Sync.objects.filter(job_result__job_model_id=job.id).last().source_load_time.micoseconds,
        )

        ssot_job_durations.add_metric(
            labels=["target_load_time", job.slug],
            value=Sync.objects.filter(job_result__job_model_id=job.id).last().target_load_time.microseconds,
        )

        ssot_job_durations.add_metric(
            labels=["diff_time", job.slug],
            value=Sync.objects.filter(job_result__job_model_id=job.id).last().diff_time.microseconds,
        )

        ssot_job_durations.add_metric(
            labels=["total_sync_time", job.slug],
            value=Sync.objects.filter(job_result__job_model_id=job.id).last().sync_time.microseconds,
        )

    yield ssot_job_durations


def metric_syncs():
    """Calculate total number of Syncs.

    Yields:
        GaugeMetricFamily: Prometheus Metrics
    """
    sync_gauge = GaugeMetricFamily("nautobot_ssot_sync_totals", "Nautobot SSoT Sync Totals", labels=["sync_type"])

    sync_gauge.add_metric(labels=["total_syncs"], value=Sync.objects.all().count())

    sync_gauge.add_metric(
        labels=["completed_syncs"],
        value=Sync.objects.filter(job_result__status="completed").count(),
    )

    sync_gauge.add_metric(labels=["failed_syncs"], value=Sync.objects.filter(job_result__status="failed").count())

    sync_gauge.add_metric(labels=["errored_syncs"], value=Sync.objects.filter(job_result__status="errored").count())

    sync_gauge.add_metric(labels=["pending_syncs"], value=Sync.objects.filter(job_result__status="pending").count())

    sync_gauge.add_metric(labels=["running_syncs"], value=Sync.objects.filter(job_result__status="running").count())

    yield sync_gauge


metrics = [metric_ssot_jobs, metric_syncs]
