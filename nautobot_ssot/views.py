"""Django views for Single Source of Truth (SSoT)."""

import pprint

from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.generic import View

from django_tables2 import RequestConfig

from nautobot.extras.jobs import get_job
from nautobot.core.views.generic import BulkDeleteView, ObjectDeleteView, ObjectListView, ObjectView
from nautobot.utilities.paginator import EnhancedPaginator
from nautobot.utilities.views import ContentTypePermissionRequiredMixin

from .filters import SyncFilter, SyncLogEntryFilter
from .forms import SyncFilterForm, SyncLogEntryFilterForm
from .jobs import get_data_jobs, DataSource, DataTarget
from .models import Sync, SyncLogEntry
from .tables import DashboardTable, SyncTable, SyncTableSingleSourceOrTarget, SyncLogEntryTable


class DashboardView(ObjectListView):
    """Dashboard / overview of SSoT."""

    queryset = Sync.objects.all()
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
        sync_ct = ContentType.objects.get_for_model(Sync)
        for source in context["data_sources"]:
            context["source"][source.name] = self.queryset.filter(
                job_result__obj_type=sync_ct,
                job_result__name=source.class_path,
            )
        for target in context["data_targets"]:
            context["target"][target.name] = self.queryset.filter(
                job_result__obj_type=sync_ct,
                job_result__name=target.class_path,
            )

        return context


class DataSourceTargetView(ContentTypePermissionRequiredMixin, View):
    """Detail view of a given Data Source or Data Target Job."""

    additional_permissions = ("nautobot_ssot.view_sync",)

    def get_required_permission(self):
        """Permissions required to access this view."""
        return "extras.view_job"

    def get(self, request, class_path):
        """HTTP GET request handler."""
        job_class = get_job(class_path)
        if not job_class or not issubclass(job_class, (DataSource, DataTarget)):
            raise Http404

        syncs = Sync.annotated_queryset().filter(source=job_class.data_source, target=job_class.data_target)
        table = SyncTableSingleSourceOrTarget(syncs, user=request.user)

        return render(
            request,
            "nautobot_ssot/data_source_target.html",
            {
                "job_class": job_class,
                "table": table,
                "source_or_target": "source" if issubclass(job_class, DataSource) else "target",
            },
        )


class SyncListView(ObjectListView):
    """View for listing Sync records."""

    queryset = Sync.annotated_queryset()
    filterset = SyncFilter
    filterset_form = SyncFilterForm
    table = SyncTable
    action_buttons = []
    template_name = "nautobot_ssot/history.html"

    def extra_context(self):
        """Extend the view context with additional information."""
        data_sources, data_targets = get_data_jobs()
        return {
            "data_sources": data_sources,
            "data_targets": data_targets,
        }


class SyncDeleteView(ObjectDeleteView):
    """View for deleting a single Sync record."""

    queryset = Sync.objects.all()


class SyncBulkDeleteView(BulkDeleteView):
    """View for bulk-deleting Sync records."""

    queryset = Sync.objects.all()
    table = SyncTable


class SyncView(ObjectView):
    """View for details of a single Sync record."""

    queryset = Sync.annotated_queryset()
    template_name = "nautobot_ssot/sync_detail.html"

    def get_extra_context(self, request, instance):
        """Add additional context to the view."""
        return {
            "diff": pprint.pformat(instance.diff, width=180, compact=True),
        }


class SyncJobResultView(ObjectView):
    """View for the JobResult associated with a single Sync record."""

    queryset = Sync.objects.all()
    template_name = "nautobot_ssot/sync_jobresult.html"

    def get_extra_context(self, request, instance):
        """Add additional context to the view."""
        return {
            "active_tab": "jobresult",
        }


class SyncLogEntriesView(ObjectListView):
    """View for SyncLogEntries associated with a given Sync."""

    queryset = SyncLogEntry.objects.all()
    filterset = SyncLogEntryFilter
    filterset_form = SyncLogEntryFilterForm
    table = SyncLogEntryTable
    action_buttons = []
    template_name = "nautobot_ssot/sync_logentries.html"

    def get(self, request, pk):  # pylint: disable=arguments-differ
        """HTTP GET request handler."""
        self.instance = get_object_or_404(Sync.objects.all(), pk=pk)  # pylint: disable=attribute-defined-outside-init
        self.queryset = SyncLogEntry.objects.filter(sync=self.instance)

        return super().get(request)

    def extra_context(self):
        """Add additional context to the view."""
        return {"active_tab": "logentries", "object": self.instance}


class SyncLogEntryListView(ObjectListView):
    """View for listing SyncLogEntry records."""

    queryset = SyncLogEntry.objects.all()
    filterset = SyncLogEntryFilter
    filterset_form = SyncLogEntryFilterForm
    table = SyncLogEntryTable
    action_buttons = []
    template_name = "nautobot_ssot/synclogentry_list.html"
