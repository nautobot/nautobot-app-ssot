"""Django views for Single Source of Truth (SSoT)."""

from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import render
from django.template import loader
from django.template.defaultfilters import date
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import slugify
from django.utils.timesince import timesince
from django.views import View as DjangoView
from django_tables2 import RequestConfig

try:
    from nautobot.apps.ui import EChartsBase, EChartsTypeChoices
    from nautobot.core.ui.constants import UI_COLORS
except ImportError:
    EChartsBase = None
    EChartsTypeChoices = None
    UI_COLORS = {}
from nautobot.apps.ui import (
    Breadcrumbs,
    DistinctViewTab,
    ModelBreadcrumbItem,
    ObjectDetailContent,
    ObjectFieldsPanel,
    ObjectsTablePanel,
    ObjectTextPanel,
    SectionChoices,
    Tab,
    ViewNameBreadcrumbItem,
    render_component_template,
)
from nautobot.apps.views import (
    ContentTypePermissionRequiredMixin,
    EnhancedPaginator,
    ObjectBulkDestroyViewMixin,
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListView,
    ObjectListViewMixin,
    ObjectView,
    get_obj_from_context,
)
from nautobot.core.ui.utils import flatten_context
from nautobot.core.views.paginator import get_paginate_count
from nautobot.extras.models import Job as JobModel
from rest_framework.decorators import action
from rest_framework.response import Response

from nautobot_ssot.api import serializers
from nautobot_ssot.integrations import utils
from nautobot_ssot.templatetags.render_diff import render_diff

from .choices import SyncLogEntryActionChoices
from .filters import SyncFilterSet, SyncLogEntryFilterSet
from .forms import SyncBulkEditForm, SyncFilterForm, SyncForm, SyncLogEntryFilterForm
from .jobs import get_data_jobs
from .jobs.base import DataSource, DataTarget
from .models import Sync, SyncLogEntry
from .tables import DashboardTable, SyncLogEntryTable, SyncTable, SyncTableSingleSourceOrTarget

# Friendly display names for JobResult status values
JOB_STATUS_DISPLAY = {
    "PENDING": "Pending",
    "STARTED": "Running",
    "SUCCESS": "Success",
    "FAILURE": "Failed",
    "ERROR": "Error",
    "REVOKED": "Revoked",
    "RETRY": "Retry",
    "RECEIVED": "Received",
}

# Canonical order for pie chart (determines which status gets which color)
JOB_STATUS_ORDER = [
    "Success",
    "Failed",
    "Error",
    "Running",
    "Pending",
    "Revoked",
    "Retry",
    "Received",
    "No syncs yet",
    "Unknown",
]


def _status_color(name, light, dark):
    """Get color dict from UI_COLORS or fallback to provided hex values."""
    if UI_COLORS and name in UI_COLORS:
        return UI_COLORS[name]
    return {"light": light, "dark": dark}


# Theme colors matching status semantics (green=success, red=failure, orange=in-progress, gray=neutral)
JOB_STATUS_THEME_COLORS = [
    _status_color("green", "#1ca92a", "#2ecc40"),  # Success
    _status_color("red", "#e01f1f", "#ff4c4c"),  # Failed
    _status_color("red-darker", "#731c1c", "#813131"),  # Error
    _status_color("orange", "#e07807", "#ff9933"),  # Running
    _status_color("gray", "#b0b0b0", "#828282"),  # Pending
    _status_color("red-darker", "#731c1c", "#813131"),  # Revoked
    _status_color("orange-lighter", "#f1c28f", "#ffd1a3"),  # Retry
    _status_color("gray-lighter", "#dbdbdb", "#c7c7c7"),  # Received
    _status_color("gray", "#b0b0b0", "#828282"),  # No syncs yet
    _status_color("gray-darker", "#5e5e5e", "#494949"),  # Unknown
]


