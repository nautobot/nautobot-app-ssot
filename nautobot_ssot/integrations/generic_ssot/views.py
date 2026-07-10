"""Views for Generic SSoT Integration."""

import json as _json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
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
    ObjectsTablePanel,
    SectionChoices,
    ViewNameBreadcrumbItem,
)
from nautobot.extras.models import Job

from nautobot_ssot.integrations.generic_ssot import filters, forms, models, tables
from nautobot_ssot.integrations.generic_ssot.api import serializers
from nautobot_ssot.integrations.generic_ssot.utils import (
    TRANSFORM_REGISTRY,
    _extract_records_from_response,
    build_dependency_tree,
    flatten_tree_to_leaves,
    normalize_record,
)

logger = logging.getLogger("nautobot.ssot")


class _JobRunButton(Button):
    """Button that links to a job run URL from context (set in get_extra_context)."""

    def __init__(self, context_key, **kwargs):
        self._context_key = context_key
        super().__init__(**kwargs)

    def get_link(self, context):
        return context.get(self._context_key)

    def should_render(self, context):
        return super().should_render(context) and context.get(self._context_key)


def _get_job_run_url(module_name, job_class_name):
    """Return the run URL for a job by module and class name, or None if not found."""
    job = Job.objects.filter(module_name=module_name, job_class_name=job_class_name).first()
    if job:
        return reverse("extras:job_run", kwargs={"pk": job.pk})
    return None


# ─── Endpoint ────────────────────────────────────────────────────────────────


class SSOTEndpointUIViewSet(views.NautobotUIViewSet):
    """SSOTEndpoint UI ViewSet."""

    queryset = models.SSOTEndpoint.objects.all()
    table_class = tables.SSOTEndpointTable
    filterset_class = filters.SSOTEndpointFilterSet
    filterset_form_class = forms.SSOTEndpointFilterForm
    form_class = forms.SSOTEndpointForm
    bulk_update_form_class = forms.SSOTEndpointBulkEditForm
    serializer_class = serializers.SSOTEndpointSerializer
    lookup_field = "pk"

    breadcrumbs = Breadcrumbs(
        items={
            "detail": [
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:dashboard",
                    label="Single Source of Truth",
                ),
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:ssotendpoint_list",
                    label="SSoT Endpoints",
                ),
                ModelBreadcrumbItem(),
            ],
        }
    )

    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields="__all__",
            ),
        ]
    )


# ─── Sync Config ──────────────────────────────────────────────────────────────


class SSOTSyncConfigUIViewSet(views.NautobotUIViewSet):
    """SSOTSyncConfig UI ViewSet."""

    queryset = models.SSOTSyncConfig.objects.all()
    table_class = tables.SSOTSyncConfigTable
    filterset_class = filters.SSOTSyncConfigFilterSet
    filterset_form_class = forms.SSOTSyncConfigFilterForm
    form_class = forms.SSOTSyncConfigForm
    bulk_update_form_class = forms.SSOTSyncConfigBulkEditForm
    serializer_class = serializers.SSOTSyncConfigSerializer
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
        """Add job run URLs and build field mappings link."""
        ctx = {}
        collect_url = _get_job_run_url(
            "nautobot_ssot.integrations.generic_ssot.jobs",
            "GenericSSOTDataCollectionJob",
        )
        sync_url = _get_job_run_url(
            "nautobot_ssot.integrations.generic_ssot.jobs",
            "GenericSSOTDataSource",
        )
        if collect_url:
            ctx["generic_ssot_collect_job_run_url"] = collect_url
        if sync_url:
            ctx["generic_ssot_sync_job_run_url"] = sync_url
        if instance:
            ctx["generic_ssot_build_mappings_url"] = reverse(
                "plugins:nautobot_ssot:ssotsyncconfig_build_field_mappings",
                kwargs={"pk": instance.pk},
            )
        return ctx

    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields=[
                    "name",
                    "description",
                    "synced_content_types",
                    "primary_endpoint",
                    "sync_direction",
                    "enabled",
                    "dry_run_default",
                    "delete_unmatched",
                ],
            ),
            ObjectsTablePanel(
                weight=200,
                section=SectionChoices.RIGHT_HALF,
                table_class=tables.SSOTSyncConfigEndpointTable,
                table_filter="sync_config",
                related_field_name="sync_config",
                table_title="Endpoints",
                add_button_route="plugins:nautobot_ssot:ssotsyncconfigendpoint_add",
                add_permissions=["nautobot_ssot.add_ssotsyncconfigendpoint"],
            ),
        ],
        extra_buttons=[
            _JobRunButton(
                context_key="generic_ssot_collect_job_run_url",
                weight=90,
                label="1. Collect Samples",
                color=ButtonColorChoices.BLUE,
                icon="mdi-database-search",
            ),
            _JobRunButton(
                context_key="generic_ssot_build_mappings_url",
                weight=100,
                label="2. Configure Mappings",
                color=ButtonColorChoices.BLUE,
                icon="mdi-table-edit",
            ),
            _JobRunButton(
                context_key="generic_ssot_sync_job_run_url",
                weight=110,
                label="3. Run Sync",
                color=ButtonColorChoices.GREEN,
                icon="mdi-sync",
            ),
        ],
    )


