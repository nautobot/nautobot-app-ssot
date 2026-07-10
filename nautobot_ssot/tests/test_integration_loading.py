"""Tests for the per-module `_add_integrations()` hooks and example-job hiding."""

import importlib
from unittest.mock import MagicMock, patch

from django.conf import settings
from nautobot.apps.testing import TestCase

import nautobot_ssot.api.urls as api_urls
import nautobot_ssot.jobs as ssot_jobs
import nautobot_ssot.urls as ssot_urls
from nautobot_ssot import navigation
from nautobot_ssot.exceptions import JobException


class TestJobsAddIntegrations(TestCase):
    """Tests for nautobot_ssot.jobs._add_integrations and example-job hiding."""

    def test_add_integrations_appends_module_jobs(self):
        """Jobs exposed by an enabled integration module are appended to the jobs list."""
        sentinel_job = type("SentinelJob", (), {})
        fake_module = MagicMock()
        fake_module.jobs = [sentinel_job]
        fake_module.__file__ = "fake_integration/jobs.py"

        original_len = len(ssot_jobs.jobs)
        try:
            with patch("nautobot_ssot.jobs.each_enabled_integration_module", return_value=[fake_module]):
                ssot_jobs._add_integrations()  # pylint: disable=protected-access
            self.assertIn(sentinel_job, ssot_jobs.jobs)
            self.assertEqual(len(ssot_jobs.jobs), original_len + 1)
        finally:
            del ssot_jobs.jobs[original_len:]

    def test_add_integrations_duplicate_job_raises(self):
        """A job already present in the jobs list raises JobException."""
        existing_job = ssot_jobs.jobs[0]
        fake_module = MagicMock()
        fake_module.jobs = [existing_job]
        fake_module.__file__ = "fake_integration/jobs.py"

        with patch("nautobot_ssot.jobs.each_enabled_integration_module", return_value=[fake_module]):
            with self.assertRaises(JobException):
                ssot_jobs._add_integrations()  # pylint: disable=protected-access

    def test_jobs_empty_when_example_jobs_hidden(self):
        """When `hide_example_jobs` is truthy, the example jobs are not registered."""
        self.addCleanup(importlib.reload, ssot_jobs)
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"hide_example_jobs": True}):
            importlib.reload(ssot_jobs)
            self.assertEqual(ssot_jobs.jobs, [])


class TestModuleAddIntegrations(TestCase):
    """Tests for the navigation/urls/api-urls `_add_integrations()` hooks."""

    def test_module_add_integrations(self):
        """Each module appends the items/urlpatterns exposed by an enabled integration module."""
        cases = [
            ("navigation", navigation, "items", "nav_items"),
            ("urls", ssot_urls, "urlpatterns", "urlpatterns"),
            ("api.urls", api_urls, "urlpatterns", "urlpatterns"),
        ]
        for label, module, list_attr, fake_attr in cases:
            with self.subTest(module=label):
                fake_module = MagicMock()
                setattr(fake_module, fake_attr, [MagicMock()])
                original_len = len(getattr(module, list_attr))
                try:
                    with patch(f"nautobot_ssot.{label}.each_enabled_integration_module", return_value=[fake_module]):
                        module._add_integrations()  # pylint: disable=protected-access
                    self.assertEqual(len(getattr(module, list_attr)), original_len + 1)
                finally:
                    del getattr(module, list_attr)[original_len:]
