"""Test IPFabric Jobs."""

from copy import deepcopy
from unittest import mock

from django.conf import settings
from django.urls import reverse
from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.ipfabric import jobs

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
BACKUP_CONFIG = deepcopy(CONFIG)


class IPFabricJobTest(TestCase):
    """Test the IPFabric job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("IPFabric ⟹ Nautobot", jobs.IpFabricDataSource.name)
        self.assertEqual("IPFabric ⟹ Nautobot", jobs.IpFabricDataSource.Meta.name)
        self.assertEqual("IP Fabric", jobs.IpFabricDataSource.Meta.data_source)
        self.assertEqual("Sync data from IP Fabric into Nautobot.", jobs.IpFabricDataSource.Meta.description)

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.IpFabricDataSource.data_mappings()

        self.assertEqual("Device", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Device", mappings[0].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[0].target_url)

        self.assertEqual("Location", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Location", mappings[1].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[1].target_url)

        self.assertEqual("Interfaces", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Interfaces", mappings[2].target_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[2].target_url)

        self.assertEqual("IP Addresses", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("IP Addresses", mappings[3].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[3].target_url)

        self.assertEqual("VLANs", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("VLANs", mappings[4].target_name)
        self.assertEqual(reverse("ipam:vlan_list"), mappings[4].target_url)

        self.assertEqual("Connectivity Matrix", mappings[5].source_name)
        self.assertIsNone(mappings[5].source_url)
        self.assertEqual("Cables", mappings[5].target_name)
        self.assertEqual(reverse("dcim:cable_list"), mappings[5].target_url)

    # @override_settings(
    #     PLUGINS_CONFIG={
    #         "nautobot_ssot": {
    #             "IPFABRIC_HOST": "https://ipfabric.networktocode.com",
    #             "IPFABRIC_API_TOKEN": "1234",
    #         }
    #     }
    # )
    # def test_config_information(self):
    #     """Verify the config_information() API."""
    #     CONFIG["ipfabric_host"] = "https://ipfabric.networktocode.com"
    #     config_information = jobs.IpFabricDataSource.config_information()
    #     self.assertContains(
    #         config_information,
    #         {
    #             "IP Fabric host": "https://ipfabric.networktocode.com",
    #         },
    #     )
    #     # CLEANUP
    #     CONFIG["ipfabric_host"] = BACKUP_CONFIG["ipfabric_host"]


class IPFabricSyncDataTest(TestCase):
    """Test that `sync_data` threads its job options through to both adapters."""

    def _job(self, **overrides):
        """Return a job instance with mocked client, sync and logger."""
        job = jobs.IpFabricDataSource()
        job.client = mock.MagicMock()
        job.sync = mock.MagicMock()
        job.logger = mock.MagicMock()
        job.kwargs = {
            "snapshot": "$last",
            "dryrun": True,
            "safe_delete_mode": True,
            "sync_ipfabric_tagged_only": True,
            "sync_cables": False,
            "location_filter": None,
            "debug": False,
            **overrides,
        }
        return job

    def test_sync_data_passes_sync_cables_to_both_adapters(self):
        """`sync_cables` reaches the IP Fabric and Nautobot adapters alike."""
        job = self._job(sync_cables=True)

        with (
            mock.patch("nautobot_ssot.integrations.ipfabric.jobs.IPFabricDiffSync") as mock_source,
            mock.patch("nautobot_ssot.integrations.ipfabric.jobs.NautobotDiffSync") as mock_dest,
        ):
            job.sync_data()

        self.assertTrue(mock_source.call_args.kwargs["sync_cables"])
        self.assertTrue(mock_dest.call_args.kwargs["sync_cables"])
        self.assertTrue(any("`Sync Cables`: True" in str(c) for c in job.logger.info.call_args_list))

    def test_sync_data_defaults_sync_cables_off(self):
        """With the option unset, neither adapter loads Cables."""
        job = self._job()

        with (
            mock.patch("nautobot_ssot.integrations.ipfabric.jobs.IPFabricDiffSync") as mock_source,
            mock.patch("nautobot_ssot.integrations.ipfabric.jobs.NautobotDiffSync") as mock_dest,
        ):
            job.sync_data()

        self.assertFalse(mock_source.call_args.kwargs["sync_cables"])
        self.assertFalse(mock_dest.call_args.kwargs["sync_cables"])

    def test_sync_data_errors_without_a_client(self):
        """No client means the job reports and returns rather than proceeding."""
        job = self._job()
        job.client = None

        with mock.patch.object(jobs.IpFabricDataSource, "_init_ipf_client", return_value=None):
            job.sync_data()

        job.logger.error.assert_called_once()