def get_job_run_status_chart():
    """Build an ECharts pie chart for Job Run Status distribution.

    Returns the chart and render context, or None if ECharts is unavailable.
    """
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    status_counts = (
        Sync.objects.filter(job_result__isnull=False).values("job_result__status").annotate(count=Count("pk"))
    )

    # Build count lookup by display name
    counts_by_status = {}
    for item in status_counts:
        status_raw = item["job_result__status"] or "Unknown"
        status_display = JOB_STATUS_DISPLAY.get(status_raw, status_raw.title())
        counts_by_status[status_display] = item["count"]

    if not counts_by_status:
        counts_by_status["No syncs yet"] = 1

    # Build data in JOB_STATUS_ORDER so slice colors match status semantics
    ordered_data = {}
    for status in JOB_STATUS_ORDER:
        if status in counts_by_status and counts_by_status[status] > 0:
            ordered_data[status] = counts_by_status[status]

    chart = EChartsBase(
        chart_type=EChartsTypeChoices.PIE,
        header="Job Run Status",
        description="Distribution of sync job outcomes",
        data={"Job Run Status": ordered_data},
        theme_colors=JOB_STATUS_THEME_COLORS,
    )

    return {
        "chart": chart,
        "chart_config": chart.get_config(),
        "chart_container_id": slugify(f"echart-{chart.header}"),
        "chart_width": "100%",
        "chart_height": "24rem",
    }


def get_integration_activity_chart():
    """Build an ECharts bar chart showing sync count per integration.

    Returns the chart and render context, or None if ECharts is unavailable.
    """
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    # Count syncs by integration: source when pulling from external, target when pushing to external
    source_counts = (
        Sync.objects.filter(source__isnull=False)
        .exclude(source="Nautobot")
        .values("source")
        .annotate(count=Count("pk"))
    )
    target_counts = (
        Sync.objects.filter(target__isnull=False)
        .exclude(target="Nautobot")
        .values("target")
        .annotate(count=Count("pk"))
    )

    # Merge: integration name -> total count (source + target)
    counts_by_integration = {}
    for item in source_counts:
        counts_by_integration[item["source"]] = counts_by_integration.get(item["source"], 0) + item["count"]
    for item in target_counts:
        counts_by_integration[item["target"]] = counts_by_integration.get(item["target"], 0) + item["count"]

    if not counts_by_integration:
        return None

    # ECharts bar format: {"SeriesName": {"x1": val1, "x2": val2}}
    data = {"Syncs": dict(sorted(counts_by_integration.items(), key=lambda x: -x[1]))}

    chart = EChartsBase(
        chart_type=EChartsTypeChoices.BAR,
        header="Integration Activity",
        description="Number of sync runs per integration (data source or target)",
        data=data,
    )

    return {
        "chart": chart,
        "chart_config": chart.get_config(),
        "chart_container_id": slugify(f"echart-{chart.header}"),
        "chart_width": "100%",
        "chart_height": "24rem",
    }


def _chart_context(chart, chart_id_suffix=""):
    """Build common chart render context."""
    return {
        "chart": chart,
        "chart_config": chart.get_config(),
        "chart_container_id": slugify(f"echart-{chart.header}{chart_id_suffix}"),
        "chart_width": "100%",
        "chart_height": "24rem",
    }


def get_sync_runs_over_time_chart(days=30):
    """Build a line chart showing sync runs per day over the last N days."""
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    from django.utils import timezone

    since = timezone.now() - timedelta(days=days)
    daily_counts = (
        Sync.objects.filter(start_time__gte=since)
        .annotate(date=TruncDate("start_time"))
        .values("date")
        .annotate(count=Count("pk"))
        .order_by("date")
    )
    data = {"Syncs": {str(item["date"]): item["count"] for item in daily_counts}}
    if not data["Syncs"]:
        return None

    chart = EChartsBase(
        chart_type=EChartsTypeChoices.LINE,
        header="Sync Runs Over Time",
        description=f"Number of sync runs per day (last {days} days)",
        data=data,
    )
    return _chart_context(chart)


