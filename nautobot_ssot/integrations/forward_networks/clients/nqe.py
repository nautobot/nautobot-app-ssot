"""Forward Networks NQE (Network Query Engine) API client."""

from typing import Any, Dict, List

from .base import BaseResource


class NQEAPI(BaseResource):
    """Forward Networks NQE API resource."""

    def run_query(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/nqe - Run an NQE query."""
        resp = self._client.post("/api/nqe", json=data)
        return self._handle_response(resp)

    def get_queries(self) -> List[Dict[str, Any]]:
        """GET /api/nqe/queries - Get available NQE queries."""
        resp = self._client.get("/api/nqe/queries")
        return self._handle_response(resp)

    def run_diff_query(self, before: str, after: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/nqe-diffs/{before}/{after} - Run NQE diff query between snapshots."""
        resp = self._client.post(f"/api/nqe-diffs/{before}/{after}", json=data)
        return self._handle_response(resp)
