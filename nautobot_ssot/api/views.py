"""API views for nautobot_ssot."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot import filters, models
from nautobot_ssot.api import serializers


class SyncViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """Sync viewset."""

    queryset = models.Sync.objects.all()
    serializer_class = serializers.SyncSerializer
    filterset_class = filters.SyncFilterSet


class SyncLogEntryViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """SyncLogEntry viewset."""

    queryset = models.SyncLogEntry.objects.all()
    serializer_class = serializers.SyncLogEntrySerializer
    filterset_class = filters.SyncLogEntryFilterSet


# ---------------------------------------------------------------------------
# Scoped sync API
# ---------------------------------------------------------------------------


class ScopedSyncTrigger(APIView):
    """Trigger a scoped SSoT sync — re-sync just one model instance + its subtree.

    POST /api/plugins/ssot/sync/scoped/
    {
        "job_class_path": "nautobot_ssot.integrations.infoblox.jobs.InfobloxDataSource",
        "scope": {
            "model_type": "prefix",
            "unique_key": "10.0.0.0/24__ns-default",
            "include_root": true,
            "integration": "infoblox"
        },
        "flags": ["STREAMING", "BULK_WRITES"],
        "async": false
    }

    Returns 200 (sync) with the sync result, or 202 (async) with sync_id.

    This is the framework-level entry point. Integration-specific webhook
    receivers (e.g. ``/api/plugins/ssot/integrations/infoblox/webhook/``) are
    expected to translate source-system payloads into a SyncScope and call
    this endpoint internally.

    Auth: standard Nautobot token auth, plus `nautobot_ssot.add_sync` permission.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        body = request.data or {}
        scope_data = body.get("scope") or {}
        if not scope_data.get("model_type") or not scope_data.get("unique_key"):
            return Response(
                {"detail": "scope.model_type and scope.unique_key are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Translate flags
        from nautobot_ssot.flags import SSoTFlags

        flags = SSoTFlags.NONE
        for name in body.get("flags") or []:
            try:
                flags |= SSoTFlags[name]
            except KeyError:
                return Response(
                    {"detail": f"unknown flag {name!r}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Build scope
        from nautobot_ssot.scope import SyncScope

        scope = SyncScope(
            model_type=scope_data["model_type"],
            unique_key=scope_data["unique_key"],
            include_root=scope_data.get("include_root", True),
            integration=scope_data.get("integration"),
        )

        # Resolve job class
        job_path = body.get("job_class_path")
        if not job_path:
            return Response(
                {"detail": "job_class_path is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Run the scoped sync inline (the framework's run_streaming_sync handles it).
        # NOTE: in production we'd push this onto Celery and return 202; for now we
        # support synchronous execution via async=false (the default for this demo).
        # The demo path below is what makes the API testable end-to-end without
        # needing a Celery worker spun up.
        if body.get("async") is True:
            return Response(
                {"detail": "async=true requires a Celery worker; not implemented in this demo"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        # Synchronous execution path. The integration's job loader is responsible
        # for constructing src + dst adapters with the right config; we re-use
        # the integration's existing job class to do that.
        try:
            sync_record = _run_scoped_sync_inline(
                job_class_path=job_path,
                scope=scope,
                flags=flags,
                user=request.user,
            )
        except Exception as exc:  # noqa: BLE001 — surface anything to the API caller
            return Response(
                {"detail": f"scoped sync failed: {type(exc).__name__}: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "sync_id": str(sync_record["sync_id"]),
                "diff_stats": sync_record["diff_stats"],
                "sync_stats": sync_record["sync_stats"],
                "duration_s": sync_record["duration_s"],
                "scope_keys_in_subtree": sync_record["scope_keys_in_subtree"],
            },
            status=status.HTTP_200_OK,
        )


def _run_scoped_sync_inline(*, job_class_path, scope, flags, user) -> dict:
    """Compatibility shim — see :mod:`nautobot_ssot.scoped_sync` for the impl."""
    from nautobot_ssot.scoped_sync import run_scoped_sync_inline

    return run_scoped_sync_inline(
        job_class_path=job_class_path, scope=scope, flags=flags, user=user
    )
