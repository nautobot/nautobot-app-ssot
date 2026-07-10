"""Generic Nautobot Adapter for DiffSync."""

import ipaddress as ipaddress_mod
import logging
from typing import Annotated, List, Optional, Type

from diffsync.exceptions import ObjectAlreadyExists
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from pydantic import ConfigDict

from nautobot_ssot.contrib.adapter import NautobotAdapter
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.types import CustomFieldAnnotation
from nautobot_ssot.integrations.generic_ssot.models import SSOTSyncConfig
from nautobot_ssot.integrations.generic_ssot.utils import (
    get_required_unmapped_fk_defaults,
    get_resolved_model_set,
    validate_nautobot_field,
)

logger = logging.getLogger("nautobot.ssot")


class GenericNautobotAdapter(NautobotAdapter):
    """Generic Nautobot adapter configured from field mappings."""

    def __init__(self, job, sync, sync_config: SSOTSyncConfig):
        """Initialize the adapter.

        ``_configure_from_mappings`` must run *before* ``super().__init__``
        because ``NautobotAdapter.validate_adapter`` requires ``top_level``
        to be populated.
        """
        self.sync_config = sync_config
        self._configure_from_mappings()
        self._order_top_level_by_dependencies()
        super().__init__(job=job, sync=sync)

    def get_from_orm_cache(self, parameters: dict, model_class: Type[Model]):
        """Look up a related object, auto-creating it if it doesn't exist.

        The contrib framework resolves FK fields (e.g. ``status__name``) by
        calling ``adapter.get_from_orm_cache({"name": "Active"}, Status)``.
        If the referenced object (Status, Role, etc.) doesn't exist yet the
        base implementation raises ``DoesNotExist`` and the whole create/update
        fails.

        For the generic SSoT integration we fall back to ``get_or_create`` so
        that referenced objects like Status and Role are automatically created
        when they're absent from Nautobot.
        """
        try:
            return super().get_from_orm_cache(parameters, model_class)
        except model_class.DoesNotExist:
            # Only auto-create for natural-key FK lookups, never for PK or
            # ContentType lookups.
            if "pk" in parameters or model_class is ContentType:
                raise
            return self._get_or_create_cached(parameters, model_class)

    def _get_or_create_cached(self, parameters: dict, model_class: Type[Model]):
        """Try ``get_or_create`` and cache the result.

        Behaviour is controlled by the ``SSOTFKCreateRule`` for this mapping:

        * ``skip_record`` (default) – raise ``DoesNotExist`` so DiffSync skips
          just this record rather than failing the whole sync.
        * ``create`` – call ``get_or_create`` using the supplied parameters
          (i.e. the name the source data provided).  If creation fails because
          the model needs additional required fields, the exception is logged
          and re-raised so the record is skipped gracefully.
        """
        from nautobot_ssot.integrations.generic_ssot.models import SSOTFKCreateRule  # noqa: PLC0415

        ct = ContentType.objects.get_for_model(model_class)

        # Look up the user-configured rule for this FK target model.
        on_missing = "skip_record"
        rule = SSOTFKCreateRule.objects.filter(
            sync_config=self.sync_config,
            target_content_type=ct,
        ).first()
        if rule:
            on_missing = rule.on_missing

        if on_missing == "skip_record":
            logger.warning(
                "FK rule for %s is 'skip_record' (sync_config=%s) — skipping record. "
                "Set to 'Create automatically' in the mapping builder to change this.",
                model_class._meta.verbose_name,
                getattr(self.sync_config, "pk", None),
            )
            raise model_class.DoesNotExist(
                f"{model_class._meta.verbose_name} matching {parameters} not found in Nautobot. " "Rule: skip record."
            )

        # on_missing == "create": attempt get_or_create with the supplied parameters,
        # merging in any creation_defaults from the rule to satisfy required fields.
        creation_defaults = rule.creation_defaults if rule else {}
        resolved_defaults = self._resolve_creation_defaults(creation_defaults)

        # Separate __ traversal keys from simple keys.  Django's
        # get_or_create uses __ keys for the GET lookup but NOT for the
        # CREATE, so we must resolve FK objects and pass them as defaults.
        lookup_params = {}
        fk_defaults = {}
        for key, value in parameters.items():
            if "__" in key:
                field_name, lookup_field = key.split("__", 1)
                try:
                    django_field = model_class._meta.get_field(field_name)
                    if django_field.is_relation and django_field.related_model:
                        related_obj, _ = django_field.related_model.objects.get_or_create(**{lookup_field: value})
                        fk_defaults[field_name] = related_obj
                        lookup_params[key] = value  # keep for the GET side
                    else:
                        lookup_params[key] = value
                except Exception:
                    lookup_params[key] = value
            else:
                lookup_params[key] = value

        # Merge: explicit FK defaults override auto-resolved ones.
        fk_defaults.update(resolved_defaults)

        try:
            obj, created = model_class.objects.get_or_create(
                **lookup_params,
                defaults=fk_defaults,
            )
        except Exception as exc:
            logger.warning(
                "FK auto-create failed for %s with %s (defaults=%s): %s",
                model_class._meta.verbose_name,
                parameters,
                resolved_defaults,
                exc,
            )
            raise model_class.DoesNotExist(
                f"{model_class._meta.verbose_name} matching {parameters} does not exist "
                f"and could not be auto-created: {exc}"
            ) from exc

        if created:
            logger.info(
                "Auto-created %s with: %s",
                model_class._meta.verbose_name,
                parameters,
            )

        # Store in the adapter cache so subsequent lookups are free.
        parameter_set = frozenset(parameters.items())
        cache_key = f"{ct.app_label}.{ct.model}"
        self.cache.cache[cache_key][parameter_set] = obj

        return obj

    def _resolve_creation_defaults(self, creation_defaults: dict) -> dict:
        """Resolve creation_defaults dict into ORM-ready kwargs.

        Simple scalar values are passed through as-is.  FK traversal keys
        (e.g. ``manufacturer__name``) are resolved to the actual FK object
        via ``get_or_create`` so they can be used in ``defaults=`` of the
        parent ``get_or_create`` call.

        Example input:  {"manufacturer__name": "Unknown"}
        Example output: {"manufacturer": <Manufacturer: Unknown>}
        """
        from django.apps import apps  # noqa: PLC0415

        resolved = {}
        for key, value in (creation_defaults or {}).items():
            if "__" in key:
                # e.g. "manufacturer__name" → field_name="manufacturer", lookup="name"
                field_name, lookup_field = key.split("__", 1)
                try:
                    # Determine the related model from the field name by inspecting
                    # the ORM field on whichever model we happen to be building.
                    # We resolve lazily by scanning all installed models for the field.
                    rel_model = None
                    for app_config in apps.get_app_configs():
                        for model in app_config.get_models():
                            try:
                                f = model._meta.get_field(field_name)
                                if f.is_relation and f.related_model:
                                    rel_model = f.related_model
                                    break
                            except Exception:
                                pass
                        if rel_model:
                            break

                    if rel_model:
                        obj, _ = rel_model.objects.get_or_create(**{lookup_field: value})
                        resolved[field_name] = obj
                    else:
                        logger.warning("creation_defaults: could not resolve FK field '%s' — skipping", key)
                except Exception as exc:
                    logger.warning("creation_defaults: failed to resolve '%s'=%r: %s", key, value, exc)
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _auto_create_parent_prefix(parameters):
        """Auto-create a parent Prefix for an IPAddress if one doesn't exist.

        Computes the network address from ``host`` and ``mask_length`` in
        *parameters*, then ``get_or_create``s a Prefix in the Global namespace.
        """
        from nautobot.extras.models import Status  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Namespace, Prefix  # pylint: disable=import-outside-toplevel

        host = parameters.get("host", "")
        mask_length = parameters.get("mask_length", "")

        if not host or not mask_length:
            return

        try:
            network = ipaddress_mod.ip_network(f"{host}/{int(mask_length)}", strict=False)
            namespace = Namespace.objects.get(name="Global")
            status = Status.objects.get(name="Active")
            _, created = Prefix.objects.get_or_create(
                network=str(network.network_address),
                prefix_length=network.prefixlen,
                namespace=namespace,
                defaults={"status": status},
            )
            if created:
                logger.info(
                    "Auto-created parent prefix %s/%s in namespace Global",
                    network.network_address,
                    network.prefixlen,
                )
        except Exception as exc:
            logger.warning(
                "Could not auto-create parent prefix for %s/%s: %s",
                host,
                mask_length,
                exc,
            )

    def _configure_from_mappings(self):
        """Configure the adapter based on field mappings from the SSoT mapping.

        Uses ``get_resolved_model_set`` to determine which models are full
        (user-selected, all field mappings) vs stub (required dependency,
        identifier-only — DiffSync won't try to update attributes).
        """
        from nautobot.ipam.models import IPAddress as NautobotIPAddress  # pylint: disable=import-outside-toplevel

        # Determine full vs stub model set.
        resolved = get_resolved_model_set(self.sync_config)
        stub_ct_ids = {ct_id for ct_id, info in resolved.items() if info.get("is_stub")}

        content_types = set()
        for endpoint in self.sync_config.get_ordered_endpoints():
            for mapping in self.sync_config.field_mappings.filter(endpoint=endpoint, enabled=True):
                content_types.add(mapping.nautobot_content_type)

        for content_type in content_types:
            is_stub = content_type.id in stub_ct_ids
            model_class = content_type.model_class()
            model_key = content_type.model

            mappings: List = []
            for endpoint in self.sync_config.get_ordered_endpoints():
                mappings.extend(
                    self.sync_config.field_mappings.filter(
                        enabled=True,
                        endpoint=endpoint,
                        nautobot_content_type=content_type,
                    )
                )

            if not mappings:
                continue

            identifiers = []
            attributes = []
            annotations = {}
            seen_fields = set()
            for mapping in mappings:
                raw_field = mapping.nautobot_field

                if not validate_nautobot_field(model_class, raw_field):
                    continue

                # Custom fields (_cf_<key>) need special handling:
                # 1. Strip leading underscore so Pydantic v2 doesn't treat them as private
                # 2. Annotate with CustomFieldAnnotation so NautobotAdapter reads obj.cf[key]
                if raw_field.startswith("_cf_"):
                    field_name = raw_field[1:]  # _cf_device_id → cf_device_id
                    cf_key = raw_field[4:]  # _cf_device_id → device_id
                    annotations[field_name] = Annotated[Optional[str], CustomFieldAnnotation(key=cf_key)]
                else:
                    # Strip leading underscore to match the external adapter
                    # (Pydantic v2 treats _ prefixed fields as private).
                    field_name = raw_field[1:] if raw_field.startswith("_") else raw_field
                    annotations[field_name] = Optional[str]

                # Deduplicate fields across endpoints mapping the same content type.
                if field_name in seen_fields:
                    continue
                seen_fields.add(field_name)

                if mapping.is_identifier:
                    identifiers.append(field_name)
                elif not is_stub:
                    # Stub models only get identifiers, no attributes.
                    attributes.append(field_name)

            # Auto-add required FK fields not in user mappings with sensible defaults.
            mapped_fields = {m.nautobot_field for m in mappings}
            required_defaults = get_required_unmapped_fk_defaults(model_class, mapped_fields)
            for ds_field, default_val in required_defaults.items():
                if ds_field not in seen_fields:
                    attributes.append(ds_field)
                    annotations[ds_field] = Optional[str]
                    seen_fields.add(ds_field)

            class_name = f"Nautobot{model_class.__name__}"
            # NautobotModel (parent) already declares ``pk``; do not re-add it
            # to annotations or the namespace or Pydantic will emit a shadow warning.
            annotations.pop("pk", None)

            ns = {
                "__module__": __name__,
                "__qualname__": class_name,
                "__annotations__": annotations,
                # Coerce ORM integers (e.g. IPAddress.mask_length) to str
                # so Pydantic v2 doesn't reject them for Optional[str] fields.
                "model_config": ConfigDict(arbitrary_types_allowed=True, coerce_numbers_to_str=True),
                "_modelname": model_key,
                "_model": model_class,
                "_identifiers": tuple(identifiers),
                "_attributes": tuple(attributes),
            }
            # Provide defaults so fields are not required at instantiation.
            for field_name in annotations:
                ns.setdefault(field_name, "")
            # Set known defaults for auto-added required fields.
            for ds_field, default_val in required_defaults.items():
                ns[ds_field] = default_val
            nautobot_model_class = type(class_name, (NautobotModel,), ns)

            # If target is IPAddress, wrap create to auto-create parent prefix.
            if model_class is NautobotIPAddress:

                @classmethod  # type: ignore[misc]
                def _create_with_prefix(cls, adapter, ids, attrs):
                    GenericNautobotAdapter._auto_create_parent_prefix({**ids, **attrs})
                    return NautobotModel.create.__func__(cls, adapter, ids, attrs)

                nautobot_model_class.create = _create_with_prefix

            setattr(self, model_key, nautobot_model_class)

            if not hasattr(self, "top_level") or not self.top_level:
                self.top_level = [model_key]
            elif model_key not in self.top_level:
                self.top_level.append(model_key)

            logger.debug(f"Created Nautobot model: {class_name} with identifiers {identifiers}")

    def _order_top_level_by_dependencies(self):
        """Topologically sort ``self.top_level`` so referenced models come first.

        Inspects ``__`` FK traversal fields in the model mappings to build a
        dependency graph.  Uses Kahn's algorithm; falls back to original
        ordering if a cycle is detected.
        """
        if not hasattr(self, "top_level") or not self.top_level or len(self.top_level) <= 1:
            return

        # model_key → set of model_keys it depends on
        deps = {mk: set() for mk in self.top_level}
        model_key_by_model = {}
        for mk in self.top_level:
            model_class = getattr(self, mk, None)
            if model_class and hasattr(model_class, "_model"):
                ct = ContentType.objects.get_for_model(model_class._model)
                model_key_by_model[ct.id] = mk

        for mk in self.top_level:
            model_class = getattr(self, mk, None)
            if not model_class or not hasattr(model_class, "_model"):
                continue
            django_model = model_class._model

            # Check all attributes and identifiers for FK traversal
            all_fields = list(model_class._identifiers) + list(model_class._attributes)
            for field_name in all_fields:
                if "__" not in field_name:
                    continue
                fk_name = field_name.split("__", maxsplit=1)[0]
                try:
                    fk_field = django_model._meta.get_field(fk_name)
                    if fk_field.is_relation and fk_field.related_model:
                        related_ct = ContentType.objects.get_for_model(fk_field.related_model)
                        related_key = model_key_by_model.get(related_ct.id)
                        if related_key and related_key != mk and related_key in deps:
                            deps[mk].add(related_key)
                except Exception:
                    continue

        # Kahn's algorithm
        in_degree = {mk: len(dep_set) for mk, dep_set in deps.items()}
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

    def _load_single_object(self, database_object, diffsync_model, parameter_names):
        """Load a single object, skipping duplicates that share the same identifier values."""
        try:
            return super()._load_single_object(database_object, diffsync_model, parameter_names)
        except ObjectAlreadyExists:
            ids = {f: getattr(database_object, f, "") for f in diffsync_model._identifiers}
            logger.warning(
                "Skipping duplicate %s object (identifiers: %s)",
                diffsync_model._modelname,
                ids,
            )
            return None
