"""Utility functions for Generic SSoT Integration."""

import json
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

try:
    import jmespath
except ImportError:
    jmespath = None  # type: ignore

import requests
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, SecretsGroupAssociation

logger = logging.getLogger("nautobot.ssot")


def _m2m_content_types(instance, field_name):
    """Query M2M ContentType relations via the through table.

    Django cannot resolve reverse-relation lookups (e.g. ``ssot_mappings``,
    ``ssot_sync_configs``) on ``ContentType`` when the plugin app hasn't fully
    registered them.  Querying the through table directly side-steps this.

    Returns a queryset of ``ContentType`` objects.
    """
    m2m_field = getattr(type(instance), field_name)
    through = m2m_field.through
    # Auto-generated M2M through tables use <lowercasemodelname>_id columns.
    source_col = f"{type(instance).__name__.lower()}_id"
    ct_ids = through.objects.filter(**{source_col: instance.pk}).values_list("contenttype_id", flat=True)
    return ContentType.objects.filter(id__in=ct_ids)


def get_api_client_config(integration: ExternalIntegration) -> Dict[str, Any]:
    """Get API client configuration from ExternalIntegration.

    Supports:
    - Token auth: SecretsGroup with TYPE_HTTP or TYPE_REST + TYPE_TOKEN → X-Auth-Token header
        (e.g. LibreNMS, many REST APIs)
    - Basic auth: SecretsGroup with TYPE_REST + TYPE_USERNAME + TYPE_PASSWORD → HTTP Basic
    """
    config = {
        "url": integration.remote_url.rstrip("/"),
        "verify_ssl": integration.verify_ssl,
        "timeout": integration.timeout or 30,
        "auth": None,
        "auth_headers": {},
    }

    if not integration.secrets_group:
        return config

    # Prefer token auth (e.g. LibreNMS X-Auth-Token) if present
    for access_type in (
        SecretsGroupAccessTypeChoices.TYPE_HTTP,
        SecretsGroupAccessTypeChoices.TYPE_REST,
    ):
        try:
            token = integration.secrets_group.get_secret_value(
                access_type=access_type,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
            )
            if token:
                config["auth_headers"]["X-Auth-Token"] = token
                return config
        except SecretsGroupAssociation.DoesNotExist:
            continue

    # Fall back to HTTP Basic (username + password)
    try:
        username = integration.secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        password = integration.secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        config["auth"] = (username, password)
    except SecretsGroupAssociation.DoesNotExist:
        pass

    return config


def _extract_records_from_response(data, data_path):
    """Extract a list of records from an API response dict.

    Tries in order:
    1. JMESPath/dict.get using the configured data_path
    2. Auto-detect: first value that is a non-empty list of dicts
    3. Fallback: wrap the whole response in a list

    Returns a list (never None).
    """
    # 1. Try configured data_path
    if data_path and isinstance(data, dict):
        result = None
        try:
            import jmespath as _jp  # noqa: PLC0415

            result = _jp.search(data_path, data)
        except Exception:
            result = data.get(data_path)
        if result and isinstance(result, list):
            return result

    # 2. Auto-detect: scan for the first value that is a non-empty list-of-dicts
    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val

    # 3. Fallback: wrap as-is
    if isinstance(data, list):
        return data
    return [data]


def fetch_data_from_endpoint_definition(
    integration: ExternalIntegration,
    endpoint_def: Dict[str, Any],
    sample_size: int = 100,
    logger=None,
) -> tuple[List[Dict], Optional[int]]:
    """
    Fetch data from an API using integration and an endpoint definition dict.

    endpoint_def should have: name (key for master dict), api_path, and optionally
    data_path, pagination_type, pagination_config, request_headers, query_parameters,
    http_method_read ("GET"|"POST"), request_body_template.
    """
    config = get_api_client_config(integration)
    base_url = config["url"]
    api_path = endpoint_def.get("api_path") or ""
    url = f"{base_url}{api_path}"

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    _auth_headers = config.get("auth_headers") or {}
    if isinstance(_auth_headers, dict):
        headers.update(_auth_headers)
    _req_headers = endpoint_def.get("request_headers") or {}
    if isinstance(_req_headers, dict):
        headers.update(_req_headers)

    _qp = endpoint_def.get("query_parameters") or {}
    params = dict(_qp) if isinstance(_qp, dict) else {}
    data_path = endpoint_def.get("data_path")
    http_method = (endpoint_def.get("http_method_read") or "GET").upper()
    pagination_type = endpoint_def.get("pagination_type") or "none"
    _pc = endpoint_def.get("pagination_config") or {}
    pagination_config = _pc if isinstance(_pc, dict) else {}
    request_body = endpoint_def.get("request_body_template")
    body = json.loads(request_body) if request_body else {}

    all_records = []
    total_count = None

    if pagination_type == "offset":
        limit_param = pagination_config.get("limit_param", "limit")
        offset_param = pagination_config.get("offset_param", "offset")
        page_size = pagination_config.get("page_size", 100)
        offset = 0
        while True:
            params[limit_param] = min(page_size, sample_size - len(all_records)) if sample_size else page_size
            params[offset_param] = offset
            if logger:
                logger.debug(f"Fetching from {url} with params {params}")
            if http_method == "POST":
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json=body,
                    auth=config.get("auth"),
                    verify=config["verify_ssl"],
                    timeout=config["timeout"],
                )
            else:
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    auth=config.get("auth"),
                    verify=config["verify_ssl"],
                    timeout=config["timeout"],
                )
            response.raise_for_status()
            data = response.json()
            records = _extract_records_from_response(data, data_path)
            if not records:
                break
            all_records.extend(records)
            offset += len(records)
            if sample_size and len(all_records) >= sample_size:
                all_records = all_records[:sample_size]
                break
            if len(records) < page_size:
                break
    else:
        if logger:
            logger.debug(f"Fetching from {url} with params {params}")
        if http_method == "POST":
            response = requests.post(
                url,
                headers=headers,
                params=params,
                json=body,
                auth=config.get("auth"),
                verify=config["verify_ssl"],
                timeout=config["timeout"],
            )
        else:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                auth=config.get("auth"),
                verify=config["verify_ssl"],
                timeout=config["timeout"],
            )
        response.raise_for_status()
        data = response.json()
        records = _extract_records_from_response(data, data_path)
        all_records = records[:sample_size] if sample_size else records

    return all_records, total_count


