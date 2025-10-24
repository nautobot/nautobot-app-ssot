"""Django views for Single Source of Truth (SSoT)."""

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.template import loader
from django.template.defaultfilters import date
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timesince import timesince
from django.views import View as DjangoView
from django_tables2 import RequestConfig
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
from nautobot.extras.models import Job as JobModel
from rest_framework.decorators import action
from rest_framework.response import Response

from nautobot_ssot.api import serializers
from nautobot_ssot.integrations import utils
from nautobot_ssot.templatetags.render_diff import render_diff

from .filters import SyncFilterSet, SyncLogEntryFilterSet
from .forms import SyncBulkEditForm, SyncFilterForm, SyncForm, SyncLogEntryFilterForm
from .jobs import get_data_jobs
from .jobs.base import DataSource, DataTarget
from .models import Sync, SyncLogEntry
from .tables import DashboardTable, SyncLogEntryTable, SyncTable, SyncTableSingleSourceOrTarget


def dry_run_label(value) -> str:
    """Return HTML label for dry run status."""
    badge, text = ("default", "Dry Run") if value else ("info", "Sync")
    return format_html('<span class="dry_run label label-{}">{}</span>', badge, text)


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
        # TODO: NEXT-3.0 Replace label label-* with Bootstrap 5 badge classes when Nautobot supports Bootstrap 5
        # TODO: If Core adds a different way to render job result status labels, use here:
        if key == "job_result__status":
            status_labels = {
                "FAILURE": ("label label-danger", "Failed"),
                "PENDING": ("label label-default", "Pending"),
                "STARTED": ("label label-warning", "Running"),
                "SUCCESS": ("label label-success", "Completed"),
            }
            css_class, text = status_labels.get(value, ("label label-default", "N/A"))
            return format_html('<label class="{}">{}</label>', css_class, text)
        return super().render_value(key, value, context)


class StatisticsObjectPanel(ObjectFieldsPanel):
    """Custom ObjectFieldsPanel to support the rendering of sync statistics."""

    def render_value(self, key, value, context):
        """Render the value for display in the table."""
        # TODO: NEXT-3.0 Replace label label-* with Bootstrap 5 badge classes when Nautobot supports Bootstrap 5
        obj = get_obj_from_context(context, self.context_object_key)
        if key == "num_created":
            return format_html(
                '<a href="{}?action=create" class="label label-success">{}</a>',
                reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": obj.pk}),
                value,
            )
        if key == "num_updated":
            return format_html(
                '<a href="{}?action=update" class="label label-warning">{}</a>',
                reverse("plugins:nautobot_ssot:sync_logentries", kwargs={"pk": obj.pk}),
                value,
            )
        if key == "num_deleted":
            return format_html(
                '<a href="{}?action=delete" class="label label-danger">{}</a>',
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
            "list": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ModelBreadcrumbItem(model=Sync),
            ],
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
            DiffPanel(
                weight=300,
                section=SectionChoices.FULL_WIDTH,
                label="Diff",
                object_field="diff",
                render_as=ObjectTextPanel.RenderOptions.PLAINTEXT,
                render_placeholder=True,
            ),
        ),
        extra_tabs=(
            DistinctViewTab(
                weight=Tab.WEIGHT_CHANGELOG_TAB + 200,
                tab_id="logentries",
                label="Sync Logs",
                url_name="plugins:nautobot_ssot:sync_logentries",
                hide_if_empty=False,
                related_object_attribute="logs",
                panels=(
                    ObjectsTablePanel(
                        weight=100,
                        section=SectionChoices.FULL_WIDTH,
                        table_class=SyncLogEntryTable,
                        table_filter="sync",
                        related_field_name="sync",
                        tab_id="logentries",
                        enable_bulk_actions=False,
                        include_paginator=True,
                    ),
                ),
            ),
            JobResultViewTab(
                weight=Tab.WEIGHT_CHANGELOG_TAB + 100,
                tab_id="jobresult",
                label="Job Logs",
                url_name="plugins:nautobot_ssot:sync_jobresult",
                hide_if_empty=False,
            ),
        ),
    )

    @action(detail=True, url_path="logs", custom_view_base_action="view")
    def logentries(self, request, *args, **kwargs):
        """Log entries action for Sync UIViewSet."""
        return Response({})

    @action(detail=True, url_path="jobresult", custom_view_base_action="view")
    def jobresult(self, request, *args, **kwargs):
        """Job result action for Sync UIViewSet."""
        return Response({})


class SyncLogEntryUIViewSet(ObjectListViewMixin):
    """ViewSet for SyncLogEntry."""

    filterset_class = SyncLogEntryFilterSet
    filterset_form_class = SyncLogEntryFilterForm
    lookup_field = "pk"
    queryset = SyncLogEntry.objects.all()
    serializer_class = serializers.SyncLogEntrySerializer
    table_class = SyncLogEntryTable
    action_buttons = ("export",)
    breadcrumbs = Breadcrumbs(
        items={
            "list": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ModelBreadcrumbItem(model=SyncLogEntry),
            ],
        }
    )


class SSOTConfigView(ContentTypePermissionRequiredMixin, DjangoView):
    """View with the SSOT integration configs."""

    def get_required_permission(self):
        """Permissions required for the view."""
        return "nautobot_ssot.view_ssotconfig"

    def get(self, request):
        """Return table with links to configuration pages for enabled integrations."""
        enabled_integrations = list(utils.each_enabled_integration())
        return render(request, "nautobot_ssot/ssot_configs.html", {"enabled_integrations": enabled_integrations})
