"""Tests for the nautobot_ssot AppConfig and app-level helpers."""

from unittest.mock import MagicMock, patch

from django.apps import apps
from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.extras.plugins import NautobotAppConfig

from nautobot_ssot import _check_for_conflicting_apps


class TestCheckForConflictingApps(TestCase):
    """Tests for the _check_for_conflicting_apps guard."""

    @override_settings(PLUGINS=["nautobot_ssot", "nautobot_ssot_infoblox"])
    def test_conflicting_app_raises(self):
        """A legacy standalone SSoT app installed alongside nautobot_ssot raises RuntimeError."""
        with self.assertRaises(RuntimeError):
            _check_for_conflicting_apps()

    @override_settings(PLUGINS=["nautobot_ssot"])
    def test_no_conflict_passes(self):
        """With no conflicting apps installed, the check passes silently."""
        _check_for_conflicting_apps()


class TestAppConfigReady(TestCase):
    """Tests for NautobotSSOTAppConfig.ready signal registration."""

    def test_ready_registers_integration_signals(self):
        """ready() registers signals for each enabled integration module exposing them."""
        app_config = apps.get_app_config("nautobot_ssot")
        fake_module = MagicMock()
        fake_module.__file__ = "fake_integration/signals.py"
        # Mock the parent ready() so we exercise only this app's integration-signal registration
        # loop without re-running Nautobot's full app initialization side effects.
        with (
            patch.object(NautobotAppConfig, "ready"),
            patch("nautobot_ssot.each_enabled_integration_module", return_value=[fake_module]),
        ):
            app_config.ready()
        fake_module.register_signals.assert_called_once_with(app_config)