# ─── Supporting CRUD viewsets ─────────────────────────────────────────────────


class SSOTFieldMappingUIViewSet(views.NautobotUIViewSet):
    """SSOTFieldMapping UI ViewSet."""

    queryset = models.SSOTFieldMapping.objects.all()
    table_class = tables.SSOTFieldMappingTable
    filterset_class = filters.SSOTFieldMappingFilterSet
    filterset_form_class = forms.SSOTFieldMappingFilterForm
    form_class = forms.SSOTFieldMappingForm
    serializer_class = serializers.SSOTFieldMappingSerializer
    lookup_field = "pk"

    breadcrumbs = Breadcrumbs(
        items={
            "detail": [
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:dashboard",
                    label="Single Source of Truth",
                ),
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:ssotsyncconfig_list",
                    label="SSoT Sync Configs",
                ),
                ModelBreadcrumbItem(),
            ],
        }
    )

    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields="__all__",
            ),
        ]
    )

    def get_initial(self):
        """Pre-fill endpoint from query params when adding from endpoint detail."""
        initial = super().get_initial()
        if self.request and self.request.GET.get("endpoint"):
            try:
                endpoint_pk = self.request.GET["endpoint"]
                initial["endpoint"] = models.SSOTEndpoint.objects.get(pk=endpoint_pk)
            except (ValueError, models.SSOTEndpoint.DoesNotExist):
                pass
        return initial


class SSOTSyncConfigEndpointUIViewSet(views.NautobotUIViewSet):
    """SSOTSyncConfigEndpoint UI ViewSet."""

    queryset = models.SSOTSyncConfigEndpoint.objects.all()
    table_class = tables.SSOTSyncConfigEndpointTable
    filterset_class = filters.SSOTSyncConfigEndpointFilterSet
    filterset_form_class = forms.SSOTSyncConfigEndpointFilterForm
    form_class = forms.SSOTSyncConfigEndpointForm
    serializer_class = serializers.SSOTSyncConfigEndpointSerializer
    lookup_field = "pk"

    breadcrumbs = Breadcrumbs(
        items={
            "detail": [
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:dashboard",
                    label="Single Source of Truth",
                ),
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:ssotsyncconfig_list",
                    label="SSoT Sync Configs",
                ),
                ModelBreadcrumbItem(),
            ],
        }
    )

    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields="__all__",
            ),
        ]
    )


class SSOTEndpointJoinUIViewSet(views.NautobotUIViewSet):
    """SSOTEndpointJoin UI ViewSet."""

    queryset = models.SSOTEndpointJoin.objects.all()
    table_class = tables.SSOTEndpointJoinTable
    filterset_class = filters.SSOTEndpointJoinFilterSet
    filterset_form_class = forms.SSOTEndpointJoinFilterForm
    form_class = forms.SSOTEndpointJoinForm
    serializer_class = serializers.SSOTEndpointJoinSerializer
    lookup_field = "pk"

    breadcrumbs = Breadcrumbs(
        items={
            "detail": [
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:dashboard",
                    label="Single Source of Truth",
                ),
                ViewNameBreadcrumbItem(
                    view_name="plugins:nautobot_ssot:ssotendpointjoin_list",
                    label="Endpoint Joins",
                ),
                ModelBreadcrumbItem(),
            ],
        }
    )

    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields="__all__",
            ),
        ]
    )