def get_sync_actions_chart():
    """Build a pie chart showing distribution of sync actions (create/update/delete/no-change)."""
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    action_counts = SyncLogEntry.objects.values("action").annotate(count=Count("pk")).order_by("-count")
    action_display = {
        SyncLogEntryActionChoices.ACTION_CREATE: "Creates",
        SyncLogEntryActionChoices.ACTION_UPDATE: "Updates",
        SyncLogEntryActionChoices.ACTION_DELETE: "Deletes",
        SyncLogEntryActionChoices.ACTION_NO_CHANGE: "No change",
    }
    data = {
        "Actions": {
            action_display.get(item["action"], item["action"] or "Unknown"): item["count"] for item in action_counts
        }
    }
    if not data["Actions"]:
        return None

    chart = EChartsBase(
        chart_type=EChartsTypeChoices.PIE,
        header="Sync Actions Distribution",
        description="Creates, updates, deletes, and no-change operations",
        data=data,
    )
    return _chart_context(chart)


def get_sync_duration_over_time_chart(days=30):
    """Build a line chart showing average sync duration per day over the last N days."""
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    from django.utils import timezone

    since = timezone.now() - timedelta(days=days)
    syncs = (
        Sync.objects.filter(start_time__gte=since)
        .annotate(date=TruncDate("start_time"))
        .values("date", "source_load_time", "target_load_time", "diff_time", "sync_time")
        .order_by("date")
    )

    daily_totals = defaultdict(lambda: {"sum": 0, "count": 0})
    for s in syncs:
        total = timedelta(0)
        for field in ("source_load_time", "target_load_time", "diff_time", "sync_time"):
            val = s.get(field)
            if val:
                total += val
        if total.total_seconds() > 0:
            date_key = str(s["date"])
            daily_totals[date_key]["sum"] += total.total_seconds()
            daily_totals[date_key]["count"] += 1

    data = {
        "Avg Duration (sec)": {
            d: round(v["sum"] / v["count"], 1) if v["count"] else 0 for d, v in sorted(daily_totals.items())
        }
    }
    if not data["Avg Duration (sec)"]:
        return None

    chart = EChartsBase(
        chart_type=EChartsTypeChoices.LINE,
        header="Sync Duration Over Time",
        description=f"Average sync duration per day (last {days} days)",
        data=data,
    )
    return _chart_context(chart)


def get_sync_phase_breakdown_chart(limit=10):
    """Build a stacked bar chart showing time spent in each sync phase for recent syncs."""
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    recent = list(
        Sync.objects.filter(
            source_load_time__isnull=False,
            sync_time__isnull=False,
        )
        .values("id", "source", "target", "source_load_time", "target_load_time", "diff_time", "sync_time")
        .order_by("-start_time")[:limit]
    )
    if not recent:
        return None

    # Build labels (short) and data for stacked bar
    def _to_secs(val):
        if val is None:
            return 0.0
        if hasattr(val, "total_seconds"):
            return round(val.total_seconds(), 1)
        return 0.0

    labels = []
    source_vals = []
    target_vals = []
    diff_vals = []
    sync_vals = []
    for s in reversed(recent):
        src = (s.get("source") or "?")[:8]
        tgt = (s.get("target") or "?")[:8]
        labels.append(f"{src}→{tgt}" if src != "?" or tgt != "?" else str(s.get("id", "?"))[:8])
        source_vals.append(_to_secs(s.get("source_load_time")))
        target_vals.append(_to_secs(s.get("target_load_time")))
        diff_vals.append(_to_secs(s.get("diff_time")))
        sync_vals.append(_to_secs(s.get("sync_time")))

    data = {
        "Source load": dict(zip(labels, source_vals)),
        "Target load": dict(zip(labels, target_vals)),
        "Diff calc": dict(zip(labels, diff_vals)),
        "Sync": dict(zip(labels, sync_vals)),
    }
    chart = EChartsBase(
        chart_type=EChartsTypeChoices.BAR,
        header="Sync Phase Breakdown",
        description=f"Time per phase for last {limit} syncs (seconds)",
        data=data,
    )
    return _chart_context(chart)


