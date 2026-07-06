"""Test Proxmox VE Jobs."""

from unittest.mock import MagicMock, patch

from django.urls import reverse
from nautobot.apps.testing import TestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.proxmox import jobs


def _mock_app_config(**overrides):
    """Build a MagicMock exposing the attributes _get_proxmox_client_config()/run() read."""
    app_config = MagicMock()
    app_config.proxmox_instance.remote_url = "https://pve.local:8006"
    app_config.proxmox_instance.verify_ssl = False
    app_config.proxmox_instance.secrets_group.get_secret_value.side_effect = ["token-id", "token-secret"]
    app_config.default_vm_status_map = {"running": "Active"}
    app_config.default_ip_status_map = {"PREFERRED": "Active"}
    app_config.primary_ip_sort_by = "Lowest"
    app_config.default_ignore_link_local = True
    app_config.use_clusters = True
    app_config.sync_lxc = True
    app_config.sync_nodes_as_devices = True
    app_config.sync_proxmox_tags = True
    app_config.enable_sync_to_nautobot = True
    for key, value in overrides.items():
        setattr(app_config, key, value)
    return app_config


class ProxmoxJobTest(TestCase):
    """Test the Proxmox VE job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Proxmox VE ⟹ Nautobot", jobs.ProxmoxDataSource.name)
        self.assertEqual("Proxmox VE ⟹ Nautobot", jobs.ProxmoxDataSource.Meta.name)
        self.assertEqual("Proxmox VE", jobs.ProxmoxDataSource.Meta.data_source)
        self.assertEqual(
            "Sync data from Proxmox VE into Nautobot.",
            jobs.ProxmoxDataSource.Meta.description,
        )

    def test_data_mappings(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.ProxmoxDataSource.data_mappings()

        expected = [
            ("Cluster", "ClusterGroup", reverse("virtualization:clustergroup_list")),
            ("Cluster", "Cluster", reverse("virtualization:cluster_list")),
            ("Node", "Device", reverse("dcim:device_list")),
            ("Node Interface", "Interface", reverse("dcim:interface_list")),
            ("Virtual Machine", "Virtual Machine", reverse("virtualization:virtualmachine_list")),
            ("VM Interface", "VMInterface", reverse("virtualization:vminterface_list")),
            ("IP Addresses", "IP Addresses", reverse("ipam:ipaddress_list")),
        ]
        self.assertEqual(len(mappings), len(expected))
        for mapping, (source_name, target_name, target_url) in zip(mappings, expected):
            self.assertEqual(mapping.source_name, source_name)
            self.assertIsNone(mapping.source_url)
            self.assertEqual(mapping.target_name, target_name)
            self.assertEqual(mapping.target_url, target_url)

    def test_get_proxmox_client_config(self):
        """_get_proxmox_client_config() builds a ProxmoxConfig from the SSOTProxmoxConfig instance."""
        app_config = _mock_app_config()
        client_config = jobs._get_proxmox_client_config(app_config, debug=True)  # pylint: disable=protected-access

        self.assertEqual(client_config.proxmox_uri, "https://pve.local:8006")
        self.assertEqual(client_config.token_id, "token-id")
        self.assertEqual(client_config.token_secret, "token-secret")
        self.assertFalse(client_config.verify_ssl)
        self.assertEqual(client_config.vm_status_map, {"running": "Active"})
        self.assertEqual(client_config.ip_status_map, {"PREFERRED": "Active"})
        self.assertEqual(client_config.primary_ip_sort_by, "Lowest")
        self.assertTrue(client_config.ignore_link_local)
        self.assertTrue(client_config.use_clusters)
        self.assertTrue(client_config.sync_lxc)
        self.assertTrue(client_config.sync_nodes_as_devices)
        self.assertTrue(client_config.sync_proxmox_tags)
        self.assertTrue(client_config.debug)

    def test_load_source_adapter_raises_on_auth_failure(self):
        """load_source_adapter() raises ValueError when the Proxmox client fails to authenticate."""
        job = jobs.ProxmoxDataSource()
        job.job_result = JobResult.objects.create(name="fake job", task_name="fake job", worker="default")
        job.config = _mock_app_config()
        job.debug = False
        job.cluster_filters = []

        with patch.object(jobs, "ProxmoxClient") as mock_client_cls:
            mock_client_cls.return_value.is_authenticated = False
            with self.assertRaises(ValueError) as ctx:
                job.load_source_adapter()
        self.assertEqual(str(ctx.exception), "Proxmox VE authentication failed.")

    def test_run_raises_when_sync_to_nautobot_disabled(self):
        """run() raises ValueError when the selected config has sync-to-Nautobot disabled."""
        job = jobs.ProxmoxDataSource()
        job.job_result = JobResult.objects.create(name="fake job", task_name="fake job", worker="default")
        config = _mock_app_config(enable_sync_to_nautobot=False)

        with self.assertRaises(ValueError) as ctx:
            job.run(debug=False, config=config, cluster_filters=[], dryrun=True)
        self.assertEqual(str(ctx.exception), "Config not enabled for sync to Nautobot.")
