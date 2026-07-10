"""Views for the Data Import integration."""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.generic import View
from nautobot.apps import views
from nautobot.apps.ui import (
    Breadcrumbs,
    Button,
    ButtonColorChoices,
    ModelBreadcrumbItem,
    ObjectDetailContent,
    ObjectFieldsPanel,
    SectionChoices,
    ViewNameBreadcrumbItem,
)
from nautobot.extras.models import Job

from nautobot_ssot.integrations.data_import import filters, forms, models, tables
from nautobot_ssot.integrations.data_import.api import serializers
from nautobot_ssot.integrations.data_import.engine import normalize, sources
from nautobot_ssot.integrations.data_import.engine.introspect import introspect_model
from nautobot_ssot.integrations.data_import.engine.runner import (
    DocumentError,
    get_content_type,
    run_plan,
    validate_document,
)
from nautobot_ssot.integrations.data_import.models import MAX_CACHED_ROWS, MAX_CSV_BYTES, ImportPlan

# App labels offered as import targets in the builder.
TARGET_APP_LABELS = ["dcim", "ipam", "tenancy", "circuits", "extras", "virtualization"]


class _ContextLinkButton(Button):
    """Detail-page button whose link comes from a context key set in get_extra_context."""

    def __init__(self, context_key, **kwargs):
        self._context_key = context_key
        super().__init__(**kwargs)

    def get_link(self, context):
        return context.get(self._context_key)

    def should_render(self, context):
        return super().should_render(context) and context.get(self._context_key)


class ImportPlanUIViewSet(views.NautobotUIViewSet):
    """ImportPlan UI ViewSet."""

    queryset = models.ImportPlan.objects.all()
    table_class = tables.ImportPlanTable
    filterset_class = filters.ImportPlanFilterSet
    filterset_form_class = forms.ImportPlanFilterForm
    form_class = forms.ImportPlanForm
    bulk_update_form_class = forms.ImportPlanBulkEditForm
    serializer_class = serializers.ImportPlanSerializer
    lookup_field = "pk"

    breadcrumbs = Breadcrumbs(
        items={
            "detail": [
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:dashboard",
                    label="Single Source of Truth",
                ),
                ModelBreadcrumbItem(),
            ],
        }
    )

    def get_extra_context(self, request, instance):
        """Provide builder and job-run URLs for the detail buttons."""
        ctx = {}
        if instance:
            ctx["data_import_builder_url"] = reverse(
                "plugins:nautobot_ssot:importplan_builder", kwargs={"pk": instance.pk}
            )
        job = Job.objects.filter(
            module_name="nautobot_ssot.integrations.data_import.jobs",
            job_class_name="RunImportPlan",
        ).first()
        if job:
            ctx["data_import_job_run_url"] = reverse("extras:job_run", kwargs={"pk": job.pk})
        return ctx

    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields=["name", "description", "integration", "enabled"],
            ),
        ],
        extra_buttons=[
            _ContextLinkButton(
                context_key="data_import_builder_url",
                weight=100,
                label="Open Builder",
                color=ButtonColorChoices.BLUE,
                icon="mdi-table-edit",
            ),
            _ContextLinkButton(
                context_key="data_import_job_run_url",
                weight=110,
                label="Run Import",
                color=ButtonColorChoices.GREEN,
                icon="mdi-database-import",
            ),
        ],
    )


# ─── Builder ─────────────────────────────────────────────────────────────────


class ImportPlanBuilderView(LoginRequiredMixin, View):
    """The drag-and-drop mapping builder."""

    template_name = "nautobot_ssot/data_import/builder.html"

    def get(self, request, pk):
        """Render the builder."""
        plan = get_object_or_404(ImportPlan, pk=pk)
        content_types = ContentType.objects.filter(app_label__in=TARGET_APP_LABELS).order_by("app_label", "model")
        target_choices = [
            {"label": f"{ct.app_label}.{ct.model}", "display": f"{ct.app_label} | {ct.model}"}
            for ct in content_types
            if ct.model_class() is not None
        ]
        return render(
            request,
            self.template_name,
            {
                "plan": plan,
                "document_json": json.dumps(plan.document or {}),
                "cached_tables_json": json.dumps(plan.cached_tables or {}),
                "target_choices_json": json.dumps(target_choices),
                "has_integration": plan.integration is not None,
            },
        )


