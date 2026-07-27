# pylint: disable=R0801
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
        """Run the prerequisite-creating receiver before each test.

        create_default_proxmox_config() only creates a config when the SSOTProxmoxConfig table is
        entirely empty, and the persistent (``--keepdb``) test database already has a default config
        row from initial migration/setup. Clear it here so each test observes the function's own
        create-or-skip behavior rather than that pre-existing row.

        Forces proxmox_create_default_secrets=True regardless of the real ambient setting, so every
        test starts from the full prerequisite set (including the default Location) and only opts
        out locally, the same way test_create_default_proxmox_config_opt_out does.
        """
        with patch.dict(signals.config, {"proxmox_create_default_secrets": True}):
            signals.nautobot_database_ready_callback(sender=None, apps=django_apps)
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
        """The default Location is (re)created when proxmox_create_default_secrets is enabled."""
        Location.objects.filter(name=NODE_LOCATION_NAME).delete()

        with patch.dict(signals.config, {"proxmox_create_default_secrets": True}):
            signals.nautobot_database_ready_callback(sender=None, apps=django_apps)

        self.assertTrue(Location.objects.filter(name=NODE_LOCATION_NAME).exists())

    def test_nautobot_database_ready_callback_skips_default_location_when_opted_out(self):
        """The default Location is not (re)created when proxmox_create_default_secrets is disabled.

        Unlike the Secrets/SecretsGroup/ExternalIntegration/Config bootstrap, every other schema
        prerequisite (Tag, CustomField, Relationship, Statuses, node Device Manufacturer/DeviceType/
        Role) is still created regardless of this setting — only the default Location, which exists
        solely as an initial value for a fresh Config's default_location field, is skipped.
        """
        Location.objects.filter(name=NODE_LOCATION_NAME).delete()

        with patch.dict(signals.config, {"proxmox_create_default_secrets": False}):
            signals.nautobot_database_ready_callback(sender=None, apps=django_apps)

        self.assertFalse(Location.objects.filter(name=NODE_LOCATION_NAME).exists())