def get_success_failure_by_integration_chart():
    """Build a grouped bar chart showing success vs failure count per integration."""
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    # Per integration: count success and failure (the non-Nautobot side of each sync)
    syncs = Sync.objects.filter(job_result__isnull=False).values("source", "target", "job_result__status")
    integration_success = {}
    integration_failure = {}
    for s in syncs:
        integration = s["source"] if s["source"] != "Nautobot" else s["target"]
        if integration:
            if s["job_result__status"] == "SUCCESS":
                integration_success[integration] = integration_success.get(integration, 0) + 1
            elif s["job_result__status"] in ("FAILURE", "ERROR"):
                integration_failure[integration] = integration_failure.get(integration, 0) + 1

    all_integrations = sorted(set(integration_success) | set(integration_failure))
    if not all_integrations:
        return None

    success_data = {i: integration_success.get(i, 0) for i in all_integrations}
    failure_data = {i: integration_failure.get(i, 0) for i in all_integrations}
    data = {"Success": success_data, "Failed": failure_data}
    chart = EChartsBase(
        chart_type=EChartsTypeChoices.BAR,
        header="Success vs Failure by Integration",
        description="Sync outcomes per integration",
        data=data,
        theme_colors=[
            _status_color("green", "#1ca92a", "#2ecc40"),
            _status_color("red", "#e01f1f", "#ff4c4c"),
        ],
    )
    return _chart_context(chart)


def get_memory_usage_chart(limit=10):
    """Build a bar chart showing peak memory usage per sync phase for recent syncs."""
    if EChartsBase is None or EChartsTypeChoices is None:
        return None

    recent = list(
        Sync.objects.filter(source_load_memory_peak__isnull=False)
        .values(
            "id",
            "source",
            "target",
            "source_load_memory_peak",
            "target_load_memory_peak",
            "diff_memory_peak",
            "sync_memory_peak",
        )
        .order_by("-start_time")[:limit]
    )
    if not recent:
        return None

    labels = []
    source_vals = []
    target_vals = []
    diff_vals = []
    sync_vals = []
    for s in reversed(recent):
        src = (s.get("source") or "?")[:6]
        tgt = (s.get("target") or "?")[:6]
        labels.append(f"{src}→{tgt}")
        source_vals.append(round((s["source_load_memory_peak"] or 0) / 1024 / 1024, 2))  # MB
        target_vals.append(round((s["target_load_memory_peak"] or 0) / 1024 / 1024, 2))
        diff_vals.append(round((s["diff_memory_peak"] or 0) / 1024 / 1024, 2))
        sync_vals.append(round((s["sync_memory_peak"] or 0) / 1024 / 1024, 2))

    data = {
        "Source load (MB)": dict(zip(labels, source_vals)),
        "Target load (MB)": dict(zip(labels, target_vals)),
        "Diff (MB)": dict(zip(labels, diff_vals)),
        "Sync (MB)": dict(zip(labels, sync_vals)),
    }
    chart = EChartsBase(
        chart_type=EChartsTypeChoices.BAR,
        header="Memory Usage by Phase",
        description=f"Peak memory per phase for last {limit} syncs (MB)",
        data=data,
    )
    return _chart_context(chart)


def dry_run_label(value) -> str:
    """Return HTML label for dry run status."""
    badge, text = ("default", "Dry Run") if value else ("info", "Sync")
    return format_html('<span class="dry_run badge bg-{}">{}</span>', badge, text)


def datetime_with_timesince(value) -> str:
    """Return formatted datetime with timesince HTML."""
    if not value:
        return None
    return format_html(
        '{} <span class="text-muted">({} ago)</span>',
        date(value, settings.DATETIME_FORMAT),
        timesince(value),
    )


