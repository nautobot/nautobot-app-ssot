"""Tests for the skip_component_autocreation opt-in (Phases 1 & 2).

Covers three layers:

* The underlying mechanism (`nautobot_ssot.contrib.component_autocreation`): patch
  installation, idempotency, context-manager semantics, and ContextVar isolation.
* End-to-end suppression of Nautobot Device/Module component instantiation.
* Job-level integration via `DataSyncBaseJob` (class attribute + PLUGINS_CONFIG setting).
"""

import os.path
import threading
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

from nautobot_ssot.contrib import is_suppression_active, skip_component_autocreation
from nautobot_ssot.contrib.component_autocreation import install_patches, uninstall_patches
from nautobot_ssot.tests.jobs import DataSyncBaseJob


def _status_for(model):
    """Return a Status valid for ``model``, creating one if none is associated."""
    status = Status.objects.get_for_model(model).first()
    if status is None:
        status = Status.objects.create(name=f"{model.__name__} Test Status")
        status.content_types.add(ContentType.objects.get_for_model(model))
    return status


class ComponentAutocreationMechanismTestCase(TestCase):
    """Unit tests for the patch installer and the context manager."""

    def test_patches_installed_on_models(self):
        """install_patches() (run at app ready) wraps both Device and Module."""
        self.assertTrue(getattr(Device.create_components, "_ssot_wrapped", False))
        self.assertTrue(getattr(Module.create_components, "_ssot_wrapped", False))

    def test_patches_idempotent(self):
        """Re-running install_patches() does not stack wrappers."""
        before_device = Device.create_components
        before_module = Module.create_components
        install_patches()
        self.assertIs(Device.create_components, before_device)
        self.assertIs(Module.create_components, before_module)

    def test_wrapper_preserves_alters_data(self):
        """The wrapper keeps Django's template-safety ``alters_data`` flag."""
        self.assertTrue(getattr(Device.create_components, "alters_data", False))
        self.assertTrue(getattr(Module.create_components, "alters_data", False))

    def test_wrapper_exposes_original(self):
        """The wrapper stores the original callable for rollback/introspection."""
        self.assertTrue(callable(getattr(Device.create_components, "_ssot_original", None)))
        self.assertTrue(callable(getattr(Module.create_components, "_ssot_original", None)))

    def test_uninstall_then_reinstall_restores_wrapper(self):
        """uninstall_patches() restores originals; install_patches() re-wraps."""
        original = Device.create_components._ssot_original
        try:
            uninstall_patches()
            self.assertIs(Device.create_components, original)
            self.assertFalse(getattr(Device.create_components, "_ssot_wrapped", False))
        finally:
            # Always leave the patches installed so we don't affect other tests.
            install_patches()
        self.assertTrue(getattr(Device.create_components, "_ssot_wrapped", False))

    def test_context_manager_inactive_by_default(self):
        """Suppression is off unless explicitly entered."""
        self.assertFalse(is_suppression_active())

    def test_context_manager_activates_and_restores(self):
        """The flag is set inside the block and cleared on exit."""
        with skip_component_autocreation():
            self.assertTrue(is_suppression_active())
        self.assertFalse(is_suppression_active())

    def test_context_manager_nested(self):
        """An outer block keeps suppressing after an inner block exits."""
        with skip_component_autocreation():
            with skip_component_autocreation():
                self.assertTrue(is_suppression_active())
            self.assertTrue(is_suppression_active())
        self.assertFalse(is_suppression_active())

    def test_context_manager_exception_safe(self):
        """An exception inside the block still restores the previous state."""
        with self.assertRaises(RuntimeError):
            with skip_component_autocreation():
                self.assertTrue(is_suppression_active())
                raise RuntimeError("boom")
        self.assertFalse(is_suppression_active())

    def test_contextvar_isolated_across_threads(self):
        """Suppression in one thread does not leak into a separately spawned thread."""
        captured = {}

        def worker():
            captured["value"] = is_suppression_active()

        with skip_component_autocreation():
            self.assertTrue(is_suppression_active())
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

        # A freshly spawned thread starts with its own (default) context.
        self.assertFalse(captured["value"])


class ComponentAutocreationModelTestCase(TestCase):
    """End-to-end tests that real Device/Module component creation is suppressed."""

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
        with skip_component_autocreation():
            device = self._create_device("suppressed-device")
        self.assertEqual(device.interfaces.count(), 0)

    def test_module_components_created_by_default(self):
        """Without opting in, a new Module still gets its template components."""
        device = self._create_device("module-parent-default")
        module = self._create_module(device, "bay-default")
        self.assertEqual(module.interfaces.count(), 1)

    def test_module_components_suppressed_in_context(self):
        """Inside the context manager, a new Module gets no auto components."""
        device = self._create_device("module-parent-suppressed")
        with skip_component_autocreation():
            module = self._create_module(device, "bay-suppressed")
        self.assertEqual(module.interfaces.count(), 0)


@override_settings(JOBS_ROOT=os.path.join(os.path.dirname(__file__), "jobs"))
class SkipComponentAutocreationJobTestCase(TransactionTestCase):
    """Tests for the DataSyncBaseJob.sync_data() integration."""

    databases = (
        "default",
        "job_logs",
    )

    def _run_recording_job(self, job_class):
        """Run ``job_class`` (dry-run) and return the instance after completion."""
        job = job_class()
        job.job_result = JobResult.objects.create(
            name="skip-component-autocreation-test",
            task_name="skip-component-autocreation-test",
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
                self.suppression_during_sync = is_suppression_active()

            def load_target_adapter(self):
                pass

        for key, value in attrs.items():
            setattr(_RecordingJob, key, value)
        return _RecordingJob

    def test_default_no_suppression(self):
        """A job without opting in does not suppress autocreation during sync."""
        job = self._run_recording_job(self._make_recording_job())
        self.assertFalse(job.suppression_during_sync)
        self.assertFalse(is_suppression_active())

    def test_class_attribute_opt_in(self):
        """`skip_component_autocreation = True` on the job suppresses during sync."""
        job = self._run_recording_job(self._make_recording_job(skip_component_autocreation=True))
        self.assertTrue(job.suppression_during_sync)
        self.assertFalse(is_suppression_active())

    def test_settings_opt_in(self):
        """The PLUGINS_CONFIG flag suppresses even without the class attribute."""
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_component_autocreation": True}):
            job = self._run_recording_job(self._make_recording_job())
        self.assertTrue(job.suppression_during_sync)
        self.assertFalse(is_suppression_active())

    def test_or_semantics_attribute_true_setting_false(self):
        """Class attribute True with the setting False still suppresses (OR semantics)."""
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"skip_component_autocreation": False}):
            job = self._run_recording_job(self._make_recording_job(skip_component_autocreation=True))
        self.assertTrue(job.suppression_during_sync)

    def test_suppression_released_between_sequential_runs(self):
        """Suppression is scoped per run; a suppressing run does not leak into the next.

        This is the per-invocation isolation property that keeps the feature safe under
        Celery worker reuse (a worker process handling many jobs in sequence).
        """
        suppressing = self._run_recording_job(self._make_recording_job(skip_component_autocreation=True))
        self.assertTrue(suppressing.suppression_during_sync)
        self.assertFalse(is_suppression_active())

        following = self._run_recording_job(self._make_recording_job())
        self.assertFalse(following.suppression_during_sync)
