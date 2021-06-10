"""Django views for Single Source of Truth (SSoT)."""

import pprint

from django.contrib.contenttypes.models import ContentType
from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render

from django_rq import get_queue
from django_rq.queues import get_connection
from rq import Worker

from nautobot.extras.models import JobResult
from nautobot.core.views.generic import BulkDeleteView, ObjectDeleteView, ObjectEditView, ObjectListView, ObjectView

from .filters import SyncFilter, SyncLogEntryFilter
from .forms import SyncFilterForm, SyncLogEntryFilterForm
from .models import Sync, SyncLogEntry
from .sync import get_data_sources, get_data_targets, get_data_source, get_data_target
from .tables import DashboardTable, SyncTable, SyncLogEntryTable


class DashboardView(ObjectListView):
    """Dashboard / overview of SSoT."""

    queryset = Sync.queryset()
    table = DashboardTable
    action_buttons = []
    template_name = "nautobot_ssot/dashboard.html"

    def extra_context(self):
        context = {
            "queryset": self.queryset,
            "data_sources": get_data_sources(),
            "data_targets": get_data_targets(),
            "source": {},
            "target": {},
        }
        sync_ct = ContentType.objects.get_for_model(Sync)
        for source in context["data_sources"]:
            context["source"][source.name] = self.queryset.filter(
                job_result__obj_type=sync_ct,
                job_result__name=source.name,
            )
        for target in context["data_targets"]:
            context["target"][target.name] = self.queryset.filter(
                job_result__obj_type=sync_ct,
                job_result__name=target.name,
            )

        return context

class SyncListView(ObjectListView):
    """View for listing Sync records."""

    queryset = Sync.queryset()
    filterset = SyncFilter
    filterset_form = SyncFilterForm
    table = SyncTable
    action_buttons = []
    template_name = "nautobot_ssot/history.html"

    def extra_context(self):
        return {
            "data_sources": get_data_sources(),
            "data_targets": get_data_targets(),
        }


class SyncCreateView(ObjectEditView):
    """View for starting a new Sync."""

    queryset = Sync.objects.all()

    def get(self, request, slug, kind="source"):
        """Render a form for executing the given sync worker."""

        try:
            if kind == "source":
                sync_worker_class = get_data_source(slug=slug)
            else:
                sync_worker_class = get_data_target(slug=slug)
        except KeyError:
            raise Http404

        form = sync_worker_class.as_form(initial=request.GET)

        return render(
            request,
            "nautobot_ssot/sync_run.html",
            {
                "sync_worker_class": sync_worker_class,
                "form": form,
            },
        )

    def post(self, request, slug, kind="source"):
        """Enqueue the given sync worker for execution!"""
        try:
            if kind == "source":
                sync_worker_class = get_data_source(slug=slug)
                source = sync_worker_class.name
                target = "Nautobot"
            else:
                sync_worker_class = get_data_target(slug=slug)
                source = "Nautobot"
                target = sync_worker_class.name
        except KeyError:
            raise Http404

        if not Worker.count(get_connection("default")):
            messages.error(request, "Unable to perform sync: RQ worker process not running.")

        form = sync_worker_class.as_form(request.POST, request.FILES)

        if form.is_valid():
            dry_run = form.cleaned_data.get("dry_run", True)

            sync = Sync.objects.create(source=source, target=target, dry_run=dry_run, diff={})
            job_result = JobResult.objects.create(
                name=sync_worker_class.name,
                obj_type=ContentType.objects.get_for_model(sync),
                user=request.user,
                job_id=sync.pk,
            )
            sync.job_result = job_result
            sync.save()

            transaction.on_commit(
                lambda: get_queue("default").enqueue(
                    "nautobot_ssot.sync.job.sync", sync_id=sync.pk, data=form.cleaned_data, job_timeout=3600
                )
            )

            return redirect("plugins:nautobot_ssot:sync", pk=sync.pk)

        return render(
            request,
            "nautobot_ssot/sync_run.html",
            {
                "sync_worker_class": sync_worker_class,
                "form": form,
            },
        )


class SyncDeleteView(ObjectDeleteView):
    """View for deleting a single Sync record."""

    queryset = Sync.objects.all()


class SyncBulkDeleteView(BulkDeleteView):
    """View for bulk-deleting Sync records."""

    queryset = Sync.objects.all()
    table = SyncTable


class SyncView(ObjectView):
    """View for details of a single Sync record."""

    queryset = Sync.queryset()
    template_name = "nautobot_ssot/sync_detail.html"

    def get_extra_context(self, request, instance):
        """Add additional context to the view."""
        return {
            "diff": pprint.pformat(instance.diff, width=180, compact=True),
        }


class SyncLogEntryListView(ObjectListView):
    """View for listing SyncLogEntry records."""

    queryset = SyncLogEntry.objects.all()
    filterset = SyncLogEntryFilter
    filterset_form = SyncLogEntryFilterForm
    table = SyncLogEntryTable
    action_buttons = []
    template_name = "nautobot_ssot/synclogentry_list.html"
