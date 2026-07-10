"""Batched upsert loader: rows → Nautobot objects (or a dry-run report).

Per batch: build values (column/fixed/value_map/type_cast), resolve FKs via
the shared FKResolver, one SELECT for existing objects by identifier, then
partition into create / update / skip. Writes use ``validated_save()`` for
correctness; the batch-shaped interface leaves room for bulk_* later.
"""

from typing import Any, Dict, List

from nautobot_ssot.integrations.data_import.engine.introspect import (
    CUSTOM_FIELD_PREFIX,
    get_django_field,
)
from nautobot_ssot.integrations.data_import.engine.resolver import SKIP_FIELD, SKIP_RECORD, Sentinel

BATCH_SIZE = 500

# Device fields that Nautobot only accepts once the IP is assigned to one of
# the device's interfaces — handled via deferred assignment after save.
PRIMARY_IP_FIELDS = ("primary_ip4", "primary_ip6")


def _cast(value: Any, target_type: str) -> Any:
    """Best-effort type cast; returns original value on failure."""
    try:
        if target_type in ("int", "integer"):
            return int(float(value))
        if target_type == "float":
            return float(value)
        if target_type in ("bool", "boolean"):
            return str(value).strip().lower() in ("1", "true", "yes", "y", "on", "up")
        if target_type in ("str", "string"):
            return str(value)
    except (ValueError, TypeError):
        pass
    return value


def extract_value(spec: Dict, row: Dict) -> Any:
    """Apply one field spec (column/fixed → value_map → type_cast) to a row."""
    if not isinstance(spec, dict):
        return spec

    if "fixed" in spec:
        value = spec["fixed"]
    elif spec.get("column"):
        value = row.get(spec["column"])
    else:
        value = None

    if value in (None, ""):
        if "default" in spec:
            value = spec["default"]
        else:
            return None

    value_map = spec.get("value_map")
    if isinstance(value_map, dict) and value_map:
        mapped = value_map.get(str(value), value_map.get(value))
        if mapped is not None:
            value = mapped

    if spec.get("type_cast"):
        value = _cast(value, spec["type_cast"])

    return value


def _values_differ(existing_value: Any, new_value: Any) -> bool:
    """Loose comparison so '1' == 1 and FK instance == instance."""
    if existing_value is None and new_value is None:
        return False
    if hasattr(existing_value, "pk") and hasattr(new_value, "pk"):
        return existing_value.pk != new_value.pk
    return str(existing_value) != str(new_value)


