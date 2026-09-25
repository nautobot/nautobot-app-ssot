"""Shared setup for DB-backed Proxmox VE sync tests."""

from unittest.mock import MagicMock

from django.apps import apps as django_apps

from nautobot_ssot.integrations.proxmox.constants import SSOT_TAG_DESCRIPTION, SSOT_TAG_NAME
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_nautobot import NBAdapter
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_proxmox import ProxmoxDiffSync
from nautobot_ssot.integrations.proxmox.signals import nautobot_database_ready_callback

from .nautobot_fixtures import create_default_proxmox_config


class ProxmoxSyncTestMixin:
    """Create the integration's default objects and build source/target adapters."""

    def setUp(self):  # pylint: disable=invalid-name
        """Run the database-ready signal and create a default config."""
        super().setUp()
        nautobot_database_ready_callback(sender=None, apps=django_apps)
        self.config = create_default_proxmox_config()

    def _source(self):
        """Build an empty Proxmox source adapter with a mocked client.

        Returns:
            ProxmoxDiffSync: Adapter with nothing loaded.
        """
        return ProxmoxDiffSync(
            job=MagicMock(), sync=MagicMock(), client=MagicMock(), config=self.config, cluster_filters=None
        )

    def _nb_adapter(self):
        """Build a Nautobot adapter loaded from the current database state.

        Returns:
            NBAdapter: Loaded target adapter.
        """
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        return nb_adapter

    @staticmethod
    def _seed_cluster(source):
        """Add the SSoT tag, a ClusterGroup and a Cluster to the source adapter.

        Args:
            source (ProxmoxDiffSync): Adapter to populate.
        """
        source.add(source.tag(name=SSOT_TAG_NAME, description=SSOT_TAG_DESCRIPTION))
        clustergroup = source.clustergroup(name="TestClusterGroup")
        cluster = source.cluster(
            name="TestCluster", cluster_type__name="Proxmox VE", cluster_group__name="TestClusterGroup"
        )
        source.add(clustergroup)
        source.add(cluster)
        clustergroup.add_child(cluster)
