"""Tests for the Proxmox VE integration's signal handlers."""

from unittest.mock import patch

from django.apps import apps as django_apps
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Location
from nautobot.extras.models import ExternalIntegration, SecretsGroup

from nautobot_ssot.integrations.proxmox import signals
from nautobot_ssot.integrations.proxmox.constants import NODE_LOCATION_NAME
from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig


class TestProxmoxSignals(TestCase):
    """Tests for the nautobot_database_ready signal receivers."""

    def setUp(self):
        """Create all prerequisites, then delete existing configs so each test starts with none."""
        with patch.dict(signals.config, {"proxmox_create_default_secrets": True}):
            signals.nautobot_database_ready_callback(sender=None, apps=django_apps)
        # A --keepdb test database already has a default config, which would make the create step a no-op.
        SSOTProxmoxConfig.objects.all().delete()

    def test_create_default_proxmox_config_creates_objects(self):
        """The default SecretsGroup/ExternalIntegration/SSOTProxmoxConfig are created."""
        with patch.dict(signals.config, {"proxmox_create_default_secrets": True}):
            signals.create_default_proxmox_config(sender=None, apps=django_apps)

        self.assertTrue(SecretsGroup.objects.filter(name="ProxmoxSSOTDefaultSecretGroup").exists())
        self.assertTrue(ExternalIntegration.objects.filter(name="DefaultProxmoxInstance").exists())
        self.assertTrue(SSOTProxmoxConfig.objects.filter(name="ProxmoxConfigDefault").exists())

    def test_create_default_proxmox_config_opt_out(self):
        """No SSOTProxmoxConfig is created when proxmox_create_default_secrets is disabled."""
        with patch.dict(signals.config, {"proxmox_create_default_secrets": False}):
            signals.create_default_proxmox_config(sender=None, apps=django_apps)

        self.assertFalse(SSOTProxmoxConfig.objects.filter(name="ProxmoxConfigDefault").exists())

    def test_nautobot_database_ready_callback_creates_default_location_by_default(self):
        """The default Location is created when proxmox_create_default_secrets is enabled."""
        Location.objects.filter(name=NODE_LOCATION_NAME).delete()

        with patch.dict(signals.config, {"proxmox_create_default_secrets": True}):
            signals.nautobot_database_ready_callback(sender=None, apps=django_apps)

        self.assertTrue(Location.objects.filter(name=NODE_LOCATION_NAME).exists())

    def test_nautobot_database_ready_callback_skips_default_location_when_opted_out(self):
        """The default Location is not created when proxmox_create_default_secrets is disabled."""
        Location.objects.filter(name=NODE_LOCATION_NAME).delete()

        with patch.dict(signals.config, {"proxmox_create_default_secrets": False}):
            signals.nautobot_database_ready_callback(sender=None, apps=django_apps)

        self.assertFalse(Location.objects.filter(name=NODE_LOCATION_NAME).exists())