def load_output(
    model_class,
    output_cfg: Dict,
    rows: List[Dict],
    resolver,
    dry_run: bool,
    logger,
    on_record_error: str = "continue",
) -> Dict[str, Any]:
    """Import all rows of one output. Returns a summary dict."""
    identifiers_cfg: Dict[str, Dict] = output_cfg.get("identifiers") or {}
    fields_cfg: Dict[str, Dict] = output_cfg.get("fields") or {}
    summary = {
        "target": output_cfg.get("to"),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "unchanged": 0,
        "errors": [],
        "records": [],  # dry-run detail: {action, identifier, changes}
    }

    if not identifiers_cfg:
        summary["errors"].append("Output has no identifier fields configured.")
        return summary

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]

        # Phase 1: build per-row values.
        prepared = []  # (ident_values, field_values, deferred, row)
        for row_index, row in enumerate(batch, start=start + 1):
            try:
                ident_values: Dict[str, Any] = {}
                ident_problem = None
                for field_name, spec in identifiers_cfg.items():
                    value = extract_value(spec, row)
                    if value in (None, ""):
                        ident_problem = "missing identifier"
                        break
                    # FK identifiers (e.g. Interface.device) resolve like fields
                    # so composite identity (name + device) works.
                    django_field = get_django_field(model_class, field_name)
                    if django_field is not None and django_field.is_relation:
                        resolved = resolver.resolve(django_field, spec.get("fk"), value, row)
                        if resolved is SKIP_RECORD or resolved is SKIP_FIELD or resolved is None:
                            ident_problem = f"unresolved identifier {field_name}: {value!r}"
                            break
                        value = resolved
                    ident_values[field_name] = value
                if ident_problem:
                    summary["skipped"] += 1
                    summary["records"].append({"action": "skip", "reason": ident_problem, "row": row_index})
                    continue

                field_values: Dict[str, Any] = {}
                skip_record = False
                for field_name, spec in fields_cfg.items():
                    raw_value = extract_value(spec, row)
                    django_field = get_django_field(model_class, field_name)

                    if django_field is not None and django_field.is_relation:
                        resolved = resolver.resolve(django_field, spec.get("fk"), raw_value, row)
                        if resolved is SKIP_RECORD:
                            skip_record = True
                            summary["records"].append(
                                {
                                    "action": "skip",
                                    "reason": f"unresolved {field_name}: {raw_value!r}",
                                    "identifier": next(iter(ident_values.values())),
                                }
                            )
                            break
                        if resolved is SKIP_FIELD or resolved is None:
                            continue
                        field_values[field_name] = resolved
                    else:
                        if raw_value is None:
                            continue
                        # Pre-validate with Django's own field logic: casts
                        # types and catches bad choices / out-of-range values
                        # BEFORE save, so problems become actionable skips
                        # (required field) or dropped fields (optional).
                        if django_field is not None:
                            try:
                                raw_value = django_field.clean(raw_value, None)
                            except Exception as exc:  # pylint: disable=broad-exception-caught
                                message = "; ".join(getattr(exc, "messages", None) or [str(exc)])
                                hint = ""
                                if getattr(django_field, "choices", None):
                                    # flatchoices flattens grouped choices to (value, label) pairs.
                                    flat = list(getattr(django_field, "flatchoices", None) or django_field.choices)
                                    valid = [str(choice[0]) for choice in flat][:12]
                                    hint = f" — map it to a valid value ({', '.join(valid)}, …)"
                                field_required = (
                                    not django_field.has_default()
                                    and not getattr(django_field, "null", False)
                                    and not getattr(django_field, "blank", False)
                                )
                                if field_required:
                                    skip_record = True
                                    summary["records"].append(
                                        {
                                            "action": "skip",
                                            "reason": f"{field_name}: {message}{hint}",
                                            "identifier": next(iter(ident_values.values())),
                                        }
                                    )
                                    break
                                summary["errors"].append(
                                    f"{next(iter(ident_values.values()))}: dropped optional field "
                                    f"{field_name} — {message}{hint}"
                                )
                                continue
                        field_values[field_name] = raw_value

                if skip_record:
                    summary["skipped"] += 1
                    continue

                # Mapped required fields that resolved to nothing would fail
                # model validation with a cryptic error — skip with a clear
                # reason instead (the user can set a per-field default).
                missing_required = []
                for field_name in fields_cfg:
                    if field_name in field_values:
                        continue
                    django_field = get_django_field(model_class, field_name)
                    if django_field is None:
                        continue
                    required = (
                        not django_field.has_default()
                        and not getattr(django_field, "null", False)
                        and not getattr(django_field, "blank", False)
                    )
                    if required:
                        missing_required.append(field_name)
                if missing_required:
                    summary["skipped"] += 1
                    summary["records"].append(
                        {
                            "action": "skip",
                            "reason": (
                                f"required field(s) {', '.join(missing_required)} have no value for this record "
                                "(set a default in the field settings, or fix the source data)"
                            ),
                            "identifier": next(iter(ident_values.values())),
                        }
                    )
                    continue

                # primary_ip4/6 can only be set AFTER the IP is assigned to
                # one of the device's interfaces — defer them (live runs).
                deferred: Dict[str, Any] = {}
                if not dry_run:
                    for primary_field in PRIMARY_IP_FIELDS:
                        if primary_field in field_values:
                            deferred[primary_field] = field_values.pop(primary_field)

                prepared.append((ident_values, field_values, deferred, row))
            except Exception as exc:  # pylint: disable=broad-exception-caught
                summary["errors"].append(f"row {row_index}: {exc}")
                if on_record_error == "abort":
                    raise

        if not prepared:
            continue

        # Phase 2: one SELECT for existing objects in this batch, matched on
        # the FULL composite identifier (e.g. Interface: name + device).
        first_ident_field = next(iter(identifiers_cfg))
        filter_values = []
        for ident, _, _, _ in prepared:
            value = ident[first_ident_field]
            if hasattr(value, "pk"):
                filter_values.append(value.pk)
            elif not isinstance(value, dict):  # exclude dry-run markers
                filter_values.append(value)
        if first_ident_field.startswith(CUSTOM_FIELD_PREFIX):
            cf_key = first_ident_field[len(CUSTOM_FIELD_PREFIX) :]
            filter_kwargs = {f"_custom_field_data__{cf_key}__in": filter_values}
        else:
            first_django_field = get_django_field(model_class, first_ident_field)
            if first_django_field is not None and first_django_field.is_relation:
                filter_kwargs = {f"{first_ident_field}_id__in": filter_values}
            else:
                filter_kwargs = {f"{first_ident_field}__in": filter_values}
        existing_by_key: Dict[tuple, Any] = {}
        for obj in model_class.objects.filter(**filter_kwargs):
            existing_by_key[_ident_key_from_obj(obj, identifiers_cfg, model_class)] = obj

        # Phase 3: create / update / unchanged.
        for ident_values, field_values, deferred, row in prepared:
            ident_display = " / ".join(display_value(v) for v in ident_values.values())
            try:
                existing = existing_by_key.get(_ident_key_from_values(ident_values))
                if existing is None:
                    obj = _apply_and_save(
                        model_class, ident_values, field_values, dry_run, summary, "create", ident_display, resolver
                    )
                    if obj is not None:
                        for primary_field, ip_instance in deferred.items():
                            _assign_primary_ip(obj, primary_field, ip_instance, logger)
                        summary["records"].append(
                            {
                                "action": "create",
                                "identifier": ident_display,
                                "pk": str(obj.pk),
                                "values": {
                                    key: display_value(value) for key, value in {**ident_values, **field_values}.items()
                                },
                            }
                        )
                else:
                    changes = {}
                    for field_name, new_value in field_values.items():
                        if field_name.startswith(CUSTOM_FIELD_PREFIX):
                            cf_key = field_name[len(CUSTOM_FIELD_PREFIX) :]
                            if _values_differ(existing.custom_field_data.get(cf_key), new_value):
                                changes[field_name] = new_value
                        elif _values_differ(getattr(existing, field_name, None), new_value):
                            changes[field_name] = new_value
                    deferred_changes = {
                        primary_field: ip_instance
                        for primary_field, ip_instance in deferred.items()
                        if _values_differ(getattr(existing, primary_field, None), ip_instance)
                    }
                    if not changes and not deferred_changes:
                        summary["unchanged"] += 1
                        summary["records"].append(
                            {"action": "unchanged", "identifier": ident_display, "pk": str(existing.pk)}
                        )
                        continue
                    if dry_run:
                        summary["updated"] += 1
                        summary["records"].append(
                            {
                                "action": "update",
                                "identifier": ident_display,
                                "pk": str(existing.pk),
                                "changes": {k: display_value(v) for k, v in changes.items()},
                            }
                        )
                    else:
                        if changes:
                            for field_name, new_value in changes.items():
                                _set_field(existing, field_name, new_value)
                            _validated_save_with_recovery(existing, model_class, set(changes), ident_display, summary)
                        for primary_field, ip_instance in deferred_changes.items():
                            _assign_primary_ip(existing, primary_field, ip_instance, logger)
                        summary["updated"] += 1
                        summary["records"].append(
                            {
                                "action": "update",
                                "identifier": ident_display,
                                "pk": str(existing.pk),
                                "changes": {k: display_value(v) for k, v in {**changes, **deferred_changes}.items()},
                            }
                        )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                summary["errors"].append(f"{ident_display}: {exc}")
                summary["records"].append({"action": "error", "identifier": ident_display, "reason": str(exc)})
                if logger:
                    logger.warning("Error importing %s: %s", ident_display, exc)
                if on_record_error == "abort":
                    raise

    summary["errors"] = _dedupe_errors(summary["errors"])
    return summary