class SyncObjectPanel(ObjectFieldsPanel):
    """Custom ObjectFieldsPanel to support the rendering of sync duration."""

    def render_value(self, key, value, context):
        """Render the value for display in the table."""
        if key == "duration":
            obj = get_obj_from_context(context, self.context_object_key)
            return obj.get_duration_display()
        # TODO: If Core adds a different way to render job result status labels, use here:
        if key == "job_result__status":
            status_labels = {
                "FAILURE": ("badge bg-danger", "Failed"),
                "PENDING": ("badge bg-secondary", "Pending"),
                "STARTED": ("badge bg-warning", "Running"),
                "SUCCESS": ("badge bg-success", "Completed"),
            }
            css_class, text = status_labels.get(value, ("badge bg-secondary", "N/A"))
            return format_html('<span class="{}">{}</span>', css_class, text)
        return super().render_value(key, value, context)


class StatisticsObjectPanel(ObjectFieldsPanel):
    """Custom ObjectFieldsPanel to support the rendering of sync statistics."""

    def render_value(self, key, value, context):
        """Render the value for display in the table."""
        obj = get_obj_from_context(context, self.context_object_key)
        if key == "num_created":
            return format_html(
                '<a href="{}?action=create" class="badge bg-success">{}</a>',
                reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": obj.pk}),
                value,
            )
        if key == "num_updated":
            return format_html(
                '<a href="{}?action=update" class="badge bg-warning">{}</a>',
                reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": obj.pk}),
                value,
            )
        if key == "num_deleted":
            return format_html(
                '<a href="{}?action=delete" class="badge bg-danger">{}</a>',
                reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": obj.pk}),
                value,
            )
        if key == "num_failed":
            return format_html(
                '<a href="{}?status=failure">{}</a>',
                reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": obj.pk}),
                value,
            )
        if key == "num_errored":
            return format_html(
                '<a href="{}?status=error">{}</a>',
                reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": obj.pk}),
                value,
            )
        return super().render_value(key, value, context)


class DiffPanel(ObjectTextPanel):
    """Custom ObjectTextPanel to support the rendering of sync diffs."""

    def get_value(self, context):
        """Render the value for the diff."""
        obj = get_obj_from_context(context, "object")
        return render_diff(obj.diff)


class JobResultViewTab(DistinctViewTab):
    """View tab for JobResult associated objects."""

    def render(self, context):
        """Render the tab's contents (layout and panels) to HTML."""
        # Check should_render_content first as it's generally a cheaper calculation than should_render checking perms
        if not self.should_render_content(context) or not self.should_render(context):
            return ""

        with context.update(
            {
                "tab_id": self.tab_id,
                "label": self.render_label(context),
                "include_plugin_content": self.tab_id == "main",
                "left_half_panels": self.panels_for_section(SectionChoices.LEFT_HALF),
                "right_half_panels": self.panels_for_section(SectionChoices.RIGHT_HALF),
                "full_width_panels": self.panels_for_section(SectionChoices.FULL_WIDTH),
                **self.get_extra_context(context),
            }
        ):
            template = loader.get_template("nautobot_ssot/inc/jobresult_tab.html")
            # tab_content = render_component_template(self.LAYOUT_TEMPLATE_PATHS[self.layout], context)
            tab_content = template.render(flatten_context(context), request=context.get("request"))
            return render_component_template(self.content_wrapper_template_path, context, tab_content=tab_content)


