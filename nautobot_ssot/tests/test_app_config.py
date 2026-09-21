"""Tests for the nautobot_ssot AppConfig and app-level helpers."""

from unittest.mock import MagicMock, patch

from django.apps import apps
from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.extras.plugins import NautobotAppConfig

import nautobot_ssot
from nautobot_ssot import NautobotSSOTAppConfig, _check_for_conflicting_apps
from nautobot_ssot.models import Sync, SyncLogEntry


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


class TestAppConfigSearchableModels(TestCase):
    """Tests for how `enable_global_search` drives NautobotSSOTAppConfig.searchable_models."""

    @staticmethod
    def _ready_app_config(plugin_config):
        """Instantiate a fresh app config and run ready() under the given `nautobot_ssot` PLUGINS_CONFIG.

        A fresh instance, rather than the loaded app registry entry, starts each test from the class-level
        state. The parent ready() and integration signal loading are mocked, as in TestAppConfigReady, so
        only this app's own ready() logic runs.
        """
        app_config = NautobotSSOTAppConfig("nautobot_ssot", nautobot_ssot)
        with (
            override_settings(PLUGINS_CONFIG={"nautobot_ssot": plugin_config}),
            patch.object(NautobotAppConfig, "ready"),
            patch("nautobot_ssot.each_enabled_integration_module", return_value=[]),
        ):
            app_config.ready()
        return app_config

    def test_enabled_or_absent_makes_sync_and_synclogentry_searchable(self):
        """Enabled explicitly or by default, exactly Sync and SyncLogEntry are searchable, as lowercase model names."""
        for plugin_config in ({"enable_global_search": True}, {}):
            with self.subTest(plugin_config=plugin_config):
                app_config = self._ready_app_config(plugin_config)
                self.assertEqual(app_config.searchable_models, ["sync", "synclogentry"])
                self.assertEqual(
                    [apps.get_model("nautobot_ssot", name) for name in app_config.searchable_models],
                    [Sync, SyncLogEntry],
                )

    def test_disabled_makes_no_models_searchable(self):
        app_config = self._ready_app_config({"enable_global_search": False})
        self.assertEqual(app_config.searchable_models, [])

    def test_disabled_overrides_class_level_default(self):
        """A class-level `searchable_models` default must not leak through when global search is disabled."""
        with patch.object(NautobotSSOTAppConfig, "searchable_models", ["sync"], create=True):
            app_config = self._ready_app_config({"enable_global_search": False})
            self.assertEqual(app_config.searchable_models, [])
