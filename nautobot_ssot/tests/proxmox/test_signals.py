# pylint: disable=R0801
"""Tests for the Proxmox VE integration's signal handlers."""

from unittest.mock import patch

from django.apps import apps as django_apps
from nautobot.apps.testing import TestCase
from nautobot.extras.models import ExternalIntegration, SecretsGroup

from nautobot_ssot.integrations.proxmox import signals
from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig


class TestProxmoxSignals(TestCase):
    """Tests for the nautobot_database_ready signal receivers."""

    def setUp(self):
        """Run the prerequisite-creating receiver before each test.

        create_default_proxmox_config() only creates a config when the SSOTProxmoxConfig table is
        entirely empty, and the persistent (``--keepdb``) test database already has a default config
        row from initial migration/setup. Clear it here so each test observes the function's own
        create-or-skip behavior rather than that pre-existing row.
        """
        signals.nautobot_database_ready_callback(sender=None, apps=django_apps)
        SSOTProxmoxConfig.objects.all().delete()

    def test_create_default_proxmox_config_creates_objects(self):
        """The default SecretsGroup/ExternalIntegration/SSOTProxmoxConfig are created."""
        signals.create_default_proxmox_config(sender=None, apps=django_apps)

        self.assertTrue(SecretsGroup.objects.filter(name="ProxmoxSSOTDefaultSecretGroup").exists())
        self.assertTrue(ExternalIntegration.objects.filter(name="DefaultProxmoxInstance").exists())
        self.assertTrue(SSOTProxmoxConfig.objects.filter(name="ProxmoxConfigDefault").exists())

    def test_create_default_proxmox_config_opt_out(self):
        """No SSOTProxmoxConfig is created when proxmox_create_default_secrets is disabled."""
        with patch.dict(signals.config, {"proxmox_create_default_secrets": False}):
            signals.create_default_proxmox_config(sender=None, apps=django_apps)

        self.assertFalse(SSOTProxmoxConfig.objects.filter(name="ProxmoxConfigDefault").exists())