def fetch_data_from_endpoint(
    endpoint,
    sample_size: int = 10,
    logger=None,
) -> tuple[List[Dict], Optional[int]]:
    """Fetch data from an API endpoint with pagination support."""
    config = get_api_client_config(endpoint.integration)
    base_url = config["url"]
    api_path = endpoint.api_path or ""

    # Build full URL
    url = f"{base_url}{api_path}"

    # Prepare headers (include token auth if set on integration)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    _auth_h = config.get("auth_headers") or {}
    if isinstance(_auth_h, dict):
        headers.update(_auth_h)
    _req_h = endpoint.request_headers or {}
    if isinstance(_req_h, dict):
        headers.update(_req_h)

    # Prepare query parameters
    _qp = endpoint.query_parameters if isinstance(endpoint.query_parameters, dict) else {}
    params = _qp.copy() if _qp else {}

    all_records = []
    total_count = None

    # Handle pagination
    if endpoint.pagination_type == "offset":
        pagination_config = endpoint.pagination_config or {}
        limit_param = pagination_config.get("limit_param", "limit")
        offset_param = pagination_config.get("offset_param", "offset")
        page_size = pagination_config.get("page_size", 100)

        offset = 0
        while len(all_records) < sample_size:
            params[limit_param] = min(page_size, sample_size - len(all_records))
            params[offset_param] = offset

            if logger:
                logger.debug(f"Fetching from {url} with params {params}")

            if endpoint.http_method_read == "POST":
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json=json.loads(endpoint.request_body_template) if endpoint.request_body_template else {},
                    auth=config.get("auth"),
                    verify=config["verify_ssl"],
                    timeout=config["timeout"],
                )
            else:
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    auth=config.get("auth"),
                    verify=config["verify_ssl"],
                    timeout=config["timeout"],
                )

            response.raise_for_status()
            data = response.json()

            # Extract data using data_path if specified
            if endpoint.data_path and jmespath:
                records = jmespath.search(endpoint.data_path, data)
            elif endpoint.data_path:
                records = _manual_data_path(data, endpoint.data_path)
            else:
                # Assume data is a list or the response itself
                records = data if isinstance(data, list) else [data]

            if not records:
                break

            all_records.extend(records[: sample_size - len(all_records)])
            offset += len(records)

            if len(records) < page_size:
                break

    else:
        # No pagination or simple GET
        if logger:
            logger.debug(f"Fetching from {url} with params {params}")

        if endpoint.http_method_read == "POST":
            response = requests.post(
                url,
                headers=headers,
                params=params,
                json=json.loads(endpoint.request_body_template) if endpoint.request_body_template else {},
                auth=config.get("auth"),
                verify=config["verify_ssl"],
                timeout=config["timeout"],
            )
        else:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                auth=config.get("auth"),
                verify=config["verify_ssl"],
                timeout=config["timeout"],
            )

        response.raise_for_status()
        data = response.json()

        # Extract data using data_path if specified
        if endpoint.data_path and jmespath:
            records = jmespath.search(endpoint.data_path, data)
        elif endpoint.data_path:
            records = _manual_data_path(data, endpoint.data_path)
        else:
            records = data if isinstance(data, list) else [data]

        all_records = records[:sample_size] if isinstance(records, list) else [records]

    return all_records, total_count


def _manual_data_path(data: Any, data_path: str) -> Any:
    """Fallback dotted-key traversal when jmespath is not installed."""
    current = data
    for part in data_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and len(current) == 1 and isinstance(current[0], dict):
            current = current[0].get(part)
        else:
            return [data] if isinstance(data, dict) else data
    if current is None:
        return []
    return current if isinstance(current, list) else [current]


def extract_field_value(record: Dict, jmespath_expression: str) -> Any:
    """Extract a field value from a record using JMESPath (or manual fallback)."""
    if jmespath is not None:
        return jmespath.search(jmespath_expression, record)
    # Manual fallback for simple dotted paths.
    current = record
    for part in jmespath_expression.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def apply_transformation(
    value: Any,
    transformation_type: str,
    transformation_config: Dict,
    value_map=None,
    logger=None,
) -> Any:
    """Apply transformation to a field value."""
    if transformation_type == "none":
        return value

    elif transformation_type == "static":
        return transformation_config.get("value")

    elif transformation_type == "value_map":
        # Use value_map if provided, otherwise use inline mapping
        mappings = value_map.mappings if value_map else transformation_config.get("inline_map", {})
        default = value_map.default_value if value_map else transformation_config.get("default_value")
        case_sensitive = value_map.case_sensitive if value_map else transformation_config.get("case_sensitive", False)

        if not case_sensitive and isinstance(value, str):
            # Case-insensitive lookup
            for k, v in mappings.items():
                if isinstance(k, str) and k.lower() == value.lower():
                    return v
        else:
            # Direct lookup (exact type match).
            if value in mappings:
                return mappings[value]
            # Fallback: try string coercion since JSON keys are always strings
            # but API values may be integers/floats (e.g. 0 → "0").
            str_value = str(value)
            if str_value in mappings:
                return mappings[str_value]

        return default

    elif transformation_type == "type_cast":
        target_type = transformation_config.get("target_type", "string")
        if target_type == "integer":
            return int(value) if value is not None else None
        elif target_type == "float":
            return float(value) if value is not None else None
        elif target_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        elif target_type == "string":
            return str(value) if value is not None else None
        # datetime conversion would go here but requires dateutil or similar

    elif transformation_type == "jinja":
        template_str = transformation_config.get("template", "")
        if not template_str:
            return value
        try:
            from jinja2 import Template  # noqa: PLC0415

            rendered = Template(template_str).render(value=value)
            return rendered
        except Exception as exc:
            if logger:
                logger.warning("Jinja transform failed for template %r: %s", template_str, exc)
            return value

    return value


