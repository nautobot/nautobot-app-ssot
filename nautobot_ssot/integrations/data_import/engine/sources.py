"""Source providers: fetch records from JSON APIs and parse CSV text.

Both providers return a plain ``list[dict]`` of raw records; everything
downstream is source-agnostic.
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional

import requests
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, SecretsGroupAssociation

# Safety ceiling on pages fetched per source — backstop against runaway
# pagination loops (misconfigured params, misbehaving APIs).
MAX_PAGES = 1000


def get_api_client_config(integration: ExternalIntegration) -> Dict[str, Any]:
    """Build request config (base URL, auth, TLS, timeout) from an ExternalIntegration.

    Supports token auth (X-Auth-Token header) and HTTP Basic via the
    integration's SecretsGroup.
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


def _walk_data_path(data: Any, data_path: str) -> Any:
    """Follow a dotted path (e.g. ``data.items``) into a nested dict."""
    current = data
    for part in data_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def extract_records(data: Any, data_path: str = "") -> List[Dict]:
    """Extract the list of records from an API response body.

    Tries the configured data_path, then auto-detects the first non-empty
    list-of-dicts value, then falls back to wrapping the response.
    """
    if data_path and isinstance(data, dict):
        result = _walk_data_path(data, data_path)
        if isinstance(result, list):
            return result

    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val

    if isinstance(data, list):
        return data
    return [data]


def fetch_api_records(
    integration: ExternalIntegration,
    source_cfg: Dict[str, Any],
    limit: Optional[int] = None,
    logger=None,
) -> List[Dict]:
    """Fetch records from an API source definition.

    source_cfg keys: api_path, data_path, method, headers, query_params,
    body, pagination {type: none|offset|page, page_size, params: {...}}.
    """
    config = get_api_client_config(integration)
    url = f"{config['url']}{source_cfg.get('api_path') or ''}"

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    headers.update(config.get("auth_headers") or {})
    headers.update(source_cfg.get("headers") or {})

    params = dict(source_cfg.get("query_params") or {})
    data_path = source_cfg.get("data_path") or ""
    method = (source_cfg.get("method") or "GET").upper()
    body_raw = source_cfg.get("body") or ""
    body = json.loads(body_raw) if isinstance(body_raw, str) and body_raw.strip() else (body_raw or {})

    pagination = source_cfg.get("pagination") or {}
    pag_type = pagination.get("type", "none")
    page_size = int(pagination.get("page_size") or 100)
    pag_params = pagination.get("params") or {}

    def _request(req_params):
        kwargs = {
            "headers": headers,
            "params": req_params,
            "auth": config.get("auth"),
            "verify": config["verify_ssl"],
            "timeout": config["timeout"],
        }
        if method == "POST":
            response = requests.post(url, json=body, **kwargs)
        else:
            response = requests.get(url, **kwargs)
        response.raise_for_status()
        return extract_records(response.json(), data_path)

    all_records: List[Dict] = []
    previous_page: Optional[List[Dict]] = None
    pages_fetched = 0

    def _repeated_page(records: List[Dict]) -> bool:
        """True when the API returned the same page again — i.e. it ignores
        pagination parameters (LibreNMS does this). Without this guard the
        loop would accumulate duplicates forever.
        """
        if previous_page is not None and records == previous_page:
            if logger:
                logger.warning(
                    "API returned an identical page twice — it appears to ignore pagination "
                    "parameters. Stopping with %d records. If this source returns everything "
                    "in one response, set its pagination type to 'None'.",
                    len(all_records),
                )
            return True
        return False

    def _hit_page_cap() -> bool:
        if pages_fetched >= MAX_PAGES:
            if logger:
                logger.warning(
                    "Reached the safety cap of %d pages (%d records); stopping. "
                    "Check the source's pagination configuration.",
                    MAX_PAGES,
                    len(all_records),
                )
            return True
        return False

    if pag_type == "offset":
        limit_param = pag_params.get("limit_param", "limit")
        offset_param = pag_params.get("offset_param", "offset")
        offset = 0
        while True:
            params[limit_param] = page_size
            params[offset_param] = offset
            if logger:
                logger.debug("Fetching %s offset=%s", url, offset)
            records = _request(params)
            if not records or _repeated_page(records):
                break
            all_records.extend(records)
            previous_page = records
            pages_fetched += 1
            offset += len(records)
            if limit and len(all_records) >= limit:
                return all_records[:limit]
            if len(records) < page_size or _hit_page_cap():
                break
    elif pag_type == "page":
        page_param = pag_params.get("page_param", "page")
        size_param = pag_params.get("size_param", "per_page")
        page = int(pag_params.get("start_page", 1))
        while True:
            params[page_param] = page
            params[size_param] = page_size
            if logger:
                logger.debug("Fetching %s page=%s", url, page)
            records = _request(params)
            if not records or _repeated_page(records):
                break
            all_records.extend(records)
            previous_page = records
            pages_fetched += 1
            page += 1
            if limit and len(all_records) >= limit:
                return all_records[:limit]
            if len(records) < page_size or _hit_page_cap():
                break
    else:
        if logger:
            logger.debug("Fetching %s (no pagination)", url)
        all_records = _request(params)

    return all_records[:limit] if limit else all_records


def parse_csv(text: str, limit: Optional[int] = None) -> List[Dict]:
    """Parse CSV text into a list of dicts keyed by header row.

    Sniffs the delimiter, strips whitespace from headers, skips fully-empty
    rows. Values are kept as strings (transformation happens downstream).
    """
    text = text.lstrip("﻿")  # strip BOM if present
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames:
        reader.fieldnames = [(name or "").strip() for name in reader.fieldnames]

    records = []
    for row in reader:
        cleaned = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items() if key}
        if any(value not in (None, "") for value in cleaned.values()):
            records.append(cleaned)
        if limit and len(records) >= limit:
            break
    return records
