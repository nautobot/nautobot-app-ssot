"""Test the Job class in this plugin."""
import os
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from nautobot.dcim.models import Device, DeviceRole, DeviceType, Interface, Manufacturer, Region, Site
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import Secret, SecretsGroup, SecretsGroupAssociation, Status

from nautobot_ssot_servicenow.jobs import ServiceNowDataTarget
from nautobot_ssot_servicenow.models import SSOTServiceNowConfig


class ServiceNowDataTargetJobTestCase(TestCase):
    """Test the ServiceNowDataTarget Job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Nautobot ⟹ ServiceNow", ServiceNowDataTarget.name)
        self.assertEqual("Nautobot ⟹ ServiceNow", ServiceNowDataTarget.Meta.name)
        self.assertEqual("ServiceNow", ServiceNowDataTarget.Meta.data_target)
        self.assertEqual("Synchronize data from Nautobot into ServiceNow.", ServiceNowDataTarget.description)
        self.assertEqual("Synchronize data from Nautobot into ServiceNow.", ServiceNowDataTarget.Meta.description)

    def test_data_mappings(self):
        """Verify correctness of the data_mappings() API."""
        mappings = ServiceNowDataTarget.data_mappings()

        self.assertEqual("Device", mappings[0].source_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[0].source_url)
        self.assertEqual("IP Switch", mappings[0].target_name)
        self.assertIsNone(mappings[0].target_url)

        self.assertEqual("Device Type", mappings[1].source_name)
        self.assertEqual(reverse("dcim:devicetype_list"), mappings[1].source_url)
        self.assertEqual("Hardware Product Model", mappings[1].target_name)
        self.assertIsNone(mappings[1].target_url)

        self.assertEqual("Interface", mappings[2].source_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[2].source_url)
        self.assertEqual("Interface", mappings[2].target_name)
        self.assertIsNone(mappings[2].target_url)

        self.assertEqual("Manufacturer", mappings[3].source_name)
        self.assertEqual(reverse("dcim:manufacturer_list"), mappings[3].source_url)
        self.assertEqual("Company", mappings[3].target_name)
        self.assertIsNone(mappings[3].target_url)

        self.assertEqual("Region", mappings[4].source_name)
        self.assertEqual(reverse("dcim:region_list"), mappings[4].source_url)
        self.assertEqual("Location", mappings[4].target_name)
        self.assertIsNone(mappings[4].target_url)

        self.assertEqual("Site", mappings[5].source_name)
        self.assertEqual(reverse("dcim:site_list"), mappings[5].source_url)
        self.assertEqual("Location", mappings[5].target_name)
        self.assertIsNone(mappings[5].target_url)

    @override_settings(
        PLUGINS_CONFIG={"nautobot_ssot_servicenow": {"instance": "dev12345", "username": "admin", "password": ""}}
    )
    def test_config_information_settings(self):
        """Verify the config_information() API for configs provided in Django settings."""
        config_information = ServiceNowDataTarget.config_information()
        self.assertEqual(
            config_information,
            {
                "ServiceNow instance": "dev12345",
                "Username": "admin",
                # password should NOT be present!
            },
        )

    @override_settings(PLUGINS_CONFIG={})
    @mock.patch.dict(os.environ, {"SNOW_USERNAME": "someuser", "SNOW_PASSWORD": "notsosecret"})
    def test_config_information_db(self):
        """Verify the config_information() API for configs provided in the database."""
        db_config = SSOTServiceNowConfig.load()
        db_config.servicenow_instance = "dev98765"
        user_secret = Secret.objects.create(
            name="ServiceNow Username",
            slug="servicenow-username",
            provider="environment-variable",
            parameters={"variable": "SNOW_USERNAME"},
        )
        password_secret = Secret.objects.create(
            name="ServiceNow Password",
            slug="servicenow-password",
            provider="environment-variable",
            parameters={"variable": "SNOW_PASSWORD"},
        )
        db_config.servicenow_secrets = SecretsGroup.objects.create(
            name="ServiceNow Secrets",
            slug="servicenow-secrets",
        )
        SecretsGroupAssociation.objects.create(
            group=db_config.servicenow_secrets,
            secret=user_secret,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        SecretsGroupAssociation.objects.create(
            group=db_config.servicenow_secrets,
            secret=password_secret,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        db_config.save()

        config_information = ServiceNowDataTarget.config_information()
        self.assertEqual(
            config_information,
            {
                "ServiceNow instance": "dev98765",
                "Username": "someuser",
                # password should NOT be present!
            },
        )

    def test_lookup_object(self):
        """Validate the lookup_object() API."""
        region = Region.objects.create(name="My Region", slug="my-region")
        site = Site.objects.create(name="My Site", slug="my-site", status=Status.objects.get(slug="active"))
        manufacturer = Manufacturer.objects.create(name="Cisco", slug="cisco")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="CSR 1000v", slug="csr1000v")
        device_role = DeviceRole.objects.create(name="Router", slug="router")
        device = Device.objects.create(
            name="mydevice",
            device_role=device_role,
            device_type=device_type,
            site=site,
            status=Status.objects.get(slug="active"),
        )
        interface = Interface.objects.create(device=device, name="eth0")

        job = ServiceNowDataTarget()

        self.assertEqual(job.lookup_object("location", "My Region"), region)
        self.assertEqual(job.lookup_object("location", "My Site"), site)
        self.assertEqual(job.lookup_object("device", "mydevice"), device)
        self.assertEqual(job.lookup_object("interface", "mydevice__eth0"), interface)

        self.assertIsNone(job.lookup_object("location", "no such region"))
        self.assertIsNone(job.lookup_object("location", "no such site"))
        self.assertIsNone(job.lookup_object("device", "no-such-device"))
        self.assertIsNone(job.lookup_object("interface", "no-such-device__no-such-interface"))
        self.assertIsNone(job.lookup_object("nosuchmodel", ""))