# ---------------------------------------------------------------------------
# Composable transform pipeline (used by endpoint normalization and per-field
# mappings).  Each transform is a small pure-ish function that takes (value,
# config_dict) and returns a new value.
# ---------------------------------------------------------------------------


def _cast_value(value: Any, target_type: str) -> Any:
    """Coerce a value to a target type, returning None on failure."""
    if value is None:
        return None
    try:
        if target_type == "integer":
            return int(value)
        if target_type == "float":
            return float(value)
        if target_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        if target_type == "string":
            return str(value)
    except (ValueError, TypeError):
        return None
    return value


def _xfm_regex_replace(value, cfg):
    if value is None:
        return None
    pattern = cfg.get("pattern", "")
    replacement = cfg.get("replacement", "")
    return re.sub(pattern, replacement, str(value))


def _xfm_value_map(value, cfg):
    mapping = cfg.get("map", {})
    default = cfg.get("default")
    if value in mapping:
        return mapping[value]
    str_value = str(value) if value is not None else ""
    if str_value in mapping:
        return mapping[str_value]
    return default if default is not None else value


def _xfm_jinja(value, cfg, record=None):
    template_str = cfg.get("template", "")
    if not template_str:
        return value
    try:
        from jinja2 import Template  # noqa: PLC0415

        return Template(template_str).render(value=value, record=record or {})
    except Exception:
        return value


TRANSFORM_REGISTRY = {
    "regex_replace": lambda v, cfg, rec=None: _xfm_regex_replace(v, cfg),
    "lowercase": lambda v, cfg, rec=None: str(v).lower() if v is not None else None,
    "uppercase": lambda v, cfg, rec=None: str(v).upper() if v is not None else None,
    "title_case": lambda v, cfg, rec=None: str(v).title() if v is not None else None,
    "strip": lambda v, cfg, rec=None: str(v).strip() if v is not None else None,
    "equals": lambda v, cfg, rec=None: v == cfg.get("value"),
    "not_equals": lambda v, cfg, rec=None: v != cfg.get("value"),
    "value_map": lambda v, cfg, rec=None: _xfm_value_map(v, cfg),
    "jinja": _xfm_jinja,
    "type_cast": lambda v, cfg, rec=None: _cast_value(v, cfg.get("target_type", "string")),
    "default": lambda v, cfg, rec=None: cfg.get("value") if (v is None or v == "") else v,
    "prefix": lambda v, cfg, rec=None: f"{cfg.get('value', '')}{v}" if v is not None else None,
    "suffix": lambda v, cfg, rec=None: f"{v}{cfg.get('value', '')}" if v is not None else None,
}


def apply_transforms(value: Any, transforms: Optional[List[Dict]], record: Optional[Dict] = None, logger=None) -> Any:
    """Run a value through an ordered list of composable transforms.

    Each transform entry must be ``{"type": str, "config": dict}``.  Unknown
    transform types are skipped with a warning.  Per-transform exceptions are
    caught so a bad config doesn't crash the whole sync.
    """
    if not transforms:
        return value
    current = value
    for xfm in transforms:
        if not isinstance(xfm, dict):
            continue
        xfm_type = xfm.get("type")
        xfm_cfg = xfm.get("config", {}) or {}
        if xfm_type not in TRANSFORM_REGISTRY:
            if logger:
                logger.warning("Unknown transform type %r — skipping", xfm_type)
            continue
        try:
            current = TRANSFORM_REGISTRY[xfm_type](current, xfm_cfg, record)
        except Exception as exc:
            if logger:
                logger.warning("Transform %r failed on value %r: %s", xfm_type, current, exc)
            # Continue with the value as-is so downstream transforms can run.
    return current


def normalize_record(raw_record: Dict, normalize_config: Optional[List[Dict]], logger=None) -> Dict:
    """Apply endpoint normalization to a raw API record.

    Returns a canonical record dict containing each configured canonical field
    plus a ``_raw`` key with the original record for escape-hatch access.

    Each entry in ``normalize_config`` is::

        {
            "name": "vendor",           # canonical field name
            "source": "icon",           # JMESPath into raw record
            "fallback": "vendor",       # optional: try if source is empty
            "transforms": [             # optional: ordered transform pipeline
                {"type": "regex_replace", "config": {"pattern": "\\.svg$", "replacement": ""}},
                {"type": "title_case", "config": {}}
            ]
        }
    """
    canonical: Dict[str, Any] = {"_raw": raw_record}
    if not normalize_config or not isinstance(raw_record, dict):
        return canonical

    for field_def in normalize_config:
        if not isinstance(field_def, dict):
            continue
        name = field_def.get("name", "").strip()
        if not name:
            continue
        source = field_def.get("source", "").strip()
        fallback = field_def.get("fallback", "").strip()
        transforms = field_def.get("transforms", [])

        value = extract_field_value(raw_record, source) if source else None
        if (value is None or value == "") and fallback:
            value = extract_field_value(raw_record, fallback)

        canonical[name] = apply_transforms(value, transforms, record=raw_record, logger=logger)

    return canonical


