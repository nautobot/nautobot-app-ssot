"""FK resolution strategies for output fields.

Each FK field in an output declares how to handle a missing related object:
``lookup_only``/``skip_record``/``skip_field`` (find or bail), ``create``
(get_or_create with defaults, including ``__``-traversal parent creation),
or ``static`` (always the same object, ignore the source).
"""

from typing import Any, Dict

from nautobot_ssot.integrations.data_import.engine.introspect import natural_lookup_field


class Sentinel:
    """Named sentinel for resolver outcomes."""

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"<{self.name}>"


SKIP_RECORD = Sentinel("SKIP_RECORD")
SKIP_FIELD = Sentinel("SKIP_FIELD")


class FKResolver:
    """Resolves FK field values to model instances, with a per-run cache."""

    def __init__(self, dry_run: bool = False, logger=None):
        self.dry_run = dry_run
        self.logger = logger
        # (model_label, lookup_field, value) -> instance | None
        self._cache: Dict[tuple, Any] = {}
        # Objects "created" during dry-run so repeats resolve consistently.
        self._dry_created: Dict[tuple, Dict] = {}
        # Dry-run only: objects PROJECTED by earlier outputs in this run
        # (e.g. Devices that a later Interface output must resolve against).
        self._projected: Dict[str, list] = {}  # model_label -> [values dict]
        self.created_related: list = []  # [(model_label, value)] for reporting

    def register_projected(self, model_class, values: Dict[str, Any]):
        """Record an object an earlier output would create (dry-run only).

        Later outputs' FK lookups consult these, so a dry-run correctly shows
        an Interface resolving against a Device created earlier in the same
        run instead of falsely reporting it as unresolvable.
        """
        self._projected.setdefault(self._label(model_class), []).append(values)

    def resolve(self, django_field, fk_cfg: Dict, raw_value: Any, row: Dict) -> Any:
        """Resolve one FK field.

        Returns a model instance, ``None`` (leave unset), ``SKIP_RECORD``,
        ``SKIP_FIELD``, or for dry-run-created objects a dict marker
        ``{"__dry_created__": ..., "value": ...}``.
        """
        related_model = django_field.related_model
        strategy = (fk_cfg or {}).get("on_missing", "skip_record")
        lookup_field = (fk_cfg or {}).get("lookup_field") or natural_lookup_field(related_model)

        if strategy == "static":
            static_value = (fk_cfg or {}).get("static_value")
            if static_value in (None, ""):
                return SKIP_FIELD
            found = self._lookup(related_model, lookup_field, static_value)
            if found is not None:
                found = self._check_scope(found, django_field, extend=True)
            if found is None and self.logger:
                self.logger.warning(
                    "Static value %r not found for %s.%s", static_value, related_model.__name__, lookup_field
                )
            return found if found is not None else SKIP_RECORD

        if raw_value in (None, ""):
            return SKIP_FIELD

        found = self._lookup(related_model, lookup_field, raw_value)
        if found is not None:
            # Objects like Status/Role are scoped by content_types — a match
            # not enabled for the target model would fail validation later.
            scoped = self._check_scope(found, django_field, extend=(strategy == "create"))
            if scoped is not None:
                return scoped
            if strategy in ("skip_record", "lookup_only"):
                return SKIP_RECORD
            if strategy == "skip_field":
                return SKIP_FIELD
            # strategy == "create" never lands here (extend=True always succeeds)

        if strategy in ("skip_record", "lookup_only"):
            return SKIP_RECORD
        if strategy == "skip_field":
            return SKIP_FIELD
        if strategy == "create":
            return self._create(related_model, lookup_field, raw_value, fk_cfg, row)

        return SKIP_RECORD

    # Models whose content_types M2M scopes WHICH models may reference them.
    _SCOPED_MODELS = ("status", "role", "tag")

    def _check_scope(self, instance, django_field, extend: bool):
        """Verify a found Status/Role/Tag is enabled for the target model.

        Returns the instance when in scope. When out of scope: extends the
        object's content_types if ``extend`` (user opted into mutation via
        create/static strategy), else warns and returns None (treat as miss).
        Dry-run markers and non-scoped models pass through untouched.
        """
        if isinstance(instance, dict):  # dry-run / projected marker
            return instance
        if instance._meta.model_name not in self._SCOPED_MODELS or not hasattr(instance, "content_types"):
            return instance

        from django.contrib.contenttypes.models import ContentType  # pylint: disable=import-outside-toplevel

        owner_ct = ContentType.objects.get_for_model(django_field.model)
        if instance.content_types.filter(pk=owner_ct.pk).exists():
            return instance
        if extend:
            if self.dry_run:
                return instance  # would be extended on a live run
            instance.content_types.add(owner_ct)
            if self.logger:
                self.logger.info(
                    "Enabled %s %r for %s.%s (it existed but was not permitted for this model)",
                    instance._meta.model_name,
                    str(instance),
                    owner_ct.app_label,
                    owner_ct.model,
                )
            return instance
        if self.logger:
            self.logger.warning(
                "%s %r exists but is not enabled for %s.%s — enable it under its content types, "
                "or use the 'Lookup or create' strategy to extend it automatically.",
                instance._meta.model_name,
                str(instance),
                owner_ct.app_label,
                owner_ct.model,
            )
        return None

    # ── internals ──────────────────────────────────────────────────────────

    def _label(self, model_class) -> str:
        return f"{model_class._meta.app_label}.{model_class._meta.model_name}"

    def _lookup(self, model_class, lookup_field: str, value: Any):
        key = (self._label(model_class), lookup_field, str(value))
        # _dry_created wins over _cache: a cached miss (None) recorded before
        # the dry-create happened must not shadow the created marker.
        if key in self._dry_created:
            return self._dry_created[key]
        if key in self._cache and self._cache[key] is not None:
            return self._cache[key]
        instance = None
        for lookup_kwargs in self._lookup_candidates(model_class, lookup_field, value):
            try:
                instance = model_class.objects.filter(**lookup_kwargs).first()
            except Exception:  # pylint: disable=broad-exception-caught
                # Unsupported lookup for this field type (e.g. iexact on a
                # binary IP field) — fall through to the next candidate.
                continue
            if instance is not None:
                break
        if instance is None and self.dry_run:
            instance = self._lookup_projected(model_class, lookup_field, value)
        self._cache[key] = instance
        return instance

    def _lookup_projected(self, model_class, lookup_field: str, value: Any):
        """Match against objects projected by earlier outputs (dry-run only)."""
        for values in self._projected.get(self._label(model_class), []):
            candidate = values.get(lookup_field)
            if candidate is None:
                continue
            if str(candidate).strip().lower() == str(value).strip().lower():
                return {"__pending__": self._label(model_class), "value": str(candidate)}
        return None

    @staticmethod
    def _lookup_candidates(model_class, lookup_field: str, value: Any):
        """Yield filter kwargs to try, best-first, based on the field type.

        - ``_cf_<key>`` lookup fields translate to JSON queries on
          ``_custom_field_data`` (trying both string and numeric forms,
          since JSON preserves types but API/CSV values arrive as strings).
        - Text fields use case-insensitive match.
        - Everything else (IP fields, integers, UUIDs…) uses exact match —
          ``iexact`` is only valid on text columns.
        """
        from django.db.models import CharField, SlugField, TextField  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.introspect import (  # pylint: disable=import-outside-toplevel
            CUSTOM_FIELD_PREFIX,
        )

        if lookup_field.startswith(CUSTOM_FIELD_PREFIX):
            cf_key = lookup_field[len(CUSTOM_FIELD_PREFIX) :]
            yield {f"_custom_field_data__{cf_key}": value}
            str_value = str(value)
            if str_value != value:
                yield {f"_custom_field_data__{cf_key}": str_value}
            try:
                int_value = int(str_value)
                yield {f"_custom_field_data__{cf_key}": int_value}
            except (ValueError, TypeError):
                pass
            return

        try:
            field = model_class._meta.get_field(lookup_field)
        except Exception:  # pylint: disable=broad-exception-caught
            field = None

        if field is not None and isinstance(field, (CharField, TextField, SlugField)):
            yield {f"{lookup_field}__iexact": str(value)}
        yield {lookup_field: value}
        if not isinstance(value, str):
            yield {lookup_field: str(value)}

    def _create(self, model_class, lookup_field: str, value: Any, fk_cfg: Dict, row: Dict):
        """get_or_create the related object, resolving create_defaults."""
        defaults = {}
        for def_key, def_spec in ((fk_cfg or {}).get("create_defaults") or {}).items():
            # Dict spec {"column": ...} or {"fixed": ...}; anything else is a literal.
            if isinstance(def_spec, dict):
                def_value = row.get(def_spec["column"]) if def_spec.get("column") else def_spec.get("fixed")
            else:
                def_value = def_spec
            if def_value in (None, ""):
                continue

            if "__" in def_key:
                # Parent traversal: resolve/create the related parent by its lookup.
                parent_field_name, parent_lookup = def_key.split("__", maxsplit=1)
                try:
                    parent_field = model_class._meta.get_field(parent_field_name)
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
                if not parent_field.is_relation:
                    continue
                parent_model = parent_field.related_model
                parent = self._lookup(parent_model, parent_lookup, def_value)
                if parent is None:
                    parent = self._create(parent_model, parent_lookup, def_value, {}, row)
                if parent is not None and not isinstance(parent, Sentinel):
                    defaults[parent_field_name] = parent
            else:
                try:
                    field_obj = model_class._meta.get_field(def_key)
                    if field_obj.many_to_many:
                        continue  # M2M handled post-create below (content_types etc.)
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
                defaults[def_key] = def_value

        # Auto-fill required parents not covered by defaults (best effort).
        for field in model_class._meta.concrete_fields:
            if not field.is_relation or field.related_model is None or field.name in defaults:
                continue
            required = (
                not field.has_default() and not getattr(field, "null", False) and not getattr(field, "blank", False)
            )
            if not required:
                continue
            parent_model = field.related_model
            parent_lookup = natural_lookup_field(parent_model)
            # Try a couple of sensible defaults before giving up.
            for candidate in ("Active", "Unknown"):
                parent = self._lookup(parent_model, parent_lookup, candidate)
                if parent is not None:
                    defaults[field.name] = parent
                    break
            else:
                parent = self._create(parent_model, parent_lookup, "Unknown", {}, row)
                if parent is not None and not isinstance(parent, Sentinel):
                    defaults[field.name] = parent

        key = (self._label(model_class), lookup_field, str(value))

        if self.dry_run:
            marker = {"__dry_created__": self._label(model_class), "value": str(value)}
            self._dry_created[key] = marker
            self.created_related.append((self._label(model_class), str(value)))
            return marker

        from nautobot_ssot.integrations.data_import.engine.introspect import (  # pylint: disable=import-outside-toplevel
            CUSTOM_FIELD_PREFIX,
        )

        try:
            if lookup_field.startswith(CUSTOM_FIELD_PREFIX):
                # Custom-field lookups can't go through get_or_create kwargs;
                # build the object manually with the CF value set.
                cf_key = lookup_field[len(CUSTOM_FIELD_PREFIX) :]
                instance = self._lookup(model_class, lookup_field, value)
                created = instance is None
                if created:
                    instance = model_class(**defaults)
                    instance.custom_field_data[cf_key] = value
                    instance.validated_save()
            elif self._label(model_class) == "ipam.ipaddress":
                # IPAddresses can't be built from a bare host string — they
                # need a mask and a parent Prefix in a Namespace.
                instance, created = self._create_ip_address(model_class, value, defaults)
            else:
                instance, created = model_class.objects.get_or_create(**{lookup_field: str(value)}, defaults=defaults)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if self.logger:
                self.logger.warning("Could not auto-create %s %r: %s", model_class.__name__, value, exc)
            return SKIP_RECORD

        if created:
            self.created_related.append((self._label(model_class), str(value)))
            # Status/Role/etc. need content_types assigned to be usable.
            self._assign_content_types(instance)
            if self.logger:
                self.logger.info("Auto-created %s %r", model_class.__name__, str(value))

        self._cache[key] = instance
        return instance

    def _create_ip_address(self, model_class, value, defaults):
        """Create an IPAddress from a host string, satisfying Nautobot's rules.

        - No mask given → /32 (IPv4) or /128 (IPv6), the host convention.
        - Uses the Global namespace (Nautobot's default).
        - IPAddresses require a containing parent Prefix; if none exists, a
          covering /24 (IPv4) or /64 (IPv6) container prefix is auto-created
          and reported, so the user can retype/re-parent it later.
        """
        import ipaddress as ip_module  # pylint: disable=import-outside-toplevel

        from nautobot.extras.models import Status  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Namespace, Prefix  # pylint: disable=import-outside-toplevel

        raw = str(value).strip()
        if "/" not in raw:
            raw = f"{raw}/128" if ":" in raw else f"{raw}/32"
        interface = ip_module.ip_interface(raw)  # raises ValueError on garbage → caught by caller

        namespace = Namespace.objects.filter(name="Global").first() or Namespace.objects.first()
        status = defaults.get("status") or Status.objects.get(name="Active")

        def _make():
            return model_class.objects.create(address=str(interface), namespace=namespace, status=status)

        from django.db import transaction  # pylint: disable=import-outside-toplevel

        try:
            with transaction.atomic():  # savepoint: a failed INSERT must not poison the outer transaction
                return _make(), True
        except Exception:  # pylint: disable=broad-exception-caught
            # Most likely: no containing parent Prefix. Create a covering
            # container and retry once.
            container_bits = 64 if interface.version == 6 else 24
            prefix_len = min(interface.network.prefixlen, container_bits)
            container = ip_module.ip_network(f"{interface.ip}/{prefix_len}", strict=False)
            if not Prefix.objects.filter(
                network=str(container.network_address), prefix_length=container.prefixlen, namespace=namespace
            ).exists():
                Prefix.objects.create(prefix=str(container), namespace=namespace, status=status)
                self.created_related.append(("ipam.prefix", str(container)))
                if self.logger:
                    self.logger.info(
                        "Auto-created parent Prefix %s in namespace %s (no containing prefix existed)",
                        container,
                        namespace,
                    )
            return _make(), True

    # For content-type-scoped models, which field on OTHER models implies
    # membership. E.g. a LocationType's content_types govern what may be
    # placed at its locations — any model with a ``location`` FK qualifies.
    _CONTENT_TYPE_FEATURE_FIELDS = {
        "status": "status",
        "role": "role",
        "tag": "tags",
        "locationtype": "location",
    }

    def _assign_content_types(self, instance):
        """If the created object has a content_types M2M (Status, Role,
        LocationType, Tag…), make it valid for every relevant model so
        imports don't fail validation.
        """
        from django.contrib.contenttypes.models import ContentType  # pylint: disable=import-outside-toplevel

        if not hasattr(instance, "content_types"):
            return
        try:
            feature_field = self._CONTENT_TYPE_FEATURE_FIELDS.get(instance._meta.model_name)
            if feature_field is None:
                return
            query = ContentType.objects.filter(app_label__in=["dcim", "ipam", "circuits", "tenancy", "extras"])
            valid = []
            for content_type in query:
                model_class = content_type.model_class()
                if model_class is None:
                    continue
                # Attach to models that actually carry this relation
                # (get_fields includes M2M like tags, unlike concrete_fields).
                if any(f.name == feature_field for f in model_class._meta.get_fields()):
                    valid.append(content_type)
            if valid:
                instance.content_types.add(*valid)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
