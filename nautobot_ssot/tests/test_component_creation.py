"""Tests for the skip_auto_component_creation opt-in on DataSyncBaseJob.

Covers the feature-detection wrapper around
:class:`nautobot.apps.dcim.SkipAutoComponentCreation`, the job-level class
attribute / PLUGINS_CONFIG settings integration on :class:`DataSyncBaseJob`,
and end-to-end suppression of Nautobot Device/Module component instantiation
when the upstream extension point is available.

Tests that exercise actual suppression behaviour are skipped if the running
Nautobot version does not yet ship ``nautobot.apps.dcim.SkipAutoComponentCreation``
(see https://github.com/nautobot/nautobot/issues/9026).
"""

import builtins
import contextlib
import importlib
import os.path
import types
import unittest
from unittest.mock import patch

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.core.testing import TestCase, TransactionTestCase
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import (
    Device,
    DeviceType,
    InterfaceTemplate,
    Location,
    LocationType,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
)
from nautobot.extras.models import JobResult, Role, Status

from nautobot_ssot.contrib import SkipAutoComponentCreation, is_auto_component_creation_suppressed
from nautobot_ssot.contrib import component_creation as component_creation_module
from nautobot_ssot.contrib.component_creation import upstream_available
from nautobot_ssot.tests.jobs import DataSyncBaseJob

_UPSTREAM_REQUIRED = (
    "nautobot.apps.dcim.SkipAutoComponentCreation is not available in this Nautobot "
    "installation; end-to-end suppression cannot be exercised. See "
    "https://github.com/nautobot/nautobot/issues/9026."
)


def _status_for(model):
    """Return a Status valid for ``model``, creating one if none is associated."""
    status = Status.objects.get_for_model(model).first()
    if status is None:
        status = Status.objects.create(name=f"{model.__name__} Test Status")
        status.content_types.add(ContentType.objects.get_for_model(model))
    return status


@contextlib.contextmanager
def _forced_fallback_module():
    """Reload ``component_creation`` with the upstream import forced to fail.

    Yields the freshly reloaded module so the no-op fallback branch can be exercised
    deterministically, regardless of whether the running Nautobot actually ships
    ``nautobot.apps.dcim.SkipAutoComponentCreation``. The module is reloaded normally
    on exit so other tests see the genuine (environment-dependent) symbols.
    """
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "nautobot.apps.dcim":
            raise ImportError("forced unavailable for test")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = _fake_import
    try:
        yield importlib.reload(component_creation_module)
    finally:
        builtins.__import__ = real_import
        importlib.reload(component_creation_module)


@contextlib.contextmanager
def _forced_upstream_module():
    """Reload ``component_creation`` with the upstream import forced to succeed.

    Substitutes a stand-in ``nautobot.apps.dcim`` module (which may be absent entirely on
    older Nautobot) so the ``try`` import succeeds, exercising the upstream-available branch.
    The module is reloaded normally on exit so other tests see the genuine symbols.
    """
    real_import = builtins.__import__
    fake_module = types.ModuleType("nautobot.apps.dcim")
    fake_module.SkipAutoComponentCreation = object
    fake_module.is_auto_component_creation_suppressed = lambda: False

    def _fake_import(name, *args, **kwargs):
        if name == "nautobot.apps.dcim":
            return fake_module
        return real_import(name, *args, **kwargs)

    builtins.__import__ = _fake_import
    try:
        yield importlib.reload(component_creation_module)
    finally:
        builtins.__import__ = real_import
        importlib.reload(component_creation_module)


class ContextManagerFeatureDetectionTestCase(TestCase):
    """Tests for the feature-detection wrapper itself."""

    def test_context_manager_callable(self):
        """``SkipAutoComponentCreation`` always works as a context manager, upstream or fallback."""
        with SkipAutoComponentCreation():
            pass

    def test_is_auto_component_creation_suppressed_returns_bool(self):
        """The introspection helper returns a bool regardless of upstream availability."""
        self.assertIsInstance(is_auto_component_creation_suppressed(), bool)

    def test_upstream_available_returns_bool(self):
        """``upstream_available()`` returns a bool reflecting whether the upstream symbol was importable."""
        self.assertIsInstance(upstream_available(), bool)

    def test_reports_upstream_available_when_symbols_present(self):
        """With the upstream symbols importable, the module reports upstream as available."""
        with _forced_upstream_module() as component_creation:
            self.assertTrue(component_creation.upstream_available())


