"""Test Slurpit Jobs."""

from copy import deepcopy

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from nautobot_ssot.integrations.slurpit import jobs

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
BACKUP_CONFIG = deepcopy(CONFIG)


class SlurpitJobTest(TestCase):
    """Test the Slurpit job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        meta = jobs.SlurpitDataSource.Meta
        self.assertEqual("Slurpit Data Source", jobs.SlurpitDataSource.name)
        self.assertEqual("Slurpit Data Source", meta.name)
        self.assertEqual("Slurpit", meta.data_source)
        self.assertEqual("Sync information from Slurpit to Nautobot.", meta.description)

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.SlurpitDataSource.data_mappings()
        expected_mappings = [
            ("Site", None, "Location", reverse("dcim:location_list")),
            ("Manufacturer", None, "Manufacturer", reverse("dcim:manufacturer_list")),
            ("Device Type", None, "Device Type", reverse("dcim:devicetype_list")),
            ("Platform", None, "Platform", reverse("dcim:platform_list")),
        ]

        for i, (source_name, source_url, target_name, target_url) in enumerate(expected_mappings):
            self.assertEqual(source_name, mappings[i].source_name)
            self.assertIsNone(source_url)
            self.assertEqual(target_name, mappings[i].target_name)
            self.assertEqual(target_url, mappings[i].target_url)
