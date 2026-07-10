"""Tests for API source fetching — pagination behavior against mocked APIs."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from nautobot_ssot.integrations.data_import.engine.sources import fetch_api_records


def _fake_integration():
    """Duck-typed ExternalIntegration — fetch only reads these attributes."""
    return SimpleNamespace(remote_url="http://api.test", verify_ssl=False, timeout=5, secrets_group=None)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _offset_cfg(page_size=100):
    return {
        "id": "ports",
        "api_path": "/ports",
        "data_path": "ports",
        "method": "GET",
        "pagination": {"type": "offset", "page_size": page_size, "params": {}},
    }


class PaginationGuardTests(SimpleTestCase):
    """The engine must not loop or duplicate when an API ignores pagination."""

    def test_api_that_ignores_pagination_stops_after_one_page(self):
        """LibreNMS-style behavior: full result set returned regardless of offset."""
        all_ports = {"ports": [{"port_id": i} for i in range(126)]}
        with patch(
            "nautobot_ssot.integrations.data_import.engine.sources.requests.get",
            return_value=_FakeResponse(all_ports),
        ) as mock_get:
            records = fetch_api_records(_fake_integration(), _offset_cfg(page_size=100))
        # 126 unique records — not 252, not an infinite loop.
        self.assertEqual(len(records), 126)
        self.assertEqual(len({r["port_id"] for r in records}), 126)
        # One real page + one repeat that triggered the guard.
        self.assertEqual(mock_get.call_count, 2)

    def test_wellbehaved_offset_pagination_still_works(self):
        pages = [
            {"ports": [{"port_id": i} for i in range(100)]},
            {"ports": [{"port_id": i} for i in range(100, 126)]},
        ]
        with patch(
            "nautobot_ssot.integrations.data_import.engine.sources.requests.get",
            side_effect=[_FakeResponse(p) for p in pages],
        ) as mock_get:
            records = fetch_api_records(_fake_integration(), _offset_cfg(page_size=100))
        self.assertEqual(len(records), 126)
        self.assertEqual(mock_get.call_count, 2)  # short page ends the loop

    def test_exact_multiple_ends_on_empty_page(self):
        """Total records an exact multiple of page_size: a trailing empty page ends cleanly."""
        pages = [
            {"ports": [{"port_id": i} for i in range(100)]},
            {"ports": [{"port_id": i} for i in range(100, 200)]},
            {"ports": []},
        ]
        with patch(
            "nautobot_ssot.integrations.data_import.engine.sources.requests.get",
            side_effect=[_FakeResponse(p) for p in pages],
        ):
            records = fetch_api_records(_fake_integration(), _offset_cfg(page_size=100))
        self.assertEqual(len(records), 200)

    def test_limit_short_circuits(self):
        all_ports = {"ports": [{"port_id": i} for i in range(126)]}
        with patch(
            "nautobot_ssot.integrations.data_import.engine.sources.requests.get",
            return_value=_FakeResponse(all_ports),
        ) as mock_get:
            records = fetch_api_records(_fake_integration(), _offset_cfg(page_size=100), limit=50)
        self.assertEqual(len(records), 50)
        self.assertEqual(mock_get.call_count, 1)

    def test_page_pagination_guard(self):
        cfg = {
            "id": "ports",
            "api_path": "/ports",
            "data_path": "ports",
            "pagination": {"type": "page", "page_size": 100, "params": {}},
        }
        all_ports = {"ports": [{"port_id": i} for i in range(126)]}
        with patch(
            "nautobot_ssot.integrations.data_import.engine.sources.requests.get",
            return_value=_FakeResponse(all_ports),
        ):
            records = fetch_api_records(_fake_integration(), cfg)
        self.assertEqual(len(records), 126)