def resolve_source_value(record: Dict, source_field: str) -> Any:
    """Resolve a source field reference against a canonical (or raw) record.

    Resolution order:
      1. ``_raw.<path>`` — JMESPath against the raw record (escape hatch)
      2. Direct canonical field name (e.g., ``vendor``)
      3. JMESPath against the raw record (backwards compatibility for legacy
         mappings that reference raw fields directly)
    """
    if not source_field:
        return None
    if source_field.startswith("_raw."):
        raw = record.get("_raw") if isinstance(record, dict) else None
        return extract_field_value(raw or {}, source_field[len("_raw.") :])
    if isinstance(record, dict) and source_field in record and source_field != "_raw":
        return record[source_field]
    # Backwards-compat: treat as JMESPath against raw record if present, else the record itself.
    raw = record.get("_raw") if isinstance(record, dict) else None
    return extract_field_value(raw if raw is not None else record, source_field)


def get_required_unmapped_fk_defaults(model_class, mapped_nautobot_fields) -> Dict[str, str]:
    """Detect required FK fields on a Django model that aren't in the user's field mappings.

    Returns a dict of ``{diffsync_field_name: default_value}`` for fields that
    should be auto-added with sensible defaults.  For example, if IPAddress has
    a required ``status`` FK and the user didn't map ``status__name``, this will
    return ``{"status__name": "Active"}``.

    Only fields with a known safe default are returned.  Other unmapped required
    FK fields are logged as debug messages.
    """
    KNOWN_DEFAULTS = {
        "status": ("status__name", "Active"),
    }

    defaults = {}
    for field in model_class._meta.concrete_fields:
        if not field.is_relation or not getattr(field, "related_model", None):
            continue
        if getattr(field, "null", False):
            continue
        # Check if the user already mapped this FK (either bare or with __ traversal)
        already_mapped = any(f == field.name or f.startswith(f"{field.name}__") for f in mapped_nautobot_fields)
        if already_mapped:
            continue

        if field.name in KNOWN_DEFAULTS:
            ds_field, default_val = KNOWN_DEFAULTS[field.name]
            defaults[ds_field] = default_val
            logger.info(
                "Auto-adding default for required field '%s' on %s: %s = '%s'",
                field.name,
                model_class.__name__,
                ds_field,
                default_val,
            )
        else:
            logger.debug(
                "Required FK field '%s' on %s is not mapped; no known default available.",
                field.name,
                model_class.__name__,
            )

    return defaults


def validate_nautobot_field(model_class, nautobot_field: str) -> bool:
    """Check that *nautobot_field* resolves to a real Django field.

    Returns ``True`` when the field is valid.  For invalid fields it returns
    ``False`` and logs a warning that suggests the ``__`` FK traversal syntax
    when the field exists on a related model.
    """
    # Custom fields are handled via annotation — nothing to validate.
    if nautobot_field.startswith("_cf_"):
        return True

    # Strip the leading underscore used for Pydantic v2 compatibility.
    field_to_check = nautobot_field[1:] if nautobot_field.startswith("_") else nautobot_field

    # FK traversal fields: validate the first segment is a relation.
    if "__" in field_to_check:
        fk_name = field_to_check.split("__", maxsplit=1)[0]
        try:
            model_class._meta.get_field(fk_name)
        except FieldDoesNotExist:
            logger.warning(
                "Field mapping '%s' is invalid: %s has no field '%s'. Skipping this mapping.",
                nautobot_field,
                model_class.__name__,
                fk_name,
            )
            return False
        return True

    # Direct field on the model.
    try:
        model_class._meta.get_field(field_to_check)
    except FieldDoesNotExist:
        # Search FK relations for the field and suggest the full path.
        suggestions = []
        for field_obj in model_class._meta.get_fields():
            if field_obj.is_relation and field_obj.related_model:
                try:
                    field_obj.related_model._meta.get_field(field_to_check)
                    suggestions.append(f"{field_obj.name}__{field_to_check}")
                except FieldDoesNotExist:
                    continue
        hint = ""
        if suggestions:
            hint = f" Did you mean: {', '.join(suggestions)}?"
        logger.warning(
            "Field mapping '%s' is invalid: %s has no field '%s'.%s Skipping this mapping.",
            nautobot_field,
            model_class.__name__,
            field_to_check,
            hint,
        )
        return False
    return True