def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def _cache_source_sample(plan, source_id, records):
    """Flatten + cache a capped sample of records for one source; persist."""
    flat_rows = [normalize.flatten_record(rec) for rec in records[:MAX_CACHED_ROWS]]
    preview = normalize.table_preview(flat_rows, max_rows=MAX_CACHED_ROWS)
    preview["raw_rows"] = flat_rows  # client derives expanded-table previews from these
    preview["row_count"] = len(records)
    cached = dict(plan.cached_tables or {})
    cached[source_id] = preview
    plan.cached_tables = cached
    plan.save()
    return preview


class BuilderUploadCSVView(LoginRequiredMixin, View):
    """POST multipart: file + source_id → store CSV text, return table preview."""

    def post(self, request, pk):
        """Handle the upload."""
        plan = get_object_or_404(ImportPlan, pk=pk)
        source_id = request.POST.get("source_id", "").strip()
        upload = request.FILES.get("file")
        if not source_id or upload is None:
            return JsonResponse({"error": "source_id and file are required."}, status=400)
        if upload.size > MAX_CSV_BYTES:
            return JsonResponse({"error": f"File too large (max {MAX_CSV_BYTES // (1024 * 1024)} MB)."}, status=400)

        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return JsonResponse({"error": "File is not UTF-8 text. Save it as UTF-8 CSV and retry."}, status=400)

        records = sources.parse_csv(text)
        if not records:
            return JsonResponse({"error": "No data rows found in the CSV."}, status=400)

        csv_data = dict(plan.csv_data or {})
        csv_data[source_id] = text
        plan.csv_data = csv_data
        preview = _cache_source_sample(plan, source_id, records)
        return JsonResponse({"source_id": source_id, "table": preview})


class BuilderFetchSampleView(LoginRequiredMixin, View):
    """POST {source: {...}} → test-fetch an API source, return table preview."""

    def post(self, request, pk):
        """Fetch a sample from the API source config."""
        plan = get_object_or_404(ImportPlan, pk=pk)
        if plan.integration is None:
            return JsonResponse({"error": "Set an External Integration on the plan first."}, status=400)
        body = _json_body(request)
        source_cfg = body.get("source") or {}
        source_id = source_cfg.get("id", "").strip()
        if not source_id:
            return JsonResponse({"error": "Source id is required."}, status=400)
        try:
            records = sources.fetch_api_records(plan.integration, source_cfg, limit=MAX_CACHED_ROWS)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return JsonResponse({"error": f"Fetch failed: {exc}"}, status=502)
        if not records:
            return JsonResponse({"error": "The API returned no records. Check the path and data path."}, status=400)
        preview = _cache_source_sample(plan, source_id, records)
        return JsonResponse({"source_id": source_id, "table": preview})


class BuilderIntrospectView(LoginRequiredMixin, View):
    """GET ?content_type=dcim.device → field metadata for the chip palette."""

    def get(self, request, pk):  # pylint: disable=unused-argument
        """Introspect one target model."""
        label = request.GET.get("content_type", "")
        content_type = get_content_type(label)
        if content_type is None:
            return JsonResponse({"error": f"Unknown content type '{label}'."}, status=400)
        return JsonResponse(introspect_model(content_type))


class BuilderSaveView(LoginRequiredMixin, View):
    """POST {document} → validate + save."""

    def post(self, request, pk):
        """Save the document."""
        plan = get_object_or_404(ImportPlan, pk=pk)
        body = _json_body(request)
        document = body.get("document")
        if not isinstance(document, dict):
            return JsonResponse({"error": "Missing document."}, status=400)
        problems = validate_document(document)
        plan.document = document
        plan.save()
        return JsonResponse({"saved": True, "problems": problems})


class BuilderDryRunView(LoginRequiredMixin, View):
    """POST {document} → run the engine in report mode over sample data."""

    def post(self, request, pk):
        """Preview what the import would do (capped sample, nothing written)."""
        plan = get_object_or_404(ImportPlan, pk=pk)
        body = _json_body(request)
        document = body.get("document")
        if isinstance(document, dict) and document:
            plan.document = document  # in-memory only; not saved
        try:
            summary = run_plan(plan, dry_run=True, limit=MAX_CACHED_ROWS)
        except DocumentError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return JsonResponse({"error": f"Dry-run failed: {exc}"}, status=500)
        return JsonResponse(summary)
