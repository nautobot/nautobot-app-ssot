# pylint: disable=duplicate-code
"""Test DNA Center Jobs."""

import os
import uuid
from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from nautobot.core.testing import run_job_for_testing
from nautobot.dcim.models import Controller, ControllerManagedDeviceGroup, Device, Interface, Location, LocationType
from nautobot.extras.choices import CustomFieldTypeChoices, SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import (
    CustomField,
    ExternalIntegration,
    Job,
    JobLogEntry,
    JobResult,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
    Status,
)
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.dna_center import jobs
from nautobot_ssot.tests.dna_center.fixtures import (
    DEVICE_DETAIL_MULTI_LEVEL_FIXTURE,
    DEVICE_FIXTURE,
    MULTI_LEVEL_LOCATION_FIXTURE,
    PORT_FIXTURE,
)


class DnaCenterDataSourceJobTest(TestCase):
    """Test the DNA Center DataSource Job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("DNA Center to Nautobot", jobs.DnaCenterDataSource.name)
        self.assertEqual("DNA Center to Nautobot", jobs.DnaCenterDataSource.Meta.name)
        self.assertEqual("DNA Center", jobs.DnaCenterDataSource.data_source)
        self.assertEqual("Sync information from DNA Center to Nautobot", jobs.DnaCenterDataSource.description)

    def test_data_mapping(self):
        mappings = jobs.DnaCenterDataSource.data_mappings()

        self.assertEqual("Areas", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Locations", mappings[0].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[0].target_url)

        self.assertEqual("Buildings", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Locations", mappings[1].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[1].target_url)

        self.assertEqual("Floors", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Locations", mappings[2].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[2].target_url)

        self.assertEqual("Devices", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("Devices", mappings[3].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[3].target_url)

        self.assertEqual("Interfaces", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("Interfaces", mappings[4].target_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[4].target_url)

        self.assertEqual("IP Addresses", mappings[5].source_name)
        self.assertIsNone(mappings[5].source_url)
        self.assertEqual("IP Addresses", mappings[5].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[5].target_url)

    def test_config_information(self):
        """Verify the config_information() API."""
        config_information = jobs.DnaCenterDataSource.config_information()
        self.assertEqual(config_information, {"Instances": "Found in Extensibility -> External Integrations menu."})


class DnaCenterMultiLevelLocationJobTest(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test to validate Job working with multiple level Location response from DNAC."""

    job_class = jobs.DnaCenterDataSource
    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize shared vars for tests."""
        super().setUp()
        self.status_active = Status.objects.get_or_create(name="Active")[0]
        self.offline_active = Status.objects.get_or_create(name="Offline")[0]
        self.global_ns = Namespace.objects.get_or_create(name="Global")[0]
        sor_cf_dict = {
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "key": "system_of_record",
            "label": "System of Record",
        }
        sor_custom_field, _ = CustomField.objects.update_or_create(key=sor_cf_dict["key"], defaults=sor_cf_dict)
        sync_cf_dict = {
            "type": CustomFieldTypeChoices.TYPE_DATE,
            "key": "last_synced_from_sor",
            "label": "Last sync from System of Record",
        }
        sync_custom_field, _ = CustomField.objects.update_or_create(key=sync_cf_dict["key"], defaults=sync_cf_dict)
        for model in [Device, Interface, IPAddress, Prefix]:
            sor_custom_field.content_types.add(ContentType.objects.get_for_model(model))
            sync_custom_field.content_types.add(ContentType.objects.get_for_model(model))
        for obj in [Controller, Device, Interface, Location, IPAddress, Prefix]:
            self.status_active.content_types.add(ContentType.objects.get_for_model(obj))
            self.offline_active.content_types.add(ContentType.objects.get_for_model(obj))
        self.area_loctype = LocationType.objects.get_or_create(name="Area", nestable=True)[0]
        self.building_loctype = LocationType.objects.get_or_create(name="Building", parent=self.area_loctype)[0]
        self.building_loctype.content_types.add(ContentType.objects.get_for_model(Device))
        self.building_loctype.content_types.add(ContentType.objects.get_for_model(Controller))
        self.floor_loctype = LocationType.objects.get_or_create(name="Floor", parent=self.building_loctype)[0]
        self.floor_loctype.content_types.add(ContentType.objects.get_for_model(Device))

        us_region = Location.objects.create(name="US", location_type=self.area_loctype, status=self.status_active)
        self.test_loc = Location.objects.create(
            name="HQ", location_type=self.building_loctype, parent=us_region, status=self.status_active
        )
        self.job = Job.objects.get(
            job_class_name="DnaCenterDataSource",
            module_name="nautobot_ssot.integrations.dna_center.jobs",
        )
        self.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="Fake task", user=None, id=uuid.uuid4()
        )
        test_user = Secret.objects.get_or_create(
            name="Test User", provider="environment-variable", parameters={"variable": "NB_TEST_ENV_USER"}
        )[0]
        test_pass = Secret.objects.get_or_create(
            name="Test Password", provider="environment-variable", parameters={"variable": "NB_TEST_ENV_PASS"}
        )[0]
        self.test_sg = SecretsGroup.objects.get_or_create(name="Test SG")[0]
        SecretsGroupAssociation.objects.get_or_create(
            secret=test_user,
            secrets_group=self.test_sg,
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        SecretsGroupAssociation.objects.get_or_create(
            secret=test_pass,
            secrets_group=self.test_sg,
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        self.ext_integration = ExternalIntegration.objects.get_or_create(
            name="Mock DNAC",
            defaults={"remote_url": "https://test_dnac.com", "secrets_group": self.test_sg, "verify_ssl": False},
        )[0]
        self.dnac = Controller.objects.get_or_create(
            name="Mock DNAC",
            external_integration=self.ext_integration,
            location=self.test_loc,
            status=self.status_active,
        )[0]
        self.cmdg = ControllerManagedDeviceGroup.objects.get_or_create(
            controller=self.dnac, defaults={"name": "Mock DNAC Managed Devices"}
        )[0]

    @patch.dict(os.environ, {"NB_TEST_ENV_USER": "testuser", "NB_TEST_ENV_PASS": "testpass"}, clear=True)
    @patch("nautobot_ssot.integrations.dna_center.jobs.verify_controller_managed_device_group")
    @patch("nautobot_ssot.integrations.dna_center.jobs.literal_eval")
    @patch("nautobot_ssot.integrations.dna_center.jobs.DnaCenterClient")
    def test_job_success(self, mock_client_instance, mock_eval, mock_verify):
        """Validate Job completes successfully."""
        mock_eval.return_value = {}
        mock_verify.return_value = self.cmdg
        mock_client = MagicMock()
        mock_client.get_locations.return_value = MULTI_LEVEL_LOCATION_FIXTURE
        mock_client.get_devices.return_value = DEVICE_FIXTURE
        mock_client.get_device_detail.side_effect = DEVICE_DETAIL_MULTI_LEVEL_FIXTURE
        mock_client.find_address_and_type.return_value = ("", "")
        mock_client.find_latitude_and_longitude.return_value = ("", "")
        mock_client.parse_site_hierarchy.side_effect = [
            {
                "areas": ["Global", "Americas", "US-AWS"],
                "building": "Wireless Controller",
                "floor": "Floor1",
            },
            {
                "areas": ["Global", "Americas", "UK-AWS"],
                "building": "Plant",
            },
            {
                "areas": ["Global", "Europe", "UK-Google"],
                "building": "Wireless Controller",
                "floor": "Floor1",
            },
        ]
        mock_client.get_model_name.return_value = "WS-C3850-24P-L"
        mock_client.get_port_info.side_effect = [PORT_FIXTURE, PORT_FIXTURE, PORT_FIXTURE]
        mock_client.get_port_type.return_value = "virtual"
        mock_client.get_port_status.return_value = "Active"
        mock_client_instance.return_value = mock_client
        result = run_job_for_testing(
            self.job,
            dnac=self.dnac.id,
            area_loctype=self.area_loctype.id,
            building_loctype=self.building_loctype.id,
            floor_loctype=self.floor_loctype.id,
            location_map={},
            hostname_map=[],
            bulk_import=False,
            debug=False,
            tenant=None,
            dryrun=False,
            memory_profiling=False,
        )
        log_entries = JobLogEntry.objects.filter(job_result=result)
        self.assertEqual(log_entries.filter(message__contains="location with this name already exists").count(), 0)
        mock_client_instance.assert_called_with(
            url="https://test_dnac.com", username="testuser", password="testpass", port=443, verify=False
        )
        created_locs = Location.objects.all()
        self.assertEqual(created_locs.count(), 12)
        mock_client.connect.assert_called()
        created_devs = Device.objects.all()
        self.assertEqual(created_devs.count(), 3)
