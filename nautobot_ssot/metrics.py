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
        last_job_sync = Sync.objects.filter(job_result__job_model_id=job.id).last()
        if last_job_sync:
            if last_job_sync.source_load_time:
                ssot_job_durations.add_metric(
                    labels=["source_load_time", job.slug],
                    value=(last_job_sync.source_load_time.seconds * 100000)
                    + last_job_sync.source_load_time.microseconds,
                )

            if last_job_sync.target_load_time:
                ssot_job_durations.add_metric(
                    labels=["target_load_time", job.slug],
                    value=(last_job_sync.target_load_time.seconds * 1000000)
                    + last_job_sync.target_load_time.microseconds,
                )

            if last_job_sync.diff_time:
                ssot_job_durations.add_metric(
                    labels=["diff_time", job.slug],
                    value=(last_job_sync.diff_time.seconds * 1000000) + last_job_sync.diff_time.microseconds,
                )

            if last_job_sync.sync_time:
                ssot_job_durations.add_metric(
                    labels=["sync_time", job.slug],
                    value=(last_job_sync.sync_time.seconds * 1000000) + last_job_sync.sync_time.microseconds,
                )

            if last_job_sync.duration:
                ssot_job_durations.add_metric(
                    labels=["sync_duration", job.slug],
                    value=(last_job_sync.duration.seconds * 1000000) + last_job_sync.duration.microseconds,
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


def metric_sync_operations():
    """Extracts the diff summary operations from each Job's last Sync.

    Yields:
        GuageMetricFamily: Prometheus Metrics
    """
    sync_ops = GaugeMetricFamily(
        "nautobot_ssot_sync_operations", "Nautobot SSoT operations by Job", labels=["job", "operation"]
    )

    for job in Job.objects.filter(slug__icontains="ssot"):
        last_job_sync = Sync.objects.filter(job_result__job_model_id=job.id).last()
        if last_job_sync and last_job_sync.summary:
            for operation, value in last_job_sync.summary.items():
                sync_ops.add_metric(
                    labels=[job.slug, operation],
                    value=value,
                )

    yield sync_ops


def metric_memory_usage():
    """Extracts memory usage for latest SSoT Sync where memory profiling was used.

    Yields:
        GaugeMetricFamily: Prometheus Metrics
    """
    memory_gauge = GaugeMetricFamily(
        "nautobot_ssot_sync_memory_usage", "Nautobot SSoT Sync Memory Usage", labels=["phase"]
    )

    last_sync = Sync.objects.filter(source_load_memory_final__isnull=False).last()

    if last_sync:
        memory_gauge.add_metric(
            labels=["source_load_memory_final"],
            value=last_sync.source_load_memory_final,
        )

        memory_gauge.add_metric(
            labels=["source_load_memory_peak"],
            value=last_sync.source_load_memory_peak,
        )

        memory_gauge.add_metric(
            labels=["target_load_memory_final"],
            value=last_sync.target_load_memory_final,
        )

        memory_gauge.add_metric(
            labels=["target_load_memory_peak"],
            value=last_sync.target_load_memory_peak,
        )

        memory_gauge.add_metric(
            labels=["diff_memory_final"],
            value=last_sync.diff_memory_final,
        )

        memory_gauge.add_metric(
            labels=["diff_memory_peak"],
            value=last_sync.diff_memory_peak,
        )

        memory_gauge.add_metric(
            labels=["sync_memory_final"],
            value=last_sync.sync_memory_final,
        )

        memory_gauge.add_metric(
            labels=["sync_memory_peak"],
            value=last_sync.sync_memory_peak,
        )

    yield memory_gauge


metrics = [metric_ssot_jobs, metric_syncs, metric_sync_operations, metric_memory_usage]