def introspect_nautobot_model(content_type) -> List[Dict[str, Any]]:
    """Return one row per mappable attribute on a Nautobot model.

    The returned list drives the model-centric field mapping builder.  Each
    item is a dict describing a single field that the user can map a JMESPath
    expression to.

    **Non-relation fields** (``CharField``, ``IntegerField``, …) produce one
    row with the bare field name (e.g. ``name``, ``serial``).

    **FK / relation fields** produce a single ``fk__name`` row (e.g.
    ``device_type__model``, ``status__name``, ``role__name``) because the
    DiffSync contrib framework resolves FK lookups via ``__`` traversal and
    ``name`` is the natural lookup key.  The related model is noted so the
    user understands the relationship.

    Internal, auto-managed, and framework-specific fields are skipped.

    Returns a list of dicts with keys:

    - ``name``:  The field name to use in ``nautobot_field`` (e.g. ``"name"``
      or ``"device_type__model"``)
    - ``field_type``:  Human-readable type string
    - ``is_required``:  ``True`` when the model needs a value
    - ``is_relation``:  ``True`` for FK rows
    - ``related_model_name``:  ``"app_label.ModelName"`` for FK rows, else ``None``
    - ``is_custom_field``:  ``True`` for Nautobot custom fields
    - ``custom_field_key``:  CF key string (only when ``is_custom_field``)
    """
    from nautobot.extras.models import CustomField  # pylint: disable=import-outside-toplevel

    model_class = content_type.model_class()
    if model_class is None:
        return []

    # Fields to never show in the builder.
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
        # Nautobot internal / ordering helpers
        "_name",
        "natural_slug",
    }
    # Also skip any field whose name starts with these prefixes.
    SKIP_PREFIXES = (
        "local_config_context",
        "_custom_field",
    )

    result = []

    for field in model_class._meta.concrete_fields:
        if field.name in SKIP_FIELDS:
            continue
        if any(field.name.startswith(p) for p in SKIP_PREFIXES):
            continue
        if getattr(field, "primary_key", False):
            continue

        is_relation = field.is_relation
        related_model = getattr(field, "related_model", None)

        has_default = field.has_default()
        null = getattr(field, "null", False)
        blank = getattr(field, "blank", False)
        is_required = not has_default and not null and not blank

        if is_relation and related_model is not None:
            # Determine the best natural lookup field for the related model.
            # Try common identifier field names in priority order.
            related_name_field = "name"
            for candidate in ("name", "address", "version", "model", "slug"):
                try:
                    related_model._meta.get_field(candidate)
                    related_name_field = candidate
                    break
                except Exception:
                    pass

            related_label = f"{related_model._meta.app_label}.{related_model.__name__}"

            result.append(
                {
                    "name": f"{field.name}__{related_name_field}",
                    "field_type": type(field).__name__,
                    "is_required": is_required,
                    "is_relation": True,
                    "related_model_name": related_label,
                    "is_custom_field": False,
                    "custom_field_key": None,
                }
            )
        else:
            result.append(
                {
                    "name": field.name,
                    "field_type": type(field).__name__,
                    "is_required": is_required,
                    "is_relation": False,
                    "related_model_name": None,
                    "is_custom_field": False,
                    "custom_field_key": None,
                }
            )

    # ── Custom fields ────────────────────────────────────────────────────
    try:
        custom_fields = CustomField.objects.get_for_model(model_class)
        for cf in custom_fields:
            result.append(
                {
                    "name": f"_cf_{cf.key}",
                    "field_type": f"CustomField ({cf.type})",
                    "is_required": cf.required,
                    "is_relation": False,
                    "related_model_name": None,
                    "is_custom_field": True,
                    "custom_field_key": cf.key,
                }
            )
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Dependency-tree introspection (model-first builder)
# ---------------------------------------------------------------------------


def _natural_lookup_field(model_class) -> str:
    """Return the best simple lookup field for *model_class*.

    Uses Nautobot's ``natural_key_field_lookups`` when available, falling back
    to the first non-FK concrete field.  This avoids hardcoding field names.
    """
    if hasattr(model_class, "natural_key_field_lookups"):
        for lookup in model_class.natural_key_field_lookups:
            # Pick the first lookup that doesn't traverse a FK (no ``__``).
            if "__" not in lookup:
                return lookup
    # Fallback: first non-PK, non-FK concrete field.
    for field in model_class._meta.concrete_fields:
        if not field.primary_key and not field.is_relation:
            return field.name
    return "pk"


