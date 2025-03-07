"""Test Cradlepoint Jobs."""

from copy import deepcopy

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from nautobot_ssot.integrations.cradlepoint import jobs

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
BACKUP_CONFIG = deepcopy(CONFIG)


class CradlepointJobTest(TestCase):
    """Test the Cradlepoint Sync job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Cradlepoint ⟹ Nautobot", jobs.CradlepointDataSource.Meta.name)
        self.assertEqual("Cradlepoint", jobs.CradlepointDataSource.Meta.data_source)
        self.assertEqual(
            "Sync data from Cradlepoint into Nautobot.",
            jobs.CradlepointDataSource.Meta.description,
        )

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.CradlepointDataSource.data_mappings()

        self.assertEqual("Router", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Device", mappings[0].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[0].target_url)
