"""Nautobot SSoT framework level metrics."""
from django.conf import settings
from prometheus_client.core import GaugeMetricFamily
from nautobot_ssot.models import Sync

PLUGIN_SETTINGS = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})


def metric_ssot_jobs():
    """Extracts duration of latest SSoT Job run.

    Yields:
        GaugeMetricFamily: Prometheus Metrics
    """
    ssot_job_durations = GaugeMetricFamily(
        "nautobot_ssot_duration_seconds", "Nautobot SSoT Job Segment Duration in seconds", labels=["seconds"]
    )

    last_sync = Sync.objects.last()

    ssot_job_durations.add_metric(
        labels=["source_load_time"],
        value=last_sync.source_load_time,
    )

    ssot_job_durations.add_metric(
        labels=["target_load_time"],
        value=last_sync.target_load_time,
    )

    ssot_job_durations.add_metric(
        labels=["diff_time"],
        value=last_sync.diff_time,
    )

    ssot_job_durations.add_metric(
        labels=["total_sync_time"],
        value=last_sync.sync_time,
    )

    yield ssot_job_durations


def metric_syncs():
    """Calculate total number of Syncs.

    Yields:
        GaugeMetricFamily: Prometheus Metrics
    """
    sync_gauge = GaugeMetricFamily("nautobot_ssot_sync_total", "Nautobot SSoT Jobs", labels=["syncs"])

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
