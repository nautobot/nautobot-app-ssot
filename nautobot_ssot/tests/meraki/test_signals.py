"""Regression tests for the Meraki SSoT post-migrate signal."""

from django.apps import apps as global_apps
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Platform

from nautobot_ssot.integrations.meraki.signals import nautobot_database_ready_callback


class TestMerakiSignals(TestCase):
    """Tests for the Meraki ``nautobot_database_ready_callback`` signal."""

    databases = ("default", "job_logs")

    def test_does_not_raise_with_multiple_meraki_platforms(self):
        """Regression for #1159.

        The callback previously looked up the canonical platform with
        ``Platform.objects.update_or_create(name__icontains="Meraki", ...)``, which raised
        ``Platform.MultipleObjectsReturned`` (crashing ``post_migrate``/startup) whenever more
        than one Platform name contained "Meraki". It must now look the platform up by its exact
        name and leave the others untouched.
        """
        Platform.objects.create(name="Meraki Dashboard")
        Platform.objects.create(name="meraki-cloud-controller")

        # Must not raise Platform.MultipleObjectsReturned.
        nautobot_database_ready_callback(sender=None, apps=global_apps)

        platform = Platform.objects.get(name="Cisco Meraki")
        self.assertEqual(platform.network_driver, "cisco_meraki")