# ─── Helpers for the model-centric builder ────────────────────────────────────


def _flatten_to_browser_fields(record, prefix="", max_depth=3):
    """Return list of {path, type, value} dicts from a nested record dict."""
    result = []
    if not isinstance(record, dict):
        return result
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and max_depth > 1:
            result.extend(_flatten_to_browser_fields(value, path, max_depth - 1))
        elif isinstance(value, list):
            result.append({"path": path, "type": "array", "value": str(value)[:120]})
        elif isinstance(value, bool):
            result.append({"path": path, "type": "boolean", "value": str(value)})
        elif isinstance(value, int):
            result.append({"path": path, "type": "integer", "value": str(value)})
        elif isinstance(value, float):
            result.append({"path": path, "type": "float", "value": str(value)})
        elif value is None:
            result.append({"path": path, "type": "null", "value": "null"})
        else:
            result.append({"path": path, "type": "string", "value": str(value)[:200]})
    return result


def _field_prefix(ct_pk, field_name):
    """Stable HTML form prefix for a (content_type_pk, field_name) pair."""
    safe = field_name.replace("__", "_dunder_").replace("-", "_dash_").replace(".", "_dot_")
    return f"fm_{ct_pk}__{safe}"


def _suggest_canonical_fields(content_types, skip_fk_to_models=None) -> list:
    """Build a list of suggested canonical field definitions for a set of content types.

    Walks every model's dependency tree and emits one canonical-field stub per
    *required* leaf path.  Used to seed the normalize editor so the user doesn't
    have to figure out what canonical fields they need from scratch.

    ``skip_fk_to_models`` is an optional set of Django model classes; any required
    FK branch on the target content types that points to one of those models is
    skipped entirely (its leaves are not suggested).  This is used to omit
    fields that will be resolved automatically by a parent/child association —
    e.g., when configuring the Ports endpoint (Interface), we skip ``device.*``
    because that FK is resolved via the parent/child link to Devices.

    Each stub: ``{"name": str, "source": "", "fallback": "", "transforms": []}``
    The canonical name is the path with ``__`` replaced by ``_``.
    """
    skip_fk_to_models = skip_fk_to_models or set()
    # Build the set of model labels we want to skip (lower-case "app.model" strings).
    skip_labels = {m._meta.label_lower for m in skip_fk_to_models if m is not None}

    suggestions = []
    seen_names = set()
    for ct in content_types:
        try:
            tree = build_dependency_tree(ct)
        except Exception:
            continue
        for leaf in flatten_tree_to_leaves(tree):
            if not leaf.get("is_required"):
                continue
            path = leaf.get("path", "") or ""
            # Skip custom fields (different mapping convention)
            if not path or path.startswith("_cf_"):
                continue
            # Skip leaves underneath an FK branch that resolves via association.
            related = (leaf.get("related_model_name") or "").lower()
            if related and related in skip_labels:
                continue
            # Also skip if any ancestor segment of this path is an FK to a skipped model.
            # build_dependency_tree leaves carry the full path; we walk the tree to find
            # the parent FK's related model.
            parent_related = _ancestor_related_model(tree, path)
            if parent_related and parent_related.lower() in skip_labels:
                continue
            canonical_name = path.replace("__", "_")
            if canonical_name in seen_names:
                continue
            seen_names.add(canonical_name)
            suggestions.append(
                {
                    "name": canonical_name,
                    "source": "",
                    "fallback": "",
                    "transforms": [],
                }
            )
    return suggestions