def _dedupe_errors(errors: List[str], cap: int = 25) -> List[str]:
    """Collapse repeated error messages (same root cause across many rows).

    Messages are grouped ignoring the leading "row N:" / "identifier:" prefix
    so one bad mapping produces one line with a count, not one line per row.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for message in errors:
        _, _, root = message.partition(": ")
        key = root or message
        if key not in groups:
            groups[key] = {"first": message, "count": 0}
        groups[key]["count"] += 1
    collapsed = [
        entry["first"] + (f"  (×{entry['count']} rows)" if entry["count"] > 1 else "") for entry in groups.values()
    ]
    if len(collapsed) > cap:
        collapsed = collapsed[:cap] + [f"… and {len(collapsed) - cap} more distinct errors"]
    return collapsed


def _set_field(obj, field_name: str, value: Any):
    """Assign a value, routing _cf_ names into custom_field_data."""
    if field_name.startswith(CUSTOM_FIELD_PREFIX):
        obj.custom_field_data[field_name[len(CUSTOM_FIELD_PREFIX) :]] = value
    else:
        setattr(obj, field_name, value)


def _ident_key_from_values(ident_values: Dict[str, Any]) -> tuple:
    """Composite match key from a row's resolved identifier values."""
    parts = []
    for value in ident_values.values():
        if isinstance(value, dict):  # dry-run marker
            parts.append(str(value.get("value", "")))
        elif hasattr(value, "pk"):
            parts.append(str(value.pk))
        else:
            parts.append(str(value))
    return tuple(parts)


