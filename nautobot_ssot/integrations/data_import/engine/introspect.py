"""Nautobot schema introspection.

One source of truth for "what does this Nautobot model need" — used by the
builder UI (chip palette) and the engine (validation, FK resolution).
"""

from typing import Any, Dict, List, Optional

from django.core.exceptions import FieldDoesNotExist

# Fields never shown in the builder or written by the engine.
SKIP_FIELDS = {
    "id",
    "pk",
    "created",
    "last_updated",
    "_custom_field_data",
    "custom_field_data",
    "tags",
    "object_id",
    "content_type",
    "_name",
    "natural_slug",
}
SKIP_PREFIXES = ("local_config_context", "_custom_field")

# Prefix marking custom-field targets in output field names.
CUSTOM_FIELD_PREFIX = "_cf_"


def natural_lookup_field(model_class) -> str:
    """Best simple lookup field for a model (used for FK resolution by value).

    Prefers Nautobot's ``natural_key_field_lookups``; falls back to the first
    non-FK concrete field.
    """
    if hasattr(model_class, "natural_key_field_lookups"):
        for lookup in model_class.natural_key_field_lookups:
            if "__" not in lookup:
                return lookup
    for field in model_class._meta.concrete_fields:
        if not field.primary_key and not field.is_relation:
            return field.name
    return "pk"


def _required_parent_fks(model_class) -> List[Dict[str, str]]:
    """Related models this model cannot be created without (e.g. DeviceType → Manufacturer)."""
    parents = []
    for field in model_class._meta.concrete_fields:
        if not field.is_relation or field.related_model is None:
            continue
        if field.name in SKIP_FIELDS:
            continue
        is_required = (
            not field.has_default() and not getattr(field, "null", False) and not getattr(field, "blank", False)
        )
        if is_required:
            related = field.related_model
            parents.append(
                {
                    "field": field.name,
                    "model": f"{related._meta.app_label}.{related._meta.model_name}",
                    "lookup_field": natural_lookup_field(related),
                }
            )
    return parents


def introspect_model(content_type) -> Dict[str, Any]:
    """Full mapping metadata for one Nautobot model.

    Returns::

        {
          "label": "dcim.device",
          "verbose_name": "device",
          "fields": [
            {"name": "name", "field_type": "CharField", "required": True,
             "is_fk": False, "related_model": None, "lookup_field": None,
             "is_custom_field": False, "choices": None},
            {"name": "status", "field_type": "ForeignKey", "required": True,
             "is_fk": True, "related_model": "extras.status",
             "lookup_field": "name", "required_parents": [...]},
            ...
          ],
        }
    """
    from nautobot.extras.models import CustomField  # pylint: disable=import-outside-toplevel

    model_class = content_type.model_class()
    if model_class is None:
        return {"label": str(content_type), "fields": []}

    fields: List[Dict[str, Any]] = []

    for field in model_class._meta.concrete_fields:
        if field.name in SKIP_FIELDS or any(field.name.startswith(p) for p in SKIP_PREFIXES):
            continue
        if getattr(field, "primary_key", False):
            continue

        required = not field.has_default() and not getattr(field, "null", False) and not getattr(field, "blank", False)
        entry: Dict[str, Any] = {
            "name": field.name,
            "field_type": type(field).__name__,
            "required": required,
            "is_fk": False,
            "related_model": None,
            "lookup_field": None,
            "required_parents": [],
            "is_custom_field": False,
            "choices": None,
        }

        if field.is_relation and field.related_model is not None:
            related = field.related_model
            entry["is_fk"] = True
            entry["related_model"] = f"{related._meta.app_label}.{related._meta.model_name}"
            entry["lookup_field"] = natural_lookup_field(related)
            entry["required_parents"] = _required_parent_fks(related)
        elif getattr(field, "choices", None):
            # flatchoices flattens grouped choices to (value, label); coerce to
            # str — some fields (e.g. TimeZoneField) use non-serializable values.
            flat = list(getattr(field, "flatchoices", None) or field.choices)
            entry["choices"] = [str(choice[0]) for choice in flat]

        fields.append(entry)

    try:
        for custom_field in CustomField.objects.get_for_model(model_class):
            fields.append(
                {
                    "name": f"{CUSTOM_FIELD_PREFIX}{custom_field.key}",
                    "field_type": f"CustomField ({custom_field.type})",
                    "required": custom_field.required,
                    "is_fk": False,
                    "related_model": None,
                    "lookup_field": None,
                    "required_parents": [],
                    "is_custom_field": True,
                    "choices": None,
                }
            )
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Required first, then alphabetical.
    fields.sort(key=lambda f: (not f["required"], f["name"]))

    natural = natural_lookup_field(model_class)
    return {
        "label": f"{content_type.app_label}.{content_type.model}",
        "verbose_name": str(model_class._meta.verbose_name),
        "natural_key_field": natural,
        "fields": fields,
    }


def get_django_field(model_class, field_name: str) -> Optional[Any]:
    """Return the Django field object for a name, or None (custom fields return None)."""
    if field_name.startswith(CUSTOM_FIELD_PREFIX):
        return None
    try:
        return model_class._meta.get_field(field_name)
    except FieldDoesNotExist:
        return None


def validate_field(model_class, field_name: str) -> bool:
    """True when the field name is writable on the model (or a custom field)."""
    if field_name.startswith(CUSTOM_FIELD_PREFIX):
        return True
    return get_django_field(model_class, field_name) is not None