def _ancestor_related_model(tree_nodes, target_path):
    """Walk a dependency tree to find the ``related_model_name`` of the FK ancestor of ``target_path``.

    Returns the related-model label (e.g., ``"dcim.device"``) if any ancestor branch
    has one, otherwise ``None``.
    """
    for node in tree_nodes:
        node_path = node.get("path", "") or ""
        children = node.get("children")
        if children is None:
            continue
        # If the target path is under this node, descend
        if target_path.startswith(node_path + "__") or target_path == node_path:
            # This node is an ancestor; record its related model and recurse for deeper ancestors.
            from_self = node.get("related_model_name")
            deeper = _ancestor_related_model(children, target_path)
            return deeper or from_self
    return None


def _endpoint_target_content_types(sync_config, ep, all_content_types):
    """Determine which content types an endpoint feeds within a sync config.

    Resolution order:
      1. Explicit: distinct content types of existing field mappings using this endpoint.
      2. Parent/child inference: if the endpoint has a parent_endpoint, look at the
         parent's targets and find content types in ``all_content_types`` that have
         a FK to one of those parent target models.
      3. Fallback: all sync config content types.

    Returns ``(targets: list[ContentType], parent_targets: list[ContentType], inferred: bool)``.
    ``inferred=True`` if we narrowed via mappings or parent/child; ``False`` when falling back.
    """
    from django.db.models import ForeignKey  # noqa: PLC0415

    # 1. Mappings-based
    ct_ids = set(
        sync_config.field_mappings.filter(endpoint=ep).values_list("nautobot_content_type_id", flat=True).distinct()
    )
    if ct_ids:
        return ([ct for ct in all_content_types if ct.id in ct_ids], [], True)

    # 2. Parent/child inference
    if ep.parent_endpoint_id:
        parent_ct_ids = set(
            sync_config.field_mappings.filter(endpoint_id=ep.parent_endpoint_id)
            .values_list("nautobot_content_type_id", flat=True)
            .distinct()
        )
        parent_targets = [ct for ct in all_content_types if ct.id in parent_ct_ids]

        # If the parent's targets are known, find content types in this sync config that
        # have an FK pointing to any of those parent models.
        if parent_targets:
            parent_models = {ct.model_class() for ct in parent_targets if ct.model_class()}
            candidates = []
            for ct in all_content_types:
                if ct in parent_targets:
                    continue
                mcls = ct.model_class()
                if mcls is None:
                    continue
                for field in mcls._meta.get_fields():
                    if isinstance(field, ForeignKey) and field.related_model in parent_models:
                        candidates.append(ct)
                        break
            if len(candidates) == 1:
                return (candidates, parent_targets, True)
            # If multiple candidates, we can't unambiguously pick; fall back below
            # but still return the parent_targets for association preview.
            if candidates:
                return (candidates, parent_targets, True)
            # If no candidate found, fall back below.

    # 3. Fallback: all
    return (all_content_types, [], False)


def _annotate_tree_with_forms(tree_nodes, ct, existing_by_field, integration):
    """Recursively attach Django form instances to leaf nodes in the dependency tree.

    Branch nodes (FK parents with ``children``) are passed through with their
    children annotated.  Leaf nodes (``children is None``) get a
    ``ModelCentricFieldMappingForm`` instance attached, along with
    ``has_mapping`` for the template.
    """
    annotated = []
    for node in tree_nodes:
        if node.get("children") is not None and isinstance(node["children"], list):
            annotated_children = _annotate_tree_with_forms(
                node["children"],
                ct,
                existing_by_field,
                integration,
            )
            annotated.append({**node, "children": annotated_children})
        else:
            # Leaf node — build form.
            existing = existing_by_field.get(node["path"])
            prefix = _field_prefix(ct.pk, node["path"])

            displayed_source = ""
            if existing:
                sf = existing.source_field or ""
                displayed_source = "" if sf.startswith("__default_") else sf

            value_map_str = ""
            transform_template_str = ""
            if existing:
                cfg = existing.transformation_config or {}
                if existing.transformation_type == "value_map":
                    inline = cfg.get("inline_map", {})
                    if inline:
                        value_map_str = _json.dumps(inline)
                elif existing.transformation_type == "jinja":
                    transform_template_str = cfg.get("template", "")

            initial = {
                "nautobot_field": node["path"],
                "content_type_id": ct.pk,
                "existing_mapping_pk": str(existing.pk) if existing else "",
                "source_field": displayed_source,
                "is_identifier": existing.is_identifier if existing else False,
                "is_required": existing.is_required if existing else False,
                "default_value": (
                    str(existing.default_value) if existing and existing.default_value is not None else ""
                ),
                "value_map": value_map_str,
                "transform_template": transform_template_str,
                "source_endpoint": existing.source_endpoint_id if existing else None,
            }
            row_form = forms.ModelCentricFieldMappingForm(initial=initial, prefix=prefix)
            row_form.fields["source_endpoint"].queryset = (
                models.SSOTEndpoint.objects.filter(integration=integration)
                if integration
                else models.SSOTEndpoint.objects.none()
            )

            annotated.append(
                {
                    **node,
                    "form": row_form,
                    "has_mapping": bool(existing and displayed_source),
                }
            )
    return annotated


