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
from .sync import get_sync_worker_class, get_sync_worker_classes
from .tables import SyncTable, SyncLogEntryTable


class SyncListView(ObjectListView):
    """View for listing Sync records."""

    queryset = Sync.queryset()
    filterset = SyncFilter
    filterset_form = SyncFilterForm
    table = SyncTable
    action_buttons = []
    template_name = "nautobot_ssot/sync_home.html"

    def extra_context(self):
        return {"sync_worker_classes": get_sync_worker_classes()}


class SyncCreateView(ObjectEditView):
    """View for starting a new Sync."""

    queryset = Sync.objects.all()

    def get(self, request, sync_worker_slug):
        """Render a form for executing the given sync worker."""

        try:
            sync_worker_class = get_sync_worker_class(slug=sync_worker_slug)
        except KeyError:
            raise Http404

        form = sync_worker_class.as_form(initial=request.GET)

        return render(
            request,
            "nautobot_ssot/sync.html",
            {
                "sync_worker_class": sync_worker_class,
                "form": form,
            },
        )

    def post(self, request, sync_worker_slug):
        """Enqueue the given sync worker for execution!"""
        try:
            sync_worker_class = get_sync_worker_class(slug=sync_worker_slug)
        except KeyError:
            raise Http404

        if not Worker.count(get_connection("default")):
            messages.error(request, "Unable to perform sync: RQ worker process not running.")

        form = sync_worker_class.as_form(request.POST, request.FILES)

        if form.is_valid():
            dry_run = form.cleaned_data.pop("dry_run")

            sync = Sync.objects.create(dry_run=dry_run, diff={})
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
                    "nautobot_ssot.sync.sync", sync_id=sync.pk, data=form.cleaned_data, job_timeout=3600
                )
            )

            return redirect("plugins:nautobot_ssot:sync", pk=sync.pk)

        return render(
            request,
            "nautobot_ssot/sync.html",
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

    queryset = Sync.objects.all()
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
