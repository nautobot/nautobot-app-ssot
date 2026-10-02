"""Tests for the Cisco SD-WAN SSoT Job."""

import os
from unittest.mock import ANY, MagicMock, patch

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from nautobot.core.testing import TransactionTestCase, run_job_for_testing
from nautobot.dcim.models import (
    Controller,
    ControllerManagedDeviceGroup,
    Device,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    SoftwareVersion,
)
from nautobot.extras.choices import (
    JobResultStatusChoices,
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import (
    ExternalIntegration,
    JobResult,
    Role,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
    Status,
)
from nautobot.ipam.models import VRF, IPAddress, Namespace

from nautobot_ssot.exceptions import JobException
from nautobot_ssot.integrations.cisco_sdwan import jobs
from nautobot_ssot.tests.cisco_sdwan.fixtures import attach_interfaces, get_merged_devices
from nautobot_ssot.tests.utils.job_helpers import get_test_job_model


class CiscoSdwanDataSourceJobTest(TransactionTestCase):
    """Test the Cisco SD-WAN DataSource Job."""

    databases = ("default", "job_logs")

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Cisco SD-WAN to Nautobot", jobs.CiscoSdwanDataSource.name)
        self.assertEqual("Cisco SD-WAN to Nautobot", jobs.CiscoSdwanDataSource.Meta.name)
        self.assertEqual("Cisco SD-WAN", jobs.CiscoSdwanDataSource.data_source)
        self.assertEqual("Sync information from Cisco SD-WAN to Nautobot", jobs.CiscoSdwanDataSource.description)

    def test_data_mapping(self):
        """Verify correctness of the data_mappings."""
        mappings = jobs.CiscoSdwanDataSource.data_mappings()

        self.assertEqual("Device Models", mappings[0].source_name)
        self.assertEqual("DeviceTypes", mappings[0].target_name)
        self.assertEqual(reverse("dcim:devicetype_list"), mappings[0].target_url)

        self.assertEqual("Software Versions", mappings[1].source_name)
        self.assertEqual("SoftwareVersions", mappings[1].target_name)
        self.assertEqual(reverse("dcim:softwareversion_list"), mappings[1].target_url)

        self.assertEqual("Devices", mappings[2].source_name)
        self.assertEqual("Devices", mappings[2].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[2].target_url)

        self.assertEqual("Interfaces", mappings[3].source_name)
        self.assertEqual("Interfaces", mappings[3].target_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[3].target_url)

        self.assertEqual("Interface IPv4 Addresses", mappings[4].source_name)
        self.assertEqual("IP Addresses", mappings[4].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[4].target_url)

        self.assertEqual("VPNs", mappings[5].source_name)
        self.assertEqual("VRFs", mappings[5].target_name)
        self.assertEqual(reverse("ipam:vrf_list"), mappings[5].target_url)

    def test_config_information(self):
        """Verify the config_information() API."""
        config_information = jobs.CiscoSdwanDataSource.config_information()
        self.assertEqual(config_information["Instances"], "Found in Extensibility -> External Integrations menu.")
        self.assertIn("Device Retired Status", config_information)
        self.assertIn("Primary IP Interfaces", config_information)
        self.assertIn("Excluded Interfaces", config_information)
        self.assertIn("Excluded Prefixes", config_information)

    def _build_job(self):
        """Instantiate the Job with a JobResult for logging."""
        job = jobs.CiscoSdwanDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path)
        return job

    def test_validate_metadata_configuration_disabled(self):
        """Verify the Job fails with a clear error when metadata is not enabled."""
        job = self._build_job()
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"enable_metadata_for": []}):
            with self.assertRaises(JobException):
                job.validate_metadata_configuration()

    def test_validate_metadata_configuration_enabled(self):
        """Verify the Job validation passes when metadata is enabled."""
        job = self._build_job()
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"enable_metadata_for": ["CiscoSdwanDataSource"]}):
            job.validate_metadata_configuration()

    def _run_job(self, job, **overrides):
        """Call the Job run() method with mocked parameters, bypassing the base sync run."""
        parameters = {
            "dryrun": True,
            "memory_profiling": False,
            "debug": True,
            "controller": MagicMock(),
            "managed_device_group": MagicMock(),
            "device_status": MagicMock(),
            "devices": None,
            "device_role": MagicMock(),
            "device_platform": MagicMock(),
            "device_location": MagicMock(),
            "device_secrets_group": MagicMock(),
            "device_tenant": None,
            "namespace": None,
            "model_normalization": "^vedge-",
            "ignore_address_mask": True,
            "delete_replaced_ips": False,
        }
        parameters.update(overrides)
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"enable_metadata_for": ["CiscoSdwanDataSource"]}):
            with patch.object(jobs.DataSource, "run") as mock_super_run:
                job.run(**parameters)
        return mock_super_run

    def test_run_sets_job_parameters(self):
        """Verify run() stores the Job parameters and invokes the base data sync run."""
        job = self._build_job()
        mock_super_run = self._run_job(job)
        self.assertTrue(job.dryrun)
        self.assertTrue(job.debug)
        self.assertEqual(job.model_normalization, "^vedge-")
        self.assertFalse(job.delete_replaced_ips)
        mock_super_run.assert_called_once_with(dryrun=True, memory_profiling=False)

    def test_run_namespace_defaults_to_global(self):
        """Verify the Global Namespace is used when no Namespace is selected."""
        job = self._build_job()
        self._run_job(job, namespace=None)
        self.assertEqual(job.namespace, Namespace.objects.get(name="Global"))

    def test_run_namespace_honored(self):
        """Verify a selected Namespace is used as-is."""
        namespace = Namespace.objects.create(name="SDWAN")
        job = self._build_job()
        self._run_job(job, namespace=namespace)
        self.assertEqual(job.namespace, namespace)

    def test_run_requires_metadata(self):
        """Verify run() fails when the metadata feature is not enabled for the Job."""
        job = self._build_job()
        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"enable_metadata_for": []}):
            with patch.object(jobs.DataSource, "run") as mock_super_run:
                with self.assertRaises(JobException):
                    job.run(
                        dryrun=True,
                        memory_profiling=False,
                        debug=False,
                        controller=MagicMock(),
                        managed_device_group=MagicMock(),
                        device_status=MagicMock(),
                        devices=None,
                        device_role=MagicMock(),
                        device_platform=MagicMock(),
                        device_location=MagicMock(),
                        device_secrets_group=MagicMock(),
                        device_tenant=None,
                        namespace=None,
                        model_normalization="",
                        ignore_address_mask=True,
                        delete_replaced_ips=False,
                    )
        mock_super_run.assert_not_called()


