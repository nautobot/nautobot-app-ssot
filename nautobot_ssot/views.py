"""Django views for Single Source of Truth (SSoT)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.template import loader
from django.template.defaultfilters import date
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timesince import timesince
from django.views import View as DjangoView
from django_tables2 import RequestConfig
from nautobot.apps import utils as app_utils
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
from nautobot.extras.models import Job as JobModel
from nautobot.extras.models import JobResult, Status
from rest_framework.decorators import action
from rest_framework.response import Response

from nautobot_ssot import filters, forms, tables
from nautobot_ssot.api import serializers
from nautobot_ssot.integrations import utils
from nautobot_ssot.templatetags import render_diff_expanded
from nautobot_ssot.templatetags.render_diff import render_diff

from .filters import SyncFilterSet, SyncLogEntryFilterSet
from .forms import SyncFilterForm, SyncForm, SyncLogEntryFilterForm
from .jobs import get_data_jobs
from .jobs.base import DataSource, DataTarget
from .models import Sync, SyncLogEntry, SyncRecord
from .tables import (
    DashboardTable,
    SyncLogEntryTable,
    SyncRecordHistoryTable,
    SyncTable,
    SyncTableSingleSourceOrTarget,
)


class ReadOnlyNautobotUIViewSet(  # pylint: disable=abstract-method
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectDestroyViewMixin,
    ObjectBulkDestroyViewMixin,
    # Shows the mixins disabled for read-only functionality
    # ObjectEditViewMixin,
    # ObjectDestroyViewMixin,
    # ObjectBulkCreateViewMixin,
    # ObjectBulkUpdateViewMixin,
):
    """ReadOnly ViewSet for Nautobot UI views."""


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
        # Link to expanded diff view
        expanded_url = reverse("plugins:nautobot_ssot:sync_diff", kwargs={"pk": obj.pk})
        link_html = format_html(
            '<div class="pull-right" style="margin-bottom:8px">'
            '<a href="{}" class="btn btn-sm btn-primary">'
            '<i class="fa fa-expand"></i> Expanded Diff'
            "</a></div>",
            expanded_url,
        )
        return format_html("{}{}", link_html, render_diff(obj.diff))


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
    breadcrumbs = Breadcrumbs(
        items={
            "list": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
            ],
        }
    )

    def extra_context(self):
        """Extend the view context with additional details."""
        data_sources, data_targets = get_data_jobs()
        # Override default table context to limit the maximum number of records shown
        table = self.table(self.queryset, user=self.request.user)
        RequestConfig(
            self.request,
            {
                "paginator_class": EnhancedPaginator,
                "per_page": 30,
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


class SyncRecordUIViewSet(ReadOnlyNautobotUIViewSet):
    """ViewSet for SyncRecord views."""

    bulk_update_form_class = forms.SyncRecordBulkEditForm
    filterset_class = filters.SyncRecordFilterSet
    filterset_form_class = forms.SyncRecordFilterForm
    form_class = forms.SyncRecordForm
    lookup_field = "pk"
    queryset = SyncRecord.objects.all()
    serializer_class = serializers.SyncRecordSerializer
    table_class = tables.SyncRecordTable
    action_buttons: tuple = ()

    def get_extra_context(self, request, instance):  # pylint: disable=signature-differs
        """Provide additional context for the list template."""
        context = super().get_extra_context(request, instance)
        if self.action == "list":
            try:
                successful_status = Status.objects.get(name="Successful")
            except Status.DoesNotExist:
                successful_status = None
                context["successful_status"] = None
                context["showing_completed"] = False
            else:
                context["successful_status"] = successful_status
                # Check if we're currently showing completed records
                status_ids = request.GET.getlist("status")
                successful_status_id_str = str(successful_status.id)
                context["showing_completed"] = successful_status_id_str in status_ids
        return context

    def alter_queryset(self, request):
        """Build actual runtime queryset to automatically remove `Successful` by default."""
        try:
            successful_status = Status.objects.get(name="Successful")
        except Status.DoesNotExist:
            # If Successful status doesn't exist, return queryset as-is
            return self.queryset

        # Get status IDs from URL parameters (they come as strings)
        status_ids = request.GET.getlist("status")
        successful_status_id_str = str(successful_status.id)

        # If the button was clicked and successful_status ID is in the params, show ONLY successful records
        if successful_status_id_str in status_ids:
            return self.queryset.filter(status=successful_status)

        # By default, exclude successful records
        return self.queryset.exclude(status=successful_status)

    # Here is an example of using the UI  Component Framework for the detail view.
    # More information can be found in the Nautobot documentation:
    # https://docs.nautobot.com/projects/core/en/stable/development/core/ui-component-framework/
    object_detail_content = ObjectDetailContent(
        extra_buttons=[],
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields="__all__",
                # Alternatively, you can specify a list of field names:
                # fields=[
                #     "name",
                #     "description",
                # ],
                # Some fields may require additional configuration, we can use value_transforms
                # value_transforms={
                #     "name": [helpers.bettertitle]
                # },
            ),
            # If there is a ForeignKey or M2M with this model we can use ObjectsTablePanel
            # to display them in a table format.
            ObjectsTablePanel(
                weight=200,
                section=SectionChoices.RIGHT_HALF,
                table_class=tables.SyncRecordTable,
                table_filter="parent",
            ),
        ],
    )


class SyncedObjectHistoryView(ContentTypePermissionRequiredMixin, ObjectView):
    """View to display SyncRecord history for a synced object (e.g., Tenant, Device)."""

    template_name = "nautobot_ssot/synced_object_history.html"
    lookup_field = "pk"
    queryset = SyncRecord.objects.none()

    def get_required_permission(self):
        """Permissions required for the view."""
        return "nautobot_ssot.view_syncrecord"

    def _get_content_type(self, request, pk):
        """Get the ContentType for the synced object."""
        # Get ContentType from query parameter or find it from existing SyncRecords
        app_label = request.GET.get("app_label")
        model = request.GET.get("model")

        # Try query parameters first if provided
        if app_label and model:
            try:
                # ContentType model names are stored in lowercase
                content_type = ContentType.objects.get(app_label=app_label, model=model.lower())
                return content_type
            except ContentType.DoesNotExist:
                # Fall through to finding from SyncRecords
                pass

        # Fallback: Try to find ContentType from existing SyncRecords
        sync_record = SyncRecord.objects.filter(synced_object_id=pk).first()
        if sync_record and sync_record.synced_object_type:
            return sync_record.synced_object_type

        # If we still don't have a ContentType, raise an error
        raise Http404(
            f"No SyncRecords found for object with pk={pk}. "
            f"Please ensure this object has been synced at least once."
        )

    def get_object(self, request, *args, **kwargs):
        """Get the synced object instance."""
        # Return cached instance if available (set by our get() method)
        if hasattr(self, "_cached_instance"):
            return self._cached_instance

        pk = kwargs.get(self.lookup_field)
        if pk is None and args:
            pk = args[0]
        if pk is None:
            raise Http404("Synced object identifier not provided")

        content_type = self._get_content_type(request, pk)

        # Get the synced object
        model_class = content_type.model_class()
        try:
            instance = model_class.objects.get(pk=pk)
        except model_class.DoesNotExist:
            raise Http404("Synced object not found")

        # Cache for later use
        self.synced_object_type = content_type
        return instance

    # pylint: disable-next=arguments-differ
    def get(self, request, *args, **kwargs):
        """Override ObjectView get to handle object lookup before it tries to use queryset."""
        # Get the object first using our custom logic
        instance = self.get_object(request, *args, **kwargs)
        # Cache the instance so if ObjectView calls get_object() again, we return the cached one
        self._cached_instance = instance
        # Temporarily set a proper queryset for the instance's model so ObjectView doesn't fail
        original_queryset = self.queryset
        try:
            model_class = type(instance)
            self.queryset = model_class.objects.all()
            return super().get(request, *args, **kwargs)
        finally:
            self.queryset = original_queryset
            # Clean up cached instance
            if hasattr(self, "_cached_instance"):
                delattr(self, "_cached_instance")

    def get_extra_context(self, request, instance):
        """Provide additional context for the object detail template."""
        content_type = getattr(self, "synced_object_type", ContentType.objects.get_for_model(instance))

        # Get all SyncRecords for this synced object
        records = (
            SyncRecord.objects.filter(synced_object_id=instance.pk, synced_object_type=content_type)
            .order_by("-timestamp")
            .restrict(request.user, "view")
        )

        # Create table using the history-specific table class
        table = SyncRecordHistoryTable(records, user=request.user)
        RequestConfig(request, paginate={"per_page": 25}).configure(table)
        # Always set context attribute to avoid AttributeError when render_table tries to delete it
        # django-tables2's render_table tag tries to delete table.context after rendering
        # Set it unconditionally to ensure it exists when the template tag tries to delete it
        table.context = object()

        context = super().get_extra_context(request, instance)
        context.update(app_utils.get_detail_view_components_context_for_model(instance))
        context["active_tab"] = "syncrecord_history"
        context["table"] = table
        context["content_type"] = content_type
        return context


class SyncDiffView(ObjectView):
    """View for expanded diff display of a single Sync record."""

    queryset = Sync.annotated_queryset()
    template_name = "nautobot_ssot/sync_diff_expanded.html"

    def get_extra_context(self, request, instance):
        """Add additional context to the view."""
        import pprint

        return {
            "diff_data": instance.diff,
            "diff_json": pprint.pformat(instance.diff, width=380, compact=False),
        }


class SyncDiffSectionContentView(DjangoView):
    """Ajax view to return HTML for a specific diff section's content (lazy-loaded)."""

    def get(self, request, pk, record_type):  # pylint: disable=arguments-differ
        """Return the HTML content for a specific section of the diff."""
        sync = Sync.annotated_queryset().get(pk=pk)
        children = sync.diff.get(record_type, {})

        # Render only inner content for this section
        html = render_diff_expanded.render_section_children_html(
            children, level=0, parent_section_id=f"root_{record_type}"
        )
        return JsonResponse({"html": str(html)})


def process_bulk_syncrecords(request):
    """Endpoint for processing mulitple SyncRecords."""
    pks = request.POST.getlist("pk")
    if not pks:
        messages.error(request, "No items selected for bulk action")
        url = reverse("plugins:nautobot_ssot:syncrecord_list")
        return redirect(url)
    job = JobModel.objects.get(name="Process Sync Records")
    _job_result = JobResult.enqueue_job(job, request.user, records=pks)
    messages.success(
        request, f"Bulk Processing initiated - Check the Job Results for more info {_job_result.get_absolute_url()}"
    )
    url = reverse("plugins:nautobot_ssot:syncrecord_list")
    return redirect(url)