class FallbackContextManagerTestCase(TestCase):
    """Tests for the no-op fallback used when the upstream extension point is unavailable.

    These force the ``ImportError`` branch via ``_forced_fallback_module`` so the fallback
    is covered deterministically even on a Nautobot that *does* ship the upstream symbol.
    """

    def test_fallback_reports_unavailable_and_is_noop(self):
        """The fallback reports upstream unavailable, never suppresses, and is a no-op context."""
        with _forced_fallback_module() as component_creation:
            self.assertFalse(component_creation.upstream_available())
            self.assertFalse(component_creation.is_auto_component_creation_suppressed())
            with component_creation.SkipAutoComponentCreation() as ctx:
                self.assertIsInstance(ctx, component_creation.SkipAutoComponentCreation)

    def test_fallback_warns_only_once(self):
        """The fallback emits its warning the first time it is entered and not on later entries."""
        with _forced_fallback_module() as component_creation:
            with self.assertLogs(component_creation.logger, level="WARNING") as captured:
                with component_creation.SkipAutoComponentCreation():
                    pass
                with component_creation.SkipAutoComponentCreation():
                    pass
        self.assertEqual(len(captured.records), 1)
        self.assertIn("SkipAutoComponentCreation is not available", captured.records[0].getMessage())

    def test_fallback_does_not_suppress_exceptions(self):
        """An exception raised inside the fallback context propagates out unchanged."""
        with _forced_fallback_module() as component_creation:
            with self.assertRaises(ValueError):
                with component_creation.SkipAutoComponentCreation():
                    raise ValueError("boom")


@unittest.skipUnless(upstream_available(), _UPSTREAM_REQUIRED)
class ContextManagerSuppressionTestCase(TestCase):
    """End-to-end tests that the context manager actually suppresses on real Device/Module saves.

    Skipped on Nautobot versions that do not ship the upstream extension point.
    """

    @classmethod
    def setUpTestData(cls):
        """Build a DeviceType and ModuleType that each define interface templates."""
        cls.manufacturer = Manufacturer.objects.create(name="SSoT Test Manufacturer")
        cls.device_type = DeviceType.objects.create(manufacturer=cls.manufacturer, model="SSoT Test Model")
        for name in ("eth0", "eth1"):
            InterfaceTemplate.objects.create(
                device_type=cls.device_type,
                name=name,
                type=InterfaceTypeChoices.TYPE_1GE_FIXED,
            )

        cls.module_type = ModuleType.objects.create(manufacturer=cls.manufacturer, model="SSoT Test Module")
        InterfaceTemplate.objects.create(
            module_type=cls.module_type,
            name="mod-eth0",
            type=InterfaceTypeChoices.TYPE_1GE_FIXED,
        )

        cls.location_type = LocationType.objects.create(name="SSoT Test Location Type")
        cls.location_type.content_types.add(ContentType.objects.get_for_model(Device))
        cls.location = Location.objects.create(
            name="SSoT Test Location",
            location_type=cls.location_type,
            status=_status_for(Location),
        )
        cls.device_role = Role.objects.create(name="SSoT Test Role")
        cls.device_role.content_types.add(ContentType.objects.get_for_model(Device))
        cls.device_status = _status_for(Device)
        cls.module_status = _status_for(Module)

    def _create_device(self, name):
        return Device.objects.create(
            device_type=self.device_type,
            role=self.device_role,
            status=self.device_status,
            name=name,
            location=self.location,
        )

    def _create_module(self, device, bay_name):
        module_bay = ModuleBay.objects.create(parent_device=device, name=bay_name, position=bay_name)
        return Module.objects.create(
            module_type=self.module_type,
            parent_module_bay=module_bay,
            status=self.module_status,
        )

    def test_device_components_created_by_default(self):
        """Without opting in, a new Device still gets its template components."""
        device = self._create_device("default-device")
        self.assertEqual(device.interfaces.count(), 2)

    def test_device_components_suppressed_in_context(self):
        """Inside the context manager, a new Device gets no auto components."""
        with SkipAutoComponentCreation():
            device = self._create_device("suppressed-device")
        self.assertEqual(device.interfaces.count(), 0)

    def test_module_components_suppressed_in_context(self):
        """Inside the context manager, a new Module gets no auto components."""
        device = self._create_device("module-parent-suppressed")
        with SkipAutoComponentCreation():
            module = self._create_module(device, "bay-suppressed")
        self.assertEqual(module.interfaces.count(), 0)