# ─── Model-centric field mapping builder ──────────────────────────────────────


class ModelCentricMappingBuilderView(LoginRequiredMixin, View):
    """Primary field mapping builder: Nautobot model fields → JMESPath expressions.

    GET  – renders the builder with one row per introspected Nautobot field.
    POST – saves SSOTFieldMapping records and SSOTFKCreateRule records.
    """

    template_name = "nautobot_ssot/generic_ssot/model_centric_builder.html"

    def get(self, request, pk):
        """Render the builder."""
        sync_config = get_object_or_404(models.SSOTSyncConfig, pk=pk)
        return render(request, self.template_name, self._get_context(sync_config))

    def post(self, request, pk):
        """Save endpoint normalize configs, field mappings, and FK rules."""
        sync_config = get_object_or_404(models.SSOTSyncConfig, pk=pk)
        with transaction.atomic():
            self._save_normalize_configs(request, sync_config)
            self._save_mappings(request, sync_config)
            self._save_fk_rules(request, sync_config)
        messages.success(request, "Field mappings saved.")
        return redirect("plugins:nautobot_ssot:ssotsyncconfig_build_field_mappings", pk=str(pk))

    def _save_normalize_configs(self, request, sync_config):
        """Parse posted normalize configurations and update SSOTEndpoint records.

        Expects a single POST field named ``normalize_configs`` containing a JSON
        object: ``{endpoint_id: [canonical_field_def, ...], ...}``.
        """
        raw = request.POST.get("normalize_configs", "").strip()
        if not raw:
            return
        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            logger.warning("normalize_configs JSON parse failed: %s", exc)
            return
        if not isinstance(parsed, dict):
            return

        for ep in sync_config.get_ordered_endpoints():
            ep_id = str(ep.pk)
            if ep_id not in parsed:
                continue
            cfg = parsed[ep_id]
            if not isinstance(cfg, list):
                cfg = []
            # Light sanitation: drop entries without a name; coerce transforms list.
            cleaned = []
            for entry in cfg:
                if not isinstance(entry, dict):
                    continue
                name = (entry.get("name") or "").strip()
                if not name:
                    continue
                transforms = entry.get("transforms") or []
                if not isinstance(transforms, list):
                    transforms = []
                cleaned.append(
                    {
                        "name": name,
                        "source": (entry.get("source") or "").strip(),
                        "fallback": (entry.get("fallback") or "").strip(),
                        "transforms": [t for t in transforms if isinstance(t, dict) and t.get("type")],
                    }
                )
            ep.normalize_config = cleaned
            ep.save(update_fields=["normalize_config"])

    # ── Context builder ────────────────────────────────────────────────────────

    def _get_context(self, sync_config):
        """Build context dict for the template."""
        from django.contrib.contenttypes.models import ContentType as CT  # noqa: N811

        # Query the through table directly — the reverse M2M lookup fails with a
        # Django FieldError even though the relation is registered.
        through = type(sync_config).synced_content_types.through
        ct_ids = list(through.objects.filter(ssotsyncconfig=sync_config).values_list("contenttype_id", flat=True))
        content_types = list(CT.objects.filter(id__in=ct_ids).order_by("app_label", "model"))

        available_endpoints = sync_config.get_ordered_endpoints()
        integration = available_endpoints[0].integration if available_endpoints else None

        # Build preview data from SSOTDataSample per endpoint.
        endpoint_sample = {}
        endpoint_records = {}
        all_source_fields = set()
        normalize_sections = []

        for ep in available_endpoints:
            sample = ep.data_samples.order_by("-collected_at").first()
            raw_records = list(sample.sample_data) if (sample and sample.sample_data) else []

            data_path = ep.data_path or ""

            if raw_records:
                # Unwrap stored samples that are the raw API wrapper response (single dict).
                # This happens when the collection job stored the envelope rather than records.
                if len(raw_records) == 1 and isinstance(raw_records[0], dict):
                    try:
                        unwrapped = _extract_records_from_response(raw_records[0], data_path)
                        if unwrapped and unwrapped != [raw_records[0]]:
                            raw_records = unwrapped
                    except Exception as exc:
                        logger.warning("data_path extraction failed for endpoint '%s': %s", ep.name, exc)

            endpoint_sample[str(ep.pk)] = _json.dumps(raw_records[:3], indent=2, default=str)
            browse = []
            paths = set()
            for rec in raw_records[:20]:
                fields = _flatten_to_browser_fields(rec)
                browse.append({"fields": fields})
                for f in fields:
                    paths.add(f["path"])
                    all_source_fields.add(f["path"])

            # Determine the endpoint's target content types using mappings, then
            # parent/child inference, then fallback to all sync config models.
            ep_content_types, parent_target_cts, feeds_inferred = _endpoint_target_content_types(
                sync_config, ep, content_types
            )

            # Models we should skip FK branches for when suggesting canonical fields
            # (because the parent/child association auto-resolves them).
            skip_fk_models = {ct.model_class() for ct in parent_target_cts if ct.model_class()}

            # Build canonical (normalized) preview using the endpoint's normalize_config.
            # If the endpoint has no canonical fields configured yet, seed the editor with
            # one canonical-field stub per required leaf path across the *scoped* models —
            # this avoids dumping the user into an empty editor.
            normalize_cfg = ep.normalize_config or []
            if not normalize_cfg:
                normalize_cfg = _suggest_canonical_fields(ep_content_types, skip_fk_to_models=skip_fk_models)
            canonical_field_names = [
                fd.get("name", "").strip() for fd in normalize_cfg if isinstance(fd, dict) and fd.get("name")
            ]
            canonical_records = []
            for rec in raw_records[:20]:
                try:
                    can_rec = normalize_record(rec, normalize_cfg)
                except Exception as exc:
                    logger.warning("normalize_record failed for endpoint '%s': %s", ep.name, exc)
                    can_rec = {"_raw": rec}
                # Flatten canonical fields to {path, value} format for preview.
                can_fields = []
                for name in canonical_field_names:
                    val = can_rec.get(name)
                    can_fields.append({"path": name, "value": "" if val is None else str(val)})
                canonical_records.append({"fields": can_fields})

            endpoint_records[str(ep.pk)] = {
                "records": browse,
                "canonical_records": canonical_records,
                "canonical_fields": canonical_field_names,
                "total_count": len(raw_records),
                "browse_count": len(browse),
                "field_paths": sorted(paths),
                "no_sample": not raw_records,
            }

            # Required-field suggestions, scoped + with parent-FK leaves skipped.
            required_suggestions = _suggest_canonical_fields(ep_content_types, skip_fk_to_models=skip_fk_models)

            # Human-readable names of the models this endpoint targets, for the
            # builder UI ("Feeds: Interface").
            feeds_model_names = sorted(
                (ct.model_class().__name__ if ct.model_class() else ct.model) for ct in ep_content_types
            )

            # Association info: if this is a child endpoint, surface the link to the parent
            # so the user can see how the FK gets resolved at sync time.
            association = None
            if ep.parent_endpoint_id and parent_target_cts:
                parent_model_names = sorted(
                    (ct.model_class().__name__ if ct.model_class() else ct.model) for ct in parent_target_cts
                )
                association = {
                    "parent_endpoint_name": ep.parent_endpoint.name,
                    "parent_key_field": ep.parent_key_field or "",
                    "parent_model_names": parent_model_names,
                }

            normalize_sections.append(
                {
                    "endpoint_id": str(ep.pk),
                    "endpoint_name": ep.name,
                    "api_path": ep.api_path or "",
                    "data_path": data_path,
                    "record_count": len(raw_records),
                    "normalize_config_json": _json.dumps(normalize_cfg),
                    "required_suggestions_json": _json.dumps(required_suggestions),
                    "available_raw_fields": sorted(paths),
                    "feeds_model_names": feeds_model_names,
                    "feeds_inferred": feeds_inferred,
                    "association": association,
                }
            )

        model_sections = []
        for ct in content_types:
            model_class = ct.model_class()
            if model_class is None:
                continue

            existing_by_field = {
                fm.nautobot_field: fm for fm in sync_config.field_mappings.filter(nautobot_content_type=ct)
            }

            # Determine the section's primary endpoint from existing mappings.
            section_endpoint_id = ""
            for fm in sync_config.field_mappings.filter(nautobot_content_type=ct).select_related("endpoint"):
                if fm.endpoint_id:
                    section_endpoint_id = str(fm.endpoint_id)
                    break

            tree = build_dependency_tree(ct)
            tree_nodes = _annotate_tree_with_forms(
                tree,
                ct,
                existing_by_field,
                integration,
            )

            model_sections.append(
                {
                    "model_name": model_class.__name__,
                    "app_label": ct.app_label,
                    "content_type": ct,
                    "endpoint_field_name": f"section_{ct.model}_endpoint",
                    "section_endpoint_id": section_endpoint_id,
                    "available_endpoints": available_endpoints,
                    "tree_nodes": tree_nodes,
                }
            )

        return {
            "mapping": sync_config,  # template uses "mapping" variable name
            "model_sections": model_sections,
            "normalize_sections": normalize_sections,
            "norm_count": len(normalize_sections),
            "no_content_types": not content_types,
            "endpoint_sample_json": _json.dumps(endpoint_sample),
            "endpoint_records_json": _json.dumps(endpoint_records),
            "source_fields_json": _json.dumps(sorted(all_source_fields)),
            "transform_types_json": _json.dumps(sorted(TRANSFORM_REGISTRY.keys())),
        }

    # ── Save helpers ───────────────────────────────────────────────────────────

    def _save_mappings(self, request, sync_config):
        """Parse POST data and update SSOTFieldMapping records."""
        from django.contrib.contenttypes.models import ContentType as CT  # noqa: N811,PLC0415

        available_endpoints = sync_config.get_ordered_endpoints()
        integration = available_endpoints[0].integration if available_endpoints else None

        # Query the through table directly — reverse M2M lookup fails.
        through = type(sync_config).synced_content_types.through
        ct_ids = list(through.objects.filter(ssotsyncconfig=sync_config).values_list("contenttype_id", flat=True))
        for ct in CT.objects.filter(id__in=ct_ids):
            model_class = ct.model_class()
            if model_class is None:
                continue

            section_ep_pk = request.POST.get(f"section_{ct.model}_endpoint", "").strip()
            section_endpoint = None
            if section_ep_pk:
                try:
                    section_endpoint = models.SSOTEndpoint.objects.get(pk=section_ep_pk)
                except models.SSOTEndpoint.DoesNotExist:
                    pass

            tree = build_dependency_tree(ct)
            for leaf in flatten_tree_to_leaves(tree):
                prefix = _field_prefix(ct.pk, leaf["path"])
                row_form = forms.ModelCentricFieldMappingForm(request.POST, prefix=prefix)
                row_form.fields["source_endpoint"].queryset = (
                    models.SSOTEndpoint.objects.filter(integration=integration)
                    if integration
                    else models.SSOTEndpoint.objects.none()
                )
                if not row_form.is_valid():
                    continue

                source_field = (row_form.cleaned_data.get("source_field") or "").strip()
                nautobot_field = (row_form.cleaned_data.get("nautobot_field") or leaf["path"]).strip()
                is_identifier = row_form.cleaned_data.get("is_identifier", False)
                is_required = row_form.cleaned_data.get("is_required", False)
                default_value_str = (row_form.cleaned_data.get("default_value") or "").strip()
                value_map_str = (row_form.cleaned_data.get("value_map") or "").strip()
                transform_template_str = (row_form.cleaned_data.get("transform_template") or "").strip()
                source_endpoint_override = row_form.cleaned_data.get("source_endpoint")
                existing_pk = row_form.cleaned_data.get("existing_mapping_pk")

                effective_endpoint = source_endpoint_override or section_endpoint

                if not source_field and not default_value_str:
                    if existing_pk:
                        models.SSOTFieldMapping.objects.filter(pk=existing_pk).delete()
                    continue

                if not effective_endpoint:
                    continue

                db_source_field = f"__default_{nautobot_field}" if not source_field else source_field
                default_value = default_value_str or None

                # Transformation precedence: jinja > value_map > none.
                transformation_type = "none"
                transformation_config = {}
                if transform_template_str:
                    transformation_type = "jinja"
                    transformation_config = {"template": transform_template_str}
                elif value_map_str:
                    try:
                        inline_map = _json.loads(value_map_str)
                        if isinstance(inline_map, dict):
                            transformation_type = "value_map"
                            transformation_config = {"inline_map": inline_map}
                    except _json.JSONDecodeError:
                        pass

                models.SSOTFieldMapping.objects.update_or_create(
                    sync_config=sync_config,
                    nautobot_content_type=ct,
                    nautobot_field=nautobot_field,
                    defaults={
                        "endpoint": effective_endpoint,
                        "source_field": db_source_field,
                        "is_identifier": is_identifier,
                        "is_required": is_required,
                        "default_value": default_value,
                        "transformation_type": transformation_type,
                        "transformation_config": transformation_config,
                        "source_endpoint": source_endpoint_override,
                        "enabled": True,
                    },
                )

    def _save_fk_rules(self, request, sync_config):
        """Parse fk_rule_<ct_id> and fk_defaults_<ct_id> POST params and update SSOTFKCreateRule records."""
        from django.contrib.contenttypes.models import ContentType as CT  # noqa: N811,PLC0415

        for key, value in request.POST.items():
            if not key.startswith("fk_rule_"):
                continue
            ct_id_str = key[len("fk_rule_") :]
            try:
                ct = CT.objects.get(pk=int(ct_id_str))
            except (ValueError, CT.DoesNotExist):
                continue
            on_missing = value if value in ("skip_record", "create") else "skip_record"

            raw_defaults = request.POST.get(f"fk_defaults_{ct_id_str}", "").strip()
            creation_defaults = {}
            if raw_defaults:
                try:
                    creation_defaults = _json.loads(raw_defaults)
                    if not isinstance(creation_defaults, dict):
                        creation_defaults = {}
                except (ValueError, TypeError):
                    creation_defaults = {}

            models.SSOTFKCreateRule.objects.update_or_create(
                sync_config=sync_config,
                target_content_type=ct,
                defaults={"on_missing": on_missing, "creation_defaults": creation_defaults},
            )


# ─── Stub views for remaining workflow steps ──────────────────────────────────


class ModelSelectionView(LoginRequiredMixin, View):
    """Workflow step: select target Nautobot models for a sync config (stub)."""

    def get(self, request, pk):
        """Redirect to sync config detail."""
        get_object_or_404(models.SSOTSyncConfig, pk=pk)
        return redirect("plugins:nautobot_ssot:ssotsyncconfig_detail", pk=str(pk))


class EndpointJoinBuilderView(LoginRequiredMixin, View):
    """Workflow step: configure endpoint joins (stub)."""

    def get(self, request, pk):
        """Redirect to sync config detail."""
        get_object_or_404(models.SSOTSyncConfig, pk=pk)
        return redirect("plugins:nautobot_ssot:ssotsyncconfig_detail", pk=str(pk))