def _ident_key_from_obj(obj, identifiers_cfg: Dict, model_class) -> tuple:
    """Composite match key from an existing DB object."""
    parts = []
    for field_name in identifiers_cfg:
        if field_name.startswith(CUSTOM_FIELD_PREFIX):
            parts.append(str(obj.custom_field_data.get(field_name[len(CUSTOM_FIELD_PREFIX) :], "")))
        else:
            django_field = get_django_field(model_class, field_name)
            if django_field is not None and django_field.is_relation:
                parts.append(str(getattr(obj, f"{field_name}_id", "")))
            else:
                parts.append(str(getattr(obj, field_name, "")))
    return tuple(parts)


def _validated_save_with_recovery(obj, model_class, candidate_fields, ident_display, summary):
    """validated_save, retrying once with offending OPTIONAL fields dropped.

    Catches cross-field model validation Django field-level checks can't see
    (e.g. "Speed is not applicable to this interface type"). Required-field
    errors still propagate.
    """
    from django.core.exceptions import ValidationError  # pylint: disable=import-outside-toplevel

    try:
        obj.validated_save()
        return
    except ValidationError as exc:
        error_dict = getattr(exc, "message_dict", None) or {}
        droppable = []
        for error_field in error_dict:
            if error_field in ("__all__", "all") or error_field not in candidate_fields:
                raise
            django_field = get_django_field(model_class, error_field)
            if django_field is None:
                raise
            optional = (
                django_field.has_default()
                or getattr(django_field, "null", False)
                or getattr(django_field, "blank", False)
            )
            if not optional:
                raise
            droppable.append(error_field)
        if not droppable:
            raise
        for error_field in droppable:
            django_field = get_django_field(model_class, error_field)
            fallback = django_field.get_default() if django_field.has_default() else None
            setattr(obj, error_field, fallback)
        obj.validated_save()  # second failure propagates to the caller
        messages = "; ".join(f"{f}: {'; '.join(error_dict[f])}" for f in droppable)
        summary["errors"].append(f"{ident_display}: imported without {', '.join(droppable)} — {messages}")


def display_value(value: Any) -> str:
    """Human-readable form of a field value for dry-run reports.

    Resolver markers render as their target value plus a short annotation
    instead of the raw marker dict.
    """
    if isinstance(value, dict):
        if "__dry_created__" in value:
            return f"{value.get('value')} (will create)"
        if "__pending__" in value:
            return f"{value.get('value')} (created earlier in this import)"
    return str(value)


def _apply_and_save(model_class, ident_values, field_values, dry_run, summary, action, ident_display, resolver=None):
    """Create a new object (or record the projected create in dry-run).

    Returns the created instance (None in dry-run).
    """
    if dry_run:
        summary["created"] += 1
        summary["records"].append(
            {
                "action": "create",
                "identifier": ident_display,
                "values": {
                    key: display_value(value)
                    for key, value in {**ident_values, **field_values}.items()
                    if not isinstance(value, Sentinel)
                },
            }
        )
        # Make this projected object visible to later outputs' FK lookups.
        if resolver is not None:
            resolver.register_projected(model_class, {**ident_values, **field_values})
        return None

    obj = model_class()
    for field_name, value in {**ident_values, **field_values}.items():
        _set_field(obj, field_name, value)
    _validated_save_with_recovery(obj, model_class, set(field_values), ident_display, summary)
    summary["created"] += 1
    return obj


def _assign_primary_ip(device, field_name: str, ip_instance, logger):
    """Set a device's primary IP the way Nautobot requires.

    A primary IP must be assigned to one of the device's interfaces. If it
    isn't yet, assign it to a ``mgmt`` interface (created on demand) — the
    same convention the device-onboarding app uses — then set the primary.
    """
    from nautobot.dcim.models import Interface  # pylint: disable=import-outside-toplevel
    from nautobot.extras.models import Status  # pylint: disable=import-outside-toplevel
    from nautobot.ipam.models import IPAddressToInterface  # pylint: disable=import-outside-toplevel

    already_assigned = IPAddressToInterface.objects.filter(ip_address=ip_instance, interface__device=device).exists()
    if not already_assigned:
        interface, created = Interface.objects.get_or_create(
            device=device,
            name="mgmt",
            defaults={"status": Status.objects.get(name="Active"), "type": "other"},
        )
        IPAddressToInterface.objects.get_or_create(ip_address=ip_instance, interface=interface)
        if created and logger:
            logger.info("Created interface 'mgmt' on %s to hold primary IP %s", device.name, ip_instance)
    setattr(device, field_name, ip_instance)
    device.validated_save()
