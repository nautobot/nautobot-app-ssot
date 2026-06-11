"""Tests for the Cisco SD-WAN SSoT Job."""

from unittest.mock import patch

from django.conf import settings
from django.urls import reverse
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.exceptions import JobException
from nautobot_ssot.integrations.cisco_sdwan import jobs


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