@override_settings(JOBS_ROOT=os.path.join(os.path.dirname(__file__), "jobs"))
class SkipAutoComponentCreationJobTestCase(TransactionTestCase):
    """Tests for the ``skip_auto_component_creation`` opt-in on ``DataSyncBaseJob``."""

    databases = (
        "default",
        "job_logs",
    )

    def _run_recording_job(self, job_class):
        """Run ``job_class`` (dry-run) and return the instance after completion."""
        job = job_class()
        job.job_result = JobResult.objects.create(
            name="skip-auto-component-creation-test",
            task_name="skip-auto-component-creation-test",
            worker="default",
        )
        job.run(dryrun=True, memory_profiling=False)
        return job

    @staticmethod
    def _make_recording_job(**attrs):
        """Build a DataSyncBaseJob subclass that records suppression state during the sync."""

        class _RecordingJob(DataSyncBaseJob):
            def __init__(self):
                super().__init__()
                self.suppression_during_sync = None

            def load_source_adapter(self):
                # Runs inside sync_data(); capture whether suppression is active here.
                self.suppression_during_sync = is_auto_component_creation_suppressed()

            def load_target_adapter(self):
                pass

        for key, value in attrs.items():
            setattr(_RecordingJob, key, value)
        return _RecordingJob

    def _context_entries(self, job_class):
        """Run ``job_class`` with the suppression context replaced by a counting spy.

        Returns how many times ``SkipAutoComponentCreation`` was entered during the run.
        This isolates the decorator's flag-resolution decision from whether the upstream
        extension point is actually available, so the OR-semantics matrix is covered in
        every environment (the suppression-effect tests above still skip without upstream).
        """
        entries = {"count": 0}

        class _SpyContext:
            def __enter__(self):
                entries["count"] += 1
                return self

            def __exit__(self, *exc_info):
                return False

        with patch("nautobot_ssot.jobs.base.SkipAutoComponentCreation", _SpyContext):
            self._run_recording_job(job_class)
        return entries["count"]

    # The four rows below are the full attribute-x-setting truth table for the decorator's
    # suppress decision. Each pins the PLUGINS_CONFIG value explicitly so the result does not
    # depend on the ambient configuration, and runs regardless of upstream availability.
    def test_decorator_skips_context_when_neither_opts_in(self):
        """Attribute False and setting False: sync_data() does not enter the suppression context."""
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_auto_component_creation": False}):
            self.assertEqual(self._context_entries(self._make_recording_job(skip_auto_component_creation=False)), 0)

    def test_decorator_enters_context_for_class_attribute_only(self):
        """Attribute True with the setting False still enters the context (OR semantics)."""
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_auto_component_creation": False}):
            self.assertEqual(self._context_entries(self._make_recording_job(skip_auto_component_creation=True)), 1)

    def test_decorator_enters_context_for_setting_only(self):
        """Setting True with the class attribute False still enters the context (OR semantics)."""
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_auto_component_creation": True}):
            self.assertEqual(self._context_entries(self._make_recording_job(skip_auto_component_creation=False)), 1)

    def test_decorator_enters_context_when_both_opt_in(self):
        """Attribute True and setting True enters the context exactly once."""
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_auto_component_creation": True}):
            self.assertEqual(self._context_entries(self._make_recording_job(skip_auto_component_creation=True)), 1)

    def test_default_no_suppression(self):
        """A job without opting in does not suppress autocreation during sync."""
        job = self._run_recording_job(self._make_recording_job())
        # Default state — suppression must be off both during and after.
        self.assertFalse(job.suppression_during_sync)
        self.assertFalse(is_auto_component_creation_suppressed())

    def test_class_attribute_opt_in(self):
        """``skip_auto_component_creation = True`` on the job suppresses during sync."""
        if not upstream_available():
            self.skipTest(_UPSTREAM_REQUIRED)
        job = self._run_recording_job(self._make_recording_job(skip_auto_component_creation=True))
        self.assertTrue(job.suppression_during_sync)
        self.assertFalse(is_auto_component_creation_suppressed())

    def test_settings_opt_in(self):
        """The PLUGINS_CONFIG flag suppresses even without the class attribute."""
        if not upstream_available():
            self.skipTest(_UPSTREAM_REQUIRED)
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_auto_component_creation": True}):
            job = self._run_recording_job(self._make_recording_job())
        self.assertTrue(job.suppression_during_sync)
        self.assertFalse(is_auto_component_creation_suppressed())

    def test_or_semantics_attribute_true_setting_false(self):
        """Class attribute True with the setting False still suppresses (OR semantics)."""
        if not upstream_available():
            self.skipTest(_UPSTREAM_REQUIRED)
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_auto_component_creation": False}):
            job = self._run_recording_job(self._make_recording_job(skip_auto_component_creation=True))
        self.assertTrue(job.suppression_during_sync)

    def test_suppression_released_between_sequential_runs(self):
        """Suppression is scoped per run; a suppressing run does not leak into the next.

        This is the per-invocation isolation property that keeps the feature safe under
        Celery worker reuse (a worker process handling many jobs in sequence).
        """
        if not upstream_available():
            self.skipTest(_UPSTREAM_REQUIRED)
        suppressing = self._run_recording_job(self._make_recording_job(skip_auto_component_creation=True))
        self.assertTrue(suppressing.suppression_during_sync)
        self.assertFalse(is_auto_component_creation_suppressed())

        following = self._run_recording_job(self._make_recording_job())
        self.assertFalse(following.suppression_during_sync)
