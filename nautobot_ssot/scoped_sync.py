"""Helper that executes a scoped sync inline.

Lives at the package root (rather than under ``api/``) so it can be imported
by tests / scripts / management commands without triggering the
``nautobot_ssot.api`` module import chain (which pulls in ``filters`` →
``models`` → integration ConfigModels and only resolves cleanly inside a
fully-bootstrapped Nautobot process).

The framework-level API view (``nautobot_ssot.api.views.ScopedSyncTrigger``)
delegates here.
"""

from __future__ import annotations

import importlib
import logging

from .flags import SSoTFlags
from .scope import SyncScope
from .utils.streaming_pipeline import run_streaming_sync


_logger = logging.getLogger("nautobot_ssot.scoped_sync")


def run_scoped_sync_inline(
    *,
    job_class_path: str,
    scope: SyncScope,
    flags: SSoTFlags,
    user=None,
) -> dict:
    """Construct adapters via the named job class and run a scoped streaming sync.

    Args:
        job_class_path: dotted import path to a class with
            ``load_source_adapter()`` / ``load_target_adapter()`` methods (i.e.
            anything quacking like a ``DataSyncBaseJob`` subclass).
        scope: the SyncScope describing which subtree to sync.
        flags: SSoTFlags controlling tier + validation hooks.
        user: optional Django user for the change-logging context.

    Returns:
        Dict with ``sync_id`` / ``diff_stats`` / ``sync_stats`` /
        ``duration_s`` / ``scope_keys_in_subtree``. (sync_id is a placeholder
        in this synchronous-demo path; production async flow would create
        and return a real ``Sync`` model UUID.)
    """
    module_path, class_name = job_class_path.rsplit(".", 1)
    job_module = importlib.import_module(module_path)
    job_class = getattr(job_module, class_name)

    job = job_class()
    job.dryrun = False
    job.logger = _NoopLogger()
    job.sync = None
    job.flags = flags

    job.load_source_adapter()
    job.load_target_adapter()

    result = run_streaming_sync(
        job.source_adapter,
        job.target_adapter,
        flags=flags,
        skip_load=True,
        user=user,
        scope=scope,
    )

    return {
        "sync_id": "(no-Sync-record-in-demo-path)",  # Real async flow creates Sync row
        "diff_stats": result.diff_stats,
        "sync_stats": result.sync_stats,
        "duration_s": result.total,
        "scope_keys_in_subtree": result.diff_stats.get("scope_keys_in_subtree", 0),
    }


class _NoopLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def debug(self, *a, **kw): pass
    def exception(self, *a, **kw): pass
