"""Generic External API Adapter for DiffSync."""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Type

from diffsync import Adapter, DiffSyncModel
from diffsync.exceptions import ObjectAlreadyExists
from django.contrib.contenttypes.models import ContentType

from nautobot_ssot.integrations.generic_ssot.models import SSOTFieldMapping, SSOTSyncConfig
from nautobot_ssot.integrations.generic_ssot.utils import (
    apply_transformation,
    build_joined_dataset,
    fetch_child_endpoint_data,
    fetch_data_from_endpoint,
    get_required_unmapped_fk_defaults,
    validate_nautobot_field,
)

logger = logging.getLogger("nautobot.ssot")


def _sanitize_field_name(nautobot_field):
    """Get a DiffSync-safe field name from a nautobot_field value.

    Pydantic v2 treats underscore-prefixed fields as private, so custom field
    names like ``_cf_device_id`` must be sanitized to ``cf_device_id``.

    FK traversal syntax (``__``) is preserved so that field names match the
    Nautobot adapter and the contrib framework can resolve foreign-key lookups
    (e.g. ``location__name`` stays ``location__name``).
    """
    if nautobot_field.startswith("_"):
        return nautobot_field[1:]
    return nautobot_field


class GenericExternalAdapter(Adapter):
    """Generic adapter for external API data."""

    def __init__(self, job, sync, sync_config: SSOTSyncConfig):
        """Initialize the adapter."""
        super().__init__()
        self.job = job
        self.sync = sync
        self.sync_config = sync_config
        self._dynamic_models: Dict[str, Type[DiffSyncModel]] = {}
        self._build_dynamic_models()
        self._order_top_level_by_dependencies()

    def _build_dynamic_models(self):
        """Dynamically create DiffSyncModel classes based on field mappings.

        Groups mappings by content_type (not by endpoint+content_type) so that
        when two endpoints map to the same Nautobot model, a SINGLE DiffSyncModel
        is created with the UNION of fields from all endpoints.  Per-endpoint
        mappings are stored on the model class via ``_mappings_by_endpoint``.
        """
        # Group all enabled mappings by content_type across all endpoints.
        mappings_by_ct: Dict[int, Dict[str, Any]] = {}

        for endpoint in self.sync_config.get_ordered_endpoints():
            endpoint_mappings = SSOTFieldMapping.objects.filter(
                sync_config=self.sync_config, endpoint=endpoint, enabled=True
            )
            for mapping in endpoint_mappings:
                ct_id = mapping.nautobot_content_type_id
                if ct_id not in mappings_by_ct:
                    mappings_by_ct[ct_id] = {
                        "content_type": mapping.nautobot_content_type,
                        "mappings_by_endpoint": defaultdict(list),
                        "all_mappings": [],
                    }
                mappings_by_ct[ct_id]["mappings_by_endpoint"][endpoint.id].append(mapping)
                mappings_by_ct[ct_id]["all_mappings"].append(mapping)

        for ct_id, info in mappings_by_ct.items():
            content_type = info["content_type"]
            all_mappings = info["all_mappings"]
            mappings_by_endpoint = dict(info["mappings_by_endpoint"])

            identifiers = []
            attributes = []
            annotations = {}
            seen_fields = set()

            for mapping in all_mappings:
                if not validate_nautobot_field(content_type.model_class(), mapping.nautobot_field):
                    continue
                field_name = _sanitize_field_name(mapping.nautobot_field)
                if field_name in seen_fields:
                    continue
                seen_fields.add(field_name)

                if mapping.is_identifier:
                    identifiers.append(field_name)
                else:
                    attributes.append(field_name)
                annotations[field_name] = Optional[str]

            # Auto-add required FK fields not in user mappings with sensible defaults.
            mapped_fields = {m.nautobot_field for m in all_mappings}
            required_defaults = get_required_unmapped_fk_defaults(content_type.model_class(), mapped_fields)
            for ds_field, default_val in required_defaults.items():
                if ds_field not in seen_fields:
                    attributes.append(ds_field)
                    annotations[ds_field] = Optional[str]
                    seen_fields.add(ds_field)

            model_name = f"External{content_type.model_class().__name__}"
            field_defaults = {fname: "" for fname in annotations}
            # Set known defaults for auto-added required fields.
            for ds_field, default_val in required_defaults.items():
                field_defaults[ds_field] = default_val
            model_class = type(
                model_name,
                (DiffSyncModel,),
                {
                    "__module__": __name__,
                    "__qualname__": model_name,
                    "__annotations__": annotations,
                    "_modelname": content_type.model,
                    "_identifiers": tuple(identifiers),
                    "_attributes": tuple(attributes),
                    **field_defaults,
                },
            )

            model_class._content_type_id = ct_id
            model_class._field_mappings = all_mappings
            model_class._mappings_by_endpoint = mappings_by_endpoint
            model_class._required_fk_defaults = required_defaults

            model_key = content_type.model
            self._dynamic_models[model_key] = model_class
            setattr(self, model_key, model_class)

            if not hasattr(self, "top_level") or not self.top_level:
                self.top_level = [model_key]
            elif model_key not in self.top_level:
                self.top_level.append(model_key)

            logger.debug(f"Created dynamic model: {model_name} with identifiers {identifiers}")

    def _order_top_level_by_dependencies(self):
        """Topologically sort ``self.top_level`` so referenced models come first.

        Inspects ``__`` FK traversal fields in the model's field mappings to
        build a dependency graph.  If model A has a field like
        ``primary_ip__host`` that references model B (IPAddress), model B is
        placed before model A in ``self.top_level``.

        Falls back to the original ordering if a cycle is detected.
        """
        if not self.top_level or len(self.top_level) <= 1:
            return

        # model_key → set of model_keys it depends on
        deps = {mk: set() for mk in self.top_level}
        model_key_by_ct_id = {}
        for mk, mc in self._dynamic_models.items():
            model_key_by_ct_id[mc._content_type_id] = mk

        for model_key, model_class in self._dynamic_models.items():
            ct = ContentType.objects.get(id=model_class._content_type_id)
            django_model = ct.model_class()
            if not django_model:
                continue

            for mapping in model_class._field_mappings:
                if "__" not in mapping.nautobot_field:
                    continue
                fk_name = mapping.nautobot_field.split("__", maxsplit=1)[0]
                try:
                    fk_field = django_model._meta.get_field(fk_name)
                    if fk_field.is_relation and fk_field.related_model:
                        related_ct = ContentType.objects.get_for_model(fk_field.related_model)
                        related_key = model_key_by_ct_id.get(related_ct.id)
                        if related_key and related_key != model_key and related_key in deps:
                            deps[model_key].add(related_key)
                except Exception:
                    continue

        # Kahn's algorithm for topological sort
        in_degree = {mk: len(dep_set) for mk, dep_set in deps.items()}

        # Build adjacency: if A depends on B, then B → A (B must come before A)
        adjacency = {mk: [] for mk in self.top_level}
        for mk, dep_set in deps.items():
            for dep in dep_set:
                if dep in adjacency:
                    adjacency[dep].append(mk)

        queue = [mk for mk in self.top_level if in_degree[mk] == 0]
        sorted_order = []

        while queue:
            node = queue.pop(0)
            sorted_order.append(node)
            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_order) == len(self.top_level):
            self.top_level = sorted_order
            logger.debug("Topologically sorted top_level: %s", self.top_level)
        else:
            logger.warning(
                "Cycle detected in model dependencies; keeping original top_level order: %s",
                self.top_level,
            )

    def load(self):
        """Load data from external API endpoints.

        Iterates endpoints in weight order.  For each endpoint, loads data for
        every content type that has mappings from that endpoint.  When an object
        with the same identifiers already exists (loaded from a previous
        endpoint), its attributes are MERGED — last-write-wins per endpoint
        weight ordering.

        Supports child endpoints (per-parent iteration), endpoint joins
        (cross-endpoint field merging), and stub models (identifier-only
        DiffSync models for required dependencies).
        """
        # Phase 1: Fetch all endpoint data into a map.
        endpoint_data_map: Dict[str, List[Dict]] = {}
        ordered_endpoints = self.sync_config.get_ordered_endpoints()

        for endpoint in ordered_endpoints:
            self.job.logger.info(f"Loading data from endpoint: {endpoint.name}")

            try:
                if endpoint.endpoint_type == "child" and endpoint.parent_endpoint:
                    # Child endpoint: iterate over parent records.  Parent records
                    # at this point are canonical (wrapped via normalize_record),
                    # so unwrap to raw form for the child key-substitution to find
                    # the expected JMESPath fields.
                    parent_id = str(endpoint.parent_endpoint_id)
                    parent_records = endpoint_data_map.get(parent_id, [])
                    if not parent_records:
                        self.job.logger.warning(
                            f"No parent records for child endpoint {endpoint.name}; "
                            f"parent {endpoint.parent_endpoint.name} has no data."
                        )
                        continue
                    parent_raw_records = [
                        rec.get("_raw", rec) if isinstance(rec, dict) else rec for rec in parent_records
                    ]
                    records = fetch_child_endpoint_data(
                        endpoint,
                        parent_raw_records,
                        sample_size=10000,
                        log=self.job.logger,
                    )
                else:
                    # Bulk endpoint: fetch list.
                    records, _ = fetch_data_from_endpoint(
                        endpoint,
                        sample_size=10000,
                        logger=self.job.logger,
                    )

                if not records:
                    self.job.logger.warning(f"No data found for endpoint: {endpoint.name}")
                    continue

                # Phase 1b: Normalize raw records into canonical records.
                # If the endpoint has no normalize_config, this just wraps the
                # raw record with a ``_raw`` key for escape-hatch access.
                normalize_cfg = endpoint.normalize_config or []
                canonical_records = [normalize_record(rec, normalize_cfg, logger=self.job.logger) for rec in records]
                endpoint_data_map[str(endpoint.id)] = canonical_records

            except Exception as e:
                self.job.logger.error(f"Error loading data from {endpoint.name}: {str(e)}")
                raise

        # Phase 2: Apply endpoint joins to merge cross-endpoint data.
        endpoint_data_map = build_joined_dataset(self.sync_config, endpoint_data_map, log=self.job.logger)

        # Phase 3: Build DiffSync objects from the fetched data.
        for endpoint in ordered_endpoints:
            ep_id_str = str(endpoint.id)
            records = endpoint_data_map.get(ep_id_str, [])
            if not records:
                continue

            for model_key, model_class in self._dynamic_models.items():
                ep_mappings = model_class._mappings_by_endpoint.get(endpoint.id)
                if not ep_mappings:
                    continue

                identifier_fields = model_class._identifiers

                for record in records:
                    try:
                        model_data = {}
                        skip_record = False

                        for mapping in ep_mappings:
                            field_name = _sanitize_field_name(mapping.nautobot_field)
                            if field_name not in model_class.__annotations__:
                                continue

                            # Determine the source record: use joined data if
                            # source_endpoint differs from this endpoint.
                            source_record = record
                            if mapping.source_endpoint_id and mapping.source_endpoint_id != endpoint.id:
                                # Look for joined data from a different endpoint.
                                source_ep = mapping.source_endpoint
                                joined_key = f"_joined_{source_ep.name}"
                                joined = record.get(joined_key)
                                if isinstance(joined, dict):
                                    source_record = joined
                                elif isinstance(joined, list) and joined:
                                    source_record = joined[0]
                                else:
                                    # No joined data available for this field.
                                    if mapping.default_value is not None:
                                        source_record = {}
                                    else:
                                        continue

                            raw_value = resolve_source_value(source_record, mapping.source_field)

                            if mapping.is_required and (raw_value is None or raw_value == ""):
                                self.job.logger.warning(
                                    f"Skipping record due to missing required field: {mapping.source_field}"
                                )
                                skip_record = True
                                break

                            if raw_value is None or raw_value == "":
                                if mapping.default_value is not None:
                                    raw_value = mapping.default_value
                                else:
                                    continue

                            transformed_value = apply_transformation(
                                raw_value,
                                mapping.transformation_type,
                                mapping.transformation_config,
                                mapping.value_map,
                                logger=self.job.logger,
                            )

                            # If transformation produced None (e.g. value_map
                            # lookup failed with no default), treat as missing
                            # so we don't overwrite Nautobot data with null.
                            if transformed_value is None:
                                continue

                            # All dynamic model fields are Optional[str], so coerce
                            # non-string values (e.g. integers from the API) to strings.
                            if not isinstance(transformed_value, str):
                                transformed_value = str(transformed_value)
                            model_data[field_name] = transformed_value

                        if skip_record:
                            continue

                        # Inject defaults for auto-added required FK fields.
                        for ds_field, default_val in model_class._required_fk_defaults.items():
                            if ds_field not in model_data:
                                model_data[ds_field] = default_val

                        # Skip objects where all identifier fields are empty — these
                        # are meaningless and would collide with each other.
                        if identifier_fields and all(not model_data.get(f, "") for f in identifier_fields):
                            self.job.logger.debug(f"Skipping {model_key} record with empty identifiers")
                            continue

                        instance = model_class(**model_data)
                        self.add(instance)

                    except ObjectAlreadyExists:
                        # Object with same identifiers already loaded from a
                        # previous endpoint — merge new attributes into it.
                        ids = {f: model_data[f] for f in identifier_fields if f in model_data}
                        try:
                            existing = self.get(model_class, ids)
                            for attr in model_class._attributes:
                                if attr in model_data and model_data[attr]:
                                    setattr(existing, attr, model_data[attr])
                        except Exception:
                            # If merge fails for any reason, skip silently
                            # (matches previous behaviour for shared reference objects).
                            pass
                    except Exception as e:
                        self.job.logger.error(f"Error processing record: {str(e)}")
                        if self.sync_config.sync_direction == "import":
                            continue
                        else:
                            raise

        total = sum(len(self.get_all(model_key)) for model_key in self.top_level)
        self.job.logger.info(f"Loaded {total} objects from external API")
