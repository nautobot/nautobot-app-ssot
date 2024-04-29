"""Test CloudVision Jobs."""

from django.test import override_settings
from django.urls import reverse
from nautobot.core.testing import TestCase

from nautobot_ssot.integrations.aristacv import jobs


class CloudVisionDataSourceJobTest(TestCase):
    """Test the CloudVision DataSource Job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("CloudVision ⟹ Nautobot", jobs.CloudVisionDataSource.name)
        self.assertEqual("CloudVision ⟹ Nautobot", jobs.CloudVisionDataSource.Meta.name)
        self.assertEqual("CloudVision", jobs.CloudVisionDataSource.data_source)
        self.assertEqual("Sync system tag data from CloudVision to Nautobot", jobs.CloudVisionDataSource.description)

    def test_data_mapping(self):  # pylint: disable=too-many-statements
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.CloudVisionDataSource.data_mappings()

        self.assertEqual("topology_network_type", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Topology Network Type", mappings[0].target_name)
        self.assertIsNone(mappings[0].target_url)

        self.assertEqual("mlag", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("MLAG", mappings[1].target_name)
        self.assertIsNone(mappings[1].target_url)

        self.assertEqual("mpls", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("mpls", mappings[2].target_name)
        self.assertIsNone(mappings[2].target_url)

        self.assertEqual("model", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("Device Type", mappings[3].target_name)
        self.assertEqual(reverse("dcim:devicetype_list"), mappings[3].target_url)

        self.assertEqual("systype", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("systype", mappings[4].target_name)
        self.assertIsNone(mappings[4].target_url)

        self.assertEqual("serialnumber", mappings[5].source_name)
        self.assertIsNone(mappings[5].source_url)
        self.assertEqual("Device Serial Number", mappings[5].target_name)
        self.assertIsNone(mappings[5].target_url)

        self.assertEqual("pimbidir", mappings[6].source_name)
        self.assertIsNone(mappings[6].source_url)
        self.assertEqual("pimbidir", mappings[6].target_name)
        self.assertIsNone(mappings[6].target_url)

        self.assertEqual("sflow", mappings[7].source_name)
        self.assertIsNone(mappings[7].source_url)
        self.assertEqual("sFlow", mappings[7].target_name)
        self.assertIsNone(mappings[7].target_url)

        self.assertEqual("eostrain", mappings[8].source_name)
        self.assertIsNone(mappings[8].source_url)
        self.assertEqual("eostrain", mappings[8].target_name)
        self.assertIsNone(mappings[8].target_url)

        self.assertEqual("tapagg", mappings[9].source_name)
        self.assertIsNone(mappings[9].source_url)
        self.assertEqual("tapagg", mappings[9].target_name)
        self.assertIsNone(mappings[9].target_url)

        self.assertEqual("pim", mappings[10].source_name)
        self.assertIsNone(mappings[10].source_url)
        self.assertEqual("pim", mappings[10].target_name)
        self.assertIsNone(mappings[10].target_url)

        self.assertEqual("bgp", mappings[11].source_name)
        self.assertIsNone(mappings[11].source_url)
        self.assertEqual("bgp", mappings[11].target_name)
        self.assertIsNone(mappings[11].target_url)

        self.assertEqual("terminattr", mappings[12].source_name)
        self.assertIsNone(mappings[12].source_url)
        self.assertEqual("TerminAttr Version", mappings[12].target_name)
        self.assertIsNone(mappings[12].target_url)

        self.assertEqual("ztp", mappings[13].source_name)
        self.assertIsNone(mappings[13].source_url)
        self.assertEqual("ztp", mappings[13].target_name)
        self.assertIsNone(mappings[13].target_url)

        self.assertEqual("eos", mappings[14].source_name)
        self.assertIsNone(mappings[14].source_url)
        self.assertEqual("EOS Version", mappings[14].target_name)
        self.assertIsNone(mappings[14].target_url)

        self.assertEqual("topology_type", mappings[15].source_name)
        self.assertIsNone(mappings[15].source_url)
        self.assertEqual("Topology Type", mappings[15].target_name)
        self.assertIsNone(mappings[15].target_url)

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvp_host": "https://localhost",
                "aristacv_cvp_user": "admin",
                "aristacv_verify": True,
                "aristacv_delete_devices_on_sync": True,
                "aristacv_from_cloudvision_default_site": "HQ",
                "aristacv_from_cloudvision_default_device_role": "Router",
                "aristacv_from_cloudvision_default_device_role_color": "ff0000",
                "aristacv_apply_import_tag": True,
                "aristacv_import_active": True,
            },
        },
    )
    def test_config_information_on_prem(self):
        """Verify the config_information() API for on-prem."""
        config_information = jobs.CloudVisionDataSource.config_information()

        self.assertEqual(config_information["Server Type"], "On prem")
        self.assertEqual(config_information["CloudVision URL"], "https://localhost:443")
        self.assertEqual(config_information["Verify SSL"], "True")
        self.assertEqual(config_information["User Name"], "admin")
        self.assertEqual(config_information["Delete Devices On Sync"], True)
        self.assertEqual(config_information["New Device Default Site"], "HQ")
        self.assertEqual(config_information["New Device Default Role"], "Router")
        self.assertEqual(config_information["New Device Default Role Color"], "ff0000")
        self.assertEqual(config_information["Apply Import Tag"], "True")
        self.assertEqual(config_information["Import Active"], "True")

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvaas_url": "https://www.arista.io",
                "aristacv_cvp_user": "admin",
            },
        },
    )
    def test_config_information_cvaas(self):
        """Verify the config_information() API for CVaaS."""
        config_information = jobs.CloudVisionDataSource.config_information()

        self.assertEqual(config_information["Server Type"], "CVaaS")
        self.assertEqual(config_information["CloudVision URL"], "https://www.arista.io:443")
        self.assertEqual(config_information["User Name"], "admin")


class CloudVisionDataTargetJobTest(TestCase):
    """Test the CloudVision DataTarget Job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Nautobot ⟹ CloudVision", jobs.CloudVisionDataTarget.name)
        self.assertEqual("Nautobot ⟹ CloudVision", jobs.CloudVisionDataTarget.Meta.name)
        self.assertEqual("Nautobot", jobs.CloudVisionDataTarget.data_source)
        self.assertEqual("Sync tag data from Nautobot to CloudVision", jobs.CloudVisionDataTarget.description)

    def test_data_mapping(self):  # pylint: disable=too-many-statements
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.CloudVisionDataTarget.data_mappings()

        self.assertEqual("Tags", mappings[0].source_name)
        self.assertEqual(reverse("extras:tag_list"), mappings[0].source_url)
        self.assertEqual("Device Tags", mappings[0].target_name)
        self.assertIsNone(mappings[0].target_url)
