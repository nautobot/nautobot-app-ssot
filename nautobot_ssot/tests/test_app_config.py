"""Tests for the nautobot_ssot AppConfig and app-level helpers."""

from unittest.mock import patch

from django.apps import apps
from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.extras.plugins import NautobotAppConfig

import nautobot_ssot
from nautobot_ssot import NautobotSSOTAppConfig
from nautobot_ssot.models import Sync, SyncLogEntry


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