def build_dependency_tree(
    content_type,
    max_depth: int = 3,
    _visited: Optional[Set[str]] = None,
    _path_prefix: str = "",
    _depth: int = 0,
) -> List[Dict[str, Any]]:
    """Build a recursive dependency tree for a Nautobot model's mappable fields.

    Each node is a dict with keys:

    - ``name``:  Field name on the immediate model (e.g. ``"model"``)
    - ``path``:  Full ``__``-joined path from the root model, suitable for use
      as ``SSOTFieldMapping.nautobot_field`` (e.g.
      ``"device_type__manufacturer__name"``)
    - ``field_type``:  Human-readable type string
    - ``is_required``:  Whether the model requires a non-null value
    - ``is_relation``:  ``True`` for FK / relation fields
    - ``related_model_name``:  ``"app_label.ModelName"`` for FK nodes
    - ``depth``:  Nesting level (0 = root model fields)
    - ``children``:  ``None`` for leaf nodes, ``list`` for FK branch nodes
    - ``is_custom_field`` / ``custom_field_key``:  Custom field metadata

    FK branches are expanded recursively up to *max_depth*.  Cycle detection
    prevents infinite recursion on self-referential relationships (e.g.
    ``Location.parent``).
    """
    from nautobot.extras.models import CustomField  # pylint: disable=import-outside-toplevel

    model_class = content_type.model_class()
    if model_class is None:
        return []

    if _visited is None:
        _visited = set()

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
    SKIP_PREFIXES = (
        "local_config_context",
        "_custom_field",
    )

    result: List[Dict[str, Any]] = []

    for field in model_class._meta.concrete_fields:
        if field.name in SKIP_FIELDS:
            continue
        if any(field.name.startswith(p) for p in SKIP_PREFIXES):
            continue
        if getattr(field, "primary_key", False):
            continue

        is_relation = field.is_relation
        related_model = getattr(field, "related_model", None)

        has_default = field.has_default()
        null = getattr(field, "null", False)
        blank = getattr(field, "blank", False)
        is_required = not has_default and not null and not blank

        if is_relation and related_model is not None:
            related_label = f"{related_model._meta.app_label}.{related_model.__name__}"
            related_ct = ContentType.objects.get_for_model(related_model)

            # Skip infrastructure models.
            if related_ct.app_label in _SKIP_APP_LABELS or related_ct.model in _SKIP_MODELS:
                continue

            # Only recurse into required FKs to keep the tree manageable.
            # Optional FKs are collapsed to a simple leaf using the natural lookup.
            # Also collapse on cycle or max depth.
            if related_label in _visited or _depth >= max_depth or not is_required:
                lookup = _natural_lookup_field(related_model)
                result.append(
                    {
                        "name": field.name,
                        "path": f"{_path_prefix}{field.name}__{lookup}",
                        "field_type": type(field).__name__,
                        "is_required": is_required,
                        "is_relation": True,
                        "related_model_name": related_label,
                        "depth": _depth,
                        "children": None,
                        "is_custom_field": False,
                        "custom_field_key": None,
                    }
                )
                continue

            # Recurse into the related model.
            _visited.add(related_label)
            children = build_dependency_tree(
                related_ct,
                max_depth=max_depth,
                _visited=_visited,
                _path_prefix=f"{_path_prefix}{field.name}__",
                _depth=_depth + 1,
            )
            _visited.discard(related_label)

            result.append(
                {
                    "name": field.name,
                    "path": f"{_path_prefix}{field.name}",
                    "field_type": type(field).__name__,
                    "is_required": is_required,
                    "is_relation": True,
                    "related_model_name": related_label,
                    "depth": _depth,
                    "children": children,
                    "is_custom_field": False,
                    "custom_field_key": None,
                }
            )
        else:
            result.append(
                {
                    "name": field.name,
                    "path": f"{_path_prefix}{field.name}",
                    "field_type": type(field).__name__,
                    "is_required": is_required,
                    "is_relation": False,
                    "related_model_name": None,
                    "depth": _depth,
                    "children": None,
                    "is_custom_field": False,
                    "custom_field_key": None,
                }
            )

    # ── Custom fields (only on root-level models) ───────────────────────
    if _depth == 0:
        try:
            custom_fields = CustomField.objects.get_for_model(model_class)
            for cf in custom_fields:
                result.append(
                    {
                        "name": f"_cf_{cf.key}",
                        "path": f"{_path_prefix}_cf_{cf.key}",
                        "field_type": f"CustomField ({cf.type})",
                        "is_required": cf.required,
                        "is_relation": False,
                        "related_model_name": None,
                        "depth": _depth,
                        "children": None,
                        "is_custom_field": True,
                        "custom_field_key": cf.key,
                    }
                )
        except Exception:
            pass

    return result