class CiscoSdwanJobRunTest(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Validate the Job completes successfully end to end with a mocked SD-WAN Manager."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Create the Nautobot objects required to run the Job."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        Status.objects.get_or_create(name="Retired")
        for model in [Controller, Device, Interface, SoftwareVersion]:
            self.status_active.content_types.add(ContentType.objects.get_for_model(model))

        location_type = LocationType.objects.get_or_create(name="Site")[0]
        location_type.content_types.add(ContentType.objects.get_for_model(Device))
        location_type.content_types.add(ContentType.objects.get_for_model(Controller))
        self.location = Location.objects.create(name="Staging", location_type=location_type, status=self.status_active)

        manufacturer = Manufacturer.objects.get_or_create(name="Cisco")[0]
        self.platform = Platform.objects.get_or_create(name="cisco_ios", manufacturer=manufacturer)[0]
        self.device_role = Role.objects.get_or_create(name="Router")[0]
        self.device_role.content_types.add(ContentType.objects.get_for_model(Device))

        test_user = Secret.objects.get_or_create(
            name="Test User", provider="environment-variable", parameters={"variable": "NB_TEST_ENV_USER"}
        )[0]
        test_pass = Secret.objects.get_or_create(
            name="Test Password", provider="environment-variable", parameters={"variable": "NB_TEST_ENV_PASS"}
        )[0]
        self.secrets_group = SecretsGroup.objects.get_or_create(name="SD-WAN Credentials")[0]
        SecretsGroupAssociation.objects.get_or_create(
            secret=test_user,
            secrets_group=self.secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        SecretsGroupAssociation.objects.get_or_create(
            secret=test_pass,
            secrets_group=self.secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        external_integration = ExternalIntegration.objects.get_or_create(
            name="SD-WAN Manager",
            defaults={
                "remote_url": "https://vmanage.example.com",
                "secrets_group": self.secrets_group,
                "verify_ssl": False,
            },
        )[0]
        self.controller = Controller.objects.create(
            name="SD-WAN Manager",
            external_integration=external_integration,
            location=self.location,
            status=self.status_active,
        )
        self.managed_device_group = ControllerManagedDeviceGroup.objects.create(
            name="SD-WAN Managed Devices", controller=self.controller
        )
        self.job_model = get_test_job_model(jobs.CiscoSdwanDataSource)

    @patch.dict(os.environ, {"NB_TEST_ENV_USER": "testuser", "NB_TEST_ENV_PASS": "testpass"}, clear=False)
    @patch("nautobot_ssot.integrations.cisco_sdwan.diffsync.adapters.cisco_sdwan.CiscoSdwanManager")
    def test_job_success(self, mock_manager_class):
        """Validate the Job creates the SD-WAN inventory in Nautobot."""
        sdwan_manager = MagicMock()
        sdwan_manager.get_devices.return_value = get_merged_devices()
        sdwan_manager.get_interfaces.side_effect = attach_interfaces
        mock_manager_class.return_value = sdwan_manager

        with patch.dict(settings.PLUGINS_CONFIG["nautobot_ssot"], {"enable_metadata_for": ["CiscoSdwanDataSource"]}):
            job_result = run_job_for_testing(
                self.job_model,
                dryrun=False,
                memory_profiling=False,
                debug=False,
                controller=self.controller.id,
                managed_device_group=self.managed_device_group.id,
                devices=[],
                device_status=self.status_active.id,
                device_role=self.device_role.id,
                device_platform=self.platform.id,
                device_location=self.location.id,
                device_secrets_group=self.secrets_group.id,
                device_tenant=None,
                namespace=None,
                model_normalization="^vedge-",
                ignore_address_mask=True,
                delete_replaced_ips=False,
            )

        self.assertEqual(job_result.status, JobResultStatusChoices.STATUS_SUCCESS)
        mock_manager_class.assert_called_once_with(
            job=ANY,
            username="testuser",
            password="testpass",  # noqa: S106
            verify=False,
            base_url="https://vmanage.example.com",
        )
        self.assertEqual(
            set(Device.objects.values_list("name", flat=True)),
            {"sdwan-edge-01", "sdwan-edge-02", "vmanage-01"},
        )
        device = Device.objects.get(name="sdwan-edge-01")
        self.assertEqual(device.controller_managed_device_group, self.managed_device_group)
        self.assertEqual(device.software_version.version, "17.06.03a")
        self.assertTrue(Interface.objects.filter(device=device, name="GigabitEthernet1").exists())
        self.assertTrue(IPAddress.objects.filter(host="192.0.2.10").exists())
        self.assertTrue(VRF.objects.filter(name="10").exists())
