"""Unit tests for helpers and base-class stubs in nautobot_ssot.jobs.base."""

import logging
import threading
from unittest.mock import MagicMock

from nautobot.apps.testing import TestCase

from nautobot_ssot.jobs.base import (
    ThreadedAdapterLoader,
    ThreadLogHandler,
    _maybe_suppress_auto_component_creation,
)
from nautobot_ssot.tests.jobs import DataSyncBaseJob


def _make_record(name, level, msg="message"):
    """Build a bare LogRecord for ThreadLogHandler tests."""
    return logging.LogRecord(name=name, level=level, pathname="p", lineno=1, msg=msg, args=None, exc_info=None)


class TestMaybeSuppressAutoComponentCreation(TestCase):
    """Tests for the `_maybe_suppress_auto_component_creation` decorator."""

    def test_suppress_enabled_via_instance_attribute(self):
        """With the opt-in set, the wrapped method runs inside the suppression context and logs once."""

        @_maybe_suppress_auto_component_creation
        def fake_sync(_self, value):
            """Return double the value; stands in for a real sync_data method."""
            return value * 2

        fake_self = MagicMock()
        fake_self.skip_auto_component_creation = True
        result = fake_sync(fake_self, 21)
        self.assertEqual(result, 42)
        fake_self.logger.info.assert_called_once()

    def test_suppress_disabled_runs_unchanged(self):
        """Without the opt-in, the wrapped method runs unchanged and does not log."""

        @_maybe_suppress_auto_component_creation
        def fake_sync(_self, value):
            """Return the value unchanged; stands in for a real sync_data method."""
            return value

        fake_self = MagicMock()
        fake_self.skip_auto_component_creation = False
        result = fake_sync(fake_self, "ok")
        self.assertEqual(result, "ok")
        fake_self.logger.info.assert_not_called()


class TestThreadLogHandler(TestCase):
    """Tests for the ThreadLogHandler used during parallel adapter loading."""

    def test_emit_ignores_records_from_other_threads(self):
        """A record emitted from a different thread than the handler's owner is dropped."""
        handler = ThreadLogHandler("job.logger", thread_id=-1)
        handler.emit(_make_record("nautobot_ssot.adapter", logging.INFO))
        self.assertEqual(handler.records, [])

    def test_emit_skips_debug_from_excluded_loggers(self):
        """DEBUG records from noisy excluded loggers are dropped."""
        handler = ThreadLogHandler("job.logger", thread_id=threading.get_ident())
        handler.emit(_make_record("urllib3.connectionpool", logging.DEBUG))
        self.assertEqual(handler.records, [])

    def test_emit_captures_relevant_record(self):
        """A record from the owning thread on the job logger is captured."""
        handler = ThreadLogHandler("job.logger", thread_id=threading.get_ident())
        handler.emit(_make_record("job.logger", logging.INFO))
        self.assertEqual(len(handler.records), 1)


class TestDataSyncBaseJobStubs(TestCase):
    """Tests for the overridable stub methods on DataSyncBaseJob."""

    def setUp(self):
        """Instantiate a base sync job."""
        self.job = DataSyncBaseJob()

    def test_load_source_adapter_not_implemented(self):
        """The base load_source_adapter must be overridden by subclasses."""
        with self.assertRaises(NotImplementedError):
            self.job.load_source_adapter()

    def test_load_target_adapter_not_implemented(self):
        """The base load_target_adapter must be overridden by subclasses."""
        with self.assertRaises(NotImplementedError):
            self.job.load_target_adapter()

    def test_execute_sync_calls_sync_to(self):
        """execute_sync delegates to the source adapter's sync_to when both adapters are set."""
        self.job.source_adapter = MagicMock()
        self.job.target_adapter = MagicMock()
        self.job.execute_sync()
        self.job.source_adapter.sync_to.assert_called_once()

    def test_lookup_object_returns_none(self):
        """The base lookup_object helper returns None."""
        self.assertIsNone(self.job.lookup_object("device", "dev1"))

    def test_data_mappings_empty(self):
        """The base data_mappings classmethod returns an empty list."""
        self.assertEqual(DataSyncBaseJob.data_mappings(), [])


class TestThreadedAdapterLoader(TestCase):
    """Tests for the ThreadedAdapterLoader dataclass."""

    def test_invalid_adapter_type_raises(self):
        """Constructing the loader with an invalid adapter type raises ValueError."""
        with self.assertRaises(ValueError):
            ThreadedAdapterLoader(adapter="bogus", job=MagicMock(), job_result=MagicMock())