def flatten_tree_to_leaves(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return all leaf nodes from a dependency tree in depth-first order.

    A leaf is any node whose ``children`` is ``None``.  Branch nodes (FK
    fields with ``children`` as a list) are skipped — only their descendant
    leaves are included.
    """
    leaves: List[Dict[str, Any]] = []
    for node in nodes:
        if node.get("children") is not None and isinstance(node["children"], list):
            leaves.extend(flatten_tree_to_leaves(node["children"]))
        else:
            leaves.append(node)
    return leaves


def discover_fields(sample_records: List[Dict]) -> Dict[str, str]:
    """Discover field names and types from sample records."""
    discovered = {}
    if not sample_records:
        return discovered

    # Analyze first record to infer structure
    first_record = sample_records[0]
    if isinstance(first_record, dict):
        for key, value in first_record.items():
            if isinstance(value, dict):
                # Nested object - suggest JMESPath expression
                discovered[key] = "object"
            elif isinstance(value, list):
                discovered[key] = "array"
            elif isinstance(value, bool):
                discovered[key] = "boolean"
            elif isinstance(value, int):
                discovered[key] = "integer"
            elif isinstance(value, float):
                discovered[key] = "float"
            else:
                discovered[key] = "string"

    return discovered


def validate_endpoint_ordering(sync_config, logger=None):
    """Check that FK dependencies are satisfiable given endpoint weights.

    Inspects ``__`` FK traversal fields in mappings to determine which content
    types depend on which.  If a dependency is mapped from a *higher*-weight
    endpoint than the dependent, a warning is logged because the referenced
    objects may not yet exist when the dependent is processed.

    Returns a list of warning strings (empty list == all good).
    """
    from nautobot_ssot.integrations.generic_ssot.models import (
        SSOTFieldMapping,  # pylint: disable=import-outside-toplevel
    )

    # Build a map: content_type_id → minimum endpoint weight that provides it.
    ct_min_weight: Dict[int, int] = {}
    # Build a map: content_type_id → list of FK content_type_ids it depends on.
    ct_dependencies: Dict[int, List[int]] = {}

    ordered_endpoints = sync_config.get_ordered_endpoints()
    # endpoint_id → weight
    endpoint_weights = {}
    for sce in sync_config.sync_config_endpoints.select_related("endpoint").all():
        endpoint_weights[sce.endpoint_id] = sce.weight

    for endpoint in ordered_endpoints:
        weight = endpoint_weights.get(endpoint.id, endpoint.weight)
        mappings = SSOTFieldMapping.objects.filter(
            sync_config=sync_config,
            endpoint=endpoint,
            enabled=True,
        ).select_related("nautobot_content_type")

        for mapping in mappings:
            ct_id = mapping.nautobot_content_type_id
            if ct_id not in ct_min_weight or weight < ct_min_weight[ct_id]:
                ct_min_weight[ct_id] = weight

            # Check for FK traversal dependencies
            if "__" in mapping.nautobot_field:
                fk_name = mapping.nautobot_field.split("__", maxsplit=1)[0]
                model_class = mapping.nautobot_content_type.model_class()
                if model_class:
                    try:
                        fk_field = model_class._meta.get_field(fk_name)
                        if fk_field.is_relation and fk_field.related_model:
                            from django.contrib.contenttypes.models import (
                                ContentType as CT,  # pylint: disable=import-outside-toplevel
                            )

                            related_ct = CT.objects.get_for_model(fk_field.related_model)
                            if ct_id not in ct_dependencies:
                                ct_dependencies[ct_id] = []
                            ct_dependencies[ct_id].append(related_ct.id)
                    except Exception:
                        pass

    warnings = []
    for ct_id, dep_ct_ids in ct_dependencies.items():
        ct_weight = ct_min_weight.get(ct_id, 0)
        for dep_ct_id in dep_ct_ids:
            dep_weight = ct_min_weight.get(dep_ct_id)
            if dep_weight is not None and dep_weight > ct_weight:
                try:
                    from django.contrib.contenttypes.models import (
                        ContentType as CT,  # pylint: disable=import-outside-toplevel
                    )

                    ct = CT.objects.get(id=ct_id)
                    dep_ct = CT.objects.get(id=dep_ct_id)
                    msg = (
                        f"{ct.app_label}.{ct.model} (weight {ct_weight}) depends on "
                        f"{dep_ct.app_label}.{dep_ct.model} (weight {dep_weight}), "
                        f"but the dependency has a higher weight and will be processed later. "
                        f"Consider reordering endpoints so the dependency is loaded first."
                    )
                    warnings.append(msg)
                    if logger:
                        logger.warning(msg)
                except Exception:
                    pass

    return warnings


# ---------------------------------------------------------------------------
# Dependency introspection utilities
# ---------------------------------------------------------------------------

# Infrastructure models that should never appear as dependencies.
_SKIP_APP_LABELS = {"auth", "admin", "contenttypes", "sessions", "django_celery_beat"}
_SKIP_MODELS = {"user", "group", "permission", "contenttype", "session"}


def introspect_dependency_tree(
    content_types: List[ContentType],
    max_depth: int = 3,
) -> Dict[str, Any]:
    """Walk FK relations on the given content types and return a dependency graph.

    Returns ``{"nodes": [...], "edges": [...]}`` where each node has::

        {
            "content_type_id": int,
            "app_label": str,
            "model": str,
            "model_name": str,   # human-readable class name
            "is_user_selected": bool,
            "is_required_dependency": bool,
            "required_by": [int, ...],  # ct ids that require this
            "depth": int,
        }

    and each edge has::

        {"from_ct_id": int, "to_ct_id": int, "field_name": str, "is_required": bool}
    """
    user_ct_ids: Set[int] = {ct.id for ct in content_types}
    nodes: Dict[int, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def _add_node(ct: ContentType, is_user_selected: bool, depth: int):
        if ct.id in nodes:
            # Update depth if shallower.
            if depth < nodes[ct.id]["depth"]:
                nodes[ct.id]["depth"] = depth
            return
        model_class = ct.model_class()
        nodes[ct.id] = {
            "content_type_id": ct.id,
            "app_label": ct.app_label,
            "model": ct.model,
            "model_name": model_class.__name__ if model_class else ct.model,
            "is_user_selected": is_user_selected,
            "is_required_dependency": False,
            "required_by": [],
            "depth": depth,
        }

    def _walk(ct: ContentType, depth: int):
        if depth > max_depth:
            return
        model_class = ct.model_class()
        if model_class is None:
            return

        for field in model_class._meta.concrete_fields:
            if not field.is_relation or not getattr(field, "related_model", None):
                continue
            related_model = field.related_model
            related_ct = ContentType.objects.get_for_model(related_model)

            # Skip infrastructure models.
            if related_ct.app_label in _SKIP_APP_LABELS or related_ct.model in _SKIP_MODELS:
                continue

            has_default = field.has_default()
            null = getattr(field, "null", False)
            blank = getattr(field, "blank", False)
            is_required = not has_default and not null and not blank

            edges.append(
                {
                    "from_ct_id": ct.id,
                    "to_ct_id": related_ct.id,
                    "field_name": field.name,
                    "is_required": is_required,
                }
            )

            if related_ct.id not in nodes:
                is_selected = related_ct.id in user_ct_ids
                _add_node(related_ct, is_selected, depth + 1)
                if is_required:
                    nodes[related_ct.id]["is_required_dependency"] = True
                    nodes[related_ct.id]["required_by"].append(ct.id)
                _walk(related_ct, depth + 1)
            else:
                if is_required:
                    nodes[related_ct.id]["is_required_dependency"] = True
                    if ct.id not in nodes[related_ct.id]["required_by"]:
                        nodes[related_ct.id]["required_by"].append(ct.id)

    # Seed with user-selected content types.
    for ct in content_types:
        _add_node(ct, is_user_selected=True, depth=0)
    for ct in content_types:
        _walk(ct, depth=0)

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def get_resolved_model_set(sync_config) -> Dict[int, Dict[str, Any]]:
    """Combine user-selected models with their required dependencies.

    Returns ``{ct_id: {"content_type": ct, "is_user_selected": bool, "is_stub": bool}}``.
    Stub models are required dependencies that the user didn't explicitly select —
    they get minimal identifier-only DiffSync models during sync.
    """
    # Query the through table directly to avoid a Django FieldError that triggers
    # when the reverse M2M lookup (`ssot_sync_configs`) is evaluated as a filter
    # kwarg on ContentType (happens on both .all() and .values_list()).
    through = type(sync_config).synced_content_types.through
    ct_ids = list(through.objects.filter(ssotsyncconfig=sync_config).values_list("contenttype_id", flat=True))
    if not ct_ids:
        return {}
    user_cts = list(ContentType.objects.filter(id__in=ct_ids))

    user_ct_ids = set(ct_ids)
    tree = introspect_dependency_tree(user_cts)

    result = {}
    for node in tree["nodes"]:
        ct_id = node["content_type_id"]
        ct = ContentType.objects.get(id=ct_id)
        is_user = ct_id in user_ct_ids
        result[ct_id] = {
            "content_type": ct,
            "is_user_selected": is_user,
            "is_stub": not is_user and node["is_required_dependency"],
        }

    # Ensure all user-selected CTs are included even if they had no deps.
    for ct in user_cts:
        if ct.id not in result:
            result[ct.id] = {
                "content_type": ct,
                "is_user_selected": True,
                "is_stub": False,
            }

    return result


def fetch_child_endpoint_data(
    endpoint,
    parent_records: List[Dict],
    sample_size: int = 10000,
    log=None,
) -> List[Dict]:
    """Fetch data from a child endpoint by iterating over parent records.

    For each parent record, extracts the parent key via JMESPath, substitutes
    it into the endpoint's ``api_path``, and fetches the child records.
    Each child record is tagged with ``__parent_key`` for linking back.

    Returns a flattened list of all child records.
    """
    if not endpoint.parent_key_field:
        return []

    all_child_records = []
    param_name = endpoint.url_param_name or endpoint.parent_key_field

    for parent_record in parent_records:
        parent_key_value = extract_field_value(parent_record, endpoint.parent_key_field)
        if parent_key_value is None:
            continue

        # Build a temporary endpoint dict with the substituted URL.
        ep_dict = endpoint.to_endpoint_dict()
        ep_dict["api_path"] = ep_dict["api_path"].replace(f"{{{param_name}}}", str(parent_key_value))

        if log:
            log.debug(
                "Fetching child endpoint %s for parent key %s=%s",
                endpoint.name,
                endpoint.parent_key_field,
                parent_key_value,
            )

        try:
            records, _ = fetch_data_from_endpoint_definition(
                endpoint.integration,
                ep_dict,
                sample_size=sample_size,
                logger=log,
            )
            # Tag each child record with the parent key for join purposes.
            for rec in records:
                rec["__parent_key"] = str(parent_key_value)
            all_child_records.extend(records)
        except Exception as exc:
            if log:
                log.warning(
                    "Failed to fetch child endpoint %s for parent key %s: %s",
                    endpoint.name,
                    parent_key_value,
                    exc,
                )

    return all_child_records


def build_joined_dataset(
    sync_config,
    endpoint_data_map: Dict[str, List[Dict]],
    log=None,
) -> Dict[str, List[Dict]]:
    """Merge joined endpoint data into source records based on SSOTEndpointJoin definitions.

    ``endpoint_data_map`` is ``{endpoint_id_str: [records]}``.

    For each join, indexes target records by ``target_key``, then for each
    source record attaches the matching target record(s) under the key
    ``_joined_{target_endpoint_name}``.

    Returns the updated ``endpoint_data_map`` (modified in-place).
    """
    from nautobot_ssot.integrations.generic_ssot.models import (
        SSOTEndpointJoin,  # pylint: disable=import-outside-toplevel
    )

    joins = SSOTEndpointJoin.objects.filter(sync_config=sync_config).select_related(
        "source_endpoint", "target_endpoint"
    )

    for join in joins:
        source_ep_id = str(join.source_endpoint_id)
        target_ep_id = str(join.target_endpoint_id)

        source_records = endpoint_data_map.get(source_ep_id, [])
        target_records = endpoint_data_map.get(target_ep_id, [])

        if not source_records or not target_records:
            if log:
                log.debug(
                    "Skipping join %s → %s: no records on one or both sides.",
                    join.source_endpoint.name,
                    join.target_endpoint.name,
                )
            continue

        # Index target records by join key.  Records may be canonical (with
        # `_raw` wrapper) or raw — resolve_source_value handles both.
        target_index: Dict[str, List[Dict]] = defaultdict(list)
        for rec in target_records:
            key_val = resolve_source_value(rec, join.target_key)
            if key_val is not None:
                target_index[str(key_val)].append(rec)

        joined_key = f"_joined_{join.target_endpoint.name}"
        unmatched = 0

        for rec in source_records:
            source_key_val = resolve_source_value(rec, join.source_key)
            if source_key_val is None:
                unmatched += 1
                if join.join_type == "inner":
                    rec["__skip_inner_join"] = True
                continue

            matches = target_index.get(str(source_key_val), [])
            if matches:
                # One-to-one: attach single dict. One-to-many: attach list.
                rec[joined_key] = matches[0] if len(matches) == 1 else matches
            else:
                unmatched += 1
                if join.join_type == "inner":
                    rec["__skip_inner_join"] = True

        # For inner joins, filter out unmatched source records.
        if join.join_type == "inner":
            endpoint_data_map[source_ep_id] = [r for r in source_records if not r.pop("__skip_inner_join", False)]

        if log:
            log.info(
                "Join %s.%s → %s.%s: %d matched, %d unmatched.",
                join.source_endpoint.name,
                join.source_key,
                join.target_endpoint.name,
                join.target_key,
                len(source_records) - unmatched,
                unmatched,
            )

    return endpoint_data_map