class DashboardView(ObjectListView):
    """Dashboard / overview of SSoT."""

    queryset = Sync.objects.defer("diff").all()
    table = DashboardTable
    action_buttons = []
    template_name = "nautobot_ssot/dashboard.html"

    def extra_context(self):
        """Extend the view context with additional details."""
        data_sources, data_targets = get_data_jobs()
        # Override default table context to limit the maximum number of records shown
        table = self.table(self.queryset, user=self.request.user)
        RequestConfig(
            self.request,
            {
                "paginator_class": EnhancedPaginator,
                "per_page": 10,
            },
        ).configure(table)
        context = {
            "queryset": self.queryset,
            "data_sources": data_sources,
            "data_targets": data_targets,
            "source": {},
            "target": {},
            "table": table,
        }
        for source in context["data_sources"]:
            context["source"][source.name] = self.queryset.filter(
                job_result__task_name=source.class_path,
            )
        for target in context["data_targets"]:
            context["target"][target.name] = self.queryset.filter(
                job_result__task_name=target.class_path,
            )

        job_status_chart = get_job_run_status_chart()
        if job_status_chart:
            context["job_status_chart"] = job_status_chart

        integration_activity_chart = get_integration_activity_chart()
        if integration_activity_chart:
            context["integration_activity_chart"] = integration_activity_chart

        sync_runs_chart = get_sync_runs_over_time_chart()
        if sync_runs_chart:
            context["sync_runs_chart"] = sync_runs_chart

        sync_actions_chart = get_sync_actions_chart()
        if sync_actions_chart:
            context["sync_actions_chart"] = sync_actions_chart

        sync_duration_chart = get_sync_duration_over_time_chart()
        if sync_duration_chart:
            context["sync_duration_chart"] = sync_duration_chart

        sync_phase_chart = get_sync_phase_breakdown_chart()
        if sync_phase_chart:
            context["sync_phase_chart"] = sync_phase_chart

        success_failure_chart = get_success_failure_by_integration_chart()
        if success_failure_chart:
            context["success_failure_chart"] = success_failure_chart

        memory_usage_chart = get_memory_usage_chart()
        if memory_usage_chart:
            context["memory_usage_chart"] = memory_usage_chart

        return context


class DataSourceTargetView(ObjectView):
    """Detail view of a given Data Source or Data Target Job."""

    additional_permissions = ("nautobot_ssot.view_sync",)
    queryset = JobModel.objects.all()
    template_name = "nautobot_ssot/data_source_target.html"

    def get_required_permission(self):
        """Permissions required to access this view."""
        return "extras.view_job"

    # pylint: disable-next=arguments-differ
    def get(self, request, class_path):
        """HTTP GET request handler."""
        job = JobModel.objects.get_for_class_path(class_path)
        return super().get(request, id=job.id)

    def get_extra_context(self, request, instance):
        """Return template context extension with job_class, table and source_or_target."""
        job_class = instance.job_class
        if not job_class or not issubclass(job_class, (DataSource, DataTarget)):
            raise Http404

        syncs = Sync.annotated_queryset().filter(source=job_class.data_source, target=job_class.data_target)
        table = SyncTableSingleSourceOrTarget(syncs, user=request.user)

        return {
            "job_class": job_class,
            "table": table,
            "source_or_target": "source" if issubclass(job_class, DataSource) else "target",
        }


