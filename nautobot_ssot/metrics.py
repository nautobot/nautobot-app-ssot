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
        "nautobot_ssot_duration_microseconds",
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


def metric_memory_usage():
    """Extracts memory usage for latest SSoT Sync where memory profiling was used.

    Yields:
        GaugeMetricFamily: Prometheus Metrics
    """
    memory_gauge = GaugeMetricFamily(
        "nautobot_ssot_sync_memory_usage", "Nautobot SSoT Sync Memory Usage", labels=["phase"]
    )

    memory_gauge.add_metric(
        labels=["source_load_memory_final"],
        value=Sync.objects.filter(source_load_memory_final__isnull=False).last().source_load_memory_final,
    )

    memory_gauge.add_metric(
        labels=["source_load_memory_peak"],
        value=Sync.objects.filter(source_load_memory_peak__isnull=False).last().source_load_memory_peak,
    )

    memory_gauge.add_metric(
        labels=["target_load_memory_final"],
        value=Sync.objects.filter(target_load_memory_final__isnull=False).last().target_load_memory_final,
    )

    memory_gauge.add_metric(
        labels=["target_load_memory_peak"],
        value=Sync.objects.filter(target_load_memory_peak__isnull=False).last().target_load_memory_peak,
    )

    memory_gauge.add_metric(
        labels=["diff_memory_final"],
        value=Sync.objects.filter(diff_memory_final__isnull=False).last().diff_memory_final,
    )

    memory_gauge.add_metric(
        labels=["diff_memory_peak"],
        value=Sync.objects.filter(diff_memory_peak__isnull=False).last().diff_memory_peak,
    )

    memory_gauge.add_metric(
        labels=["sync_memory_final"],
        value=Sync.objects.filter(sync_memory_final__isnull=False).last().sync_memory_final,
    )

    memory_gauge.add_metric(
        labels=["sync_memory_peak"],
        value=Sync.objects.filter(sync_memory_peak__isnull=False).last().sync_memory_peak,
    )

    yield memory_gauge


metrics = [metric_ssot_jobs, metric_syncs, metric_memory_usage]