class SyncUIViewSet(
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectDestroyViewMixin,
    ObjectBulkDestroyViewMixin,
):
    """ViewSet for Sync."""

    bulk_update_form_class = SyncBulkEditForm
    filterset_class = SyncFilterSet
    filterset_form_class = SyncFilterForm
    form_class = SyncForm
    lookup_field = "pk"
    queryset = Sync.annotated_queryset()
    serializer_class = serializers.SyncSerializer
    table_class = SyncTable
    action_buttons = ("export",)
    breadcrumbs = Breadcrumbs(
        items={
            "detail": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ModelBreadcrumbItem(),
            ],
        }
    )

    object_detail_content = ObjectDetailContent(
        panels=(
            SyncObjectPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields=[
                    "source",
                    "target",
                    "dry_run",
                    "start_time",
                    "end_time",
                    "duration",
                    "job_result__status",
                    "job_result",
                ],
                value_transforms={
                    "dry_run": [dry_run_label],
                    "start_time": [datetime_with_timesince],
                    "end_time": [datetime_with_timesince],
                },
            ),
            StatisticsObjectPanel(
                weight=200,
                section=SectionChoices.RIGHT_HALF,
                label="Statistics",
                fields=[
                    "num_created",
                    "num_updated",
                    "num_deleted",
                    "num_failed",
                    "num_errored",
                ],
                key_transforms={
                    "num_created": "creates",
                    "num_updated": "updates",
                    "num_deleted": "deletes",
                    "num_failed": "failures",
                    "num_errored": "errors",
                },
            ),
        ),
        extra_tabs=(
            DistinctViewTab(
                weight=Tab.WEIGHT_CHANGELOG_TAB + 100,
                tab_id="diff",
                label="Diff",
                url_name="plugins:nautobot_ssot:sync_diff",
                hide_if_empty=False,
                panels=(
                    DiffPanel(
                        weight=300,
                        section=SectionChoices.FULL_WIDTH,
                        label="Diff",
                        object_field="diff",
                        render_as=ObjectTextPanel.RenderOptions.PLAINTEXT,
                        render_placeholder=True,
                    ),
                ),
            ),
            DistinctViewTab(
                weight=Tab.WEIGHT_CHANGELOG_TAB + 300,
                tab_id="logentries",
                label="Sync Logs",
                url_name="plugins:nautobot_ssot:sync_logentries",
                hide_if_empty=False,
                related_object_attribute="logs",
                panels=(
                    ObjectsTablePanel(
                        weight=100,
                        section=SectionChoices.FULL_WIDTH,
                        related_field_name="sync",
                        tab_id="logentries",
                        context_table_key="logs_table",
                        enable_bulk_actions=False,
                        include_paginator=True,
                    ),
                ),
            ),
            JobResultViewTab(
                weight=Tab.WEIGHT_CHANGELOG_TAB + 200,
                tab_id="jobresult",
                label="Job Logs",
                url_name="plugins:nautobot_ssot:sync_jobresult",
                hide_if_empty=False,
            ),
        ),
    )

    @action(detail=True, url_path="diff", custom_view_base_action="view")
    def diff(self, request, *args, **kwargs):
        """Diff action for Sync UIViewSet."""
        return Response({})

    @action(detail=True, url_path="logs", custom_view_base_action="view")
    def logentries(self, request, *args, **kwargs):
        """Log entries action for Sync UIViewSet."""
        sync = self.get_object()
        queryset = sync.logs.all()
        filterset = SyncLogEntryFilterSet(request.GET, queryset=queryset, request=request)

        table = SyncLogEntryTable(filterset.qs, user=request.user)
        RequestConfig(
            request,
            paginate={"paginator_class": EnhancedPaginator, "per_page": get_paginate_count(request)},
        ).configure(table)

        return Response({"logs_table": table})

    @action(detail=True, url_path="jobresult", custom_view_base_action="view")
    def jobresult(self, request, *args, **kwargs):
        """Job result action for Sync UIViewSet."""
        return Response({})


class SyncLogEntryUIViewSet(ObjectListViewMixin):
    """ViewSet for SyncLogEntry."""

    filterset_class = SyncLogEntryFilterSet
    filterset_form_class = SyncLogEntryFilterForm
    lookup_field = "pk"
    queryset = SyncLogEntry.objects.select_related("sync").only(
        "id",
        "timestamp",
        "sync_id",
        "action",
        "status",
        "diff",
        "message",
        "synced_object_type",
        "synced_object_id",
        "object_repr",
        # Sync fields needed for __str__ and link rendering
        "sync__id",
        "sync__source",
        "sync__target",
        "sync__start_time",
    )
    serializer_class = serializers.SyncLogEntrySerializer
    table_class = SyncLogEntryTable
    action_buttons = ("export",)


class SSOTConfigView(ContentTypePermissionRequiredMixin, DjangoView):
    """View with the SSOT integration configs."""

    def get_required_permission(self):
        """Permissions required for the view."""
        return "nautobot_ssot.view_ssotconfig"

    def get(self, request):
        """Return table with links to configuration pages for enabled integrations."""
        enabled_integrations = list(utils.each_enabled_integration())
        return render(request, "nautobot_ssot/ssot_configs.html", {"enabled_integrations": enabled_integrations})
