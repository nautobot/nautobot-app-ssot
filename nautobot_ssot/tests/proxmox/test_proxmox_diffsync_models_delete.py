# pylint: disable=R0801
"""Delete-path tests for the Proxmox VE DiffSync models (DB-backed)."""

from unittest.mock import MagicMock

from django.apps import apps as django_apps
from nautobot.apps.testing import TestCase
from nautobot.extras.models import Tag
from nautobot.virtualization.models import Cluster, VirtualMachine, VMInterface

from nautobot_ssot.integrations.proxmox.constants import SSOT_TAG_DESCRIPTION, SSOT_TAG_NAME
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_nautobot import NBAdapter
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_proxmox import ProxmoxDiffSync
from nautobot_ssot.integrations.proxmox.signals import nautobot_database_ready_callback

from .proxmox_fixtures import _get_virtual_machine_dict, _get_vm_interface_dict, create_default_proxmox_config


class TestProxmoxDiffSyncModelsDelete(TestCase):
    """Delete-path tests: objects absent from the source are removed from Nautobot."""

    def setUp(self):
        """Build scaffolding + config."""
        nautobot_database_ready_callback(sender=None, apps=django_apps)
        self.config = create_default_proxmox_config()

    def _source(self):
        return ProxmoxDiffSync(
            job=MagicMock(), sync=MagicMock(), client=MagicMock(), config=self.config, cluster_filters=None
        )

    def _nb_adapter(self):
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        return nb_adapter

    def _seed_cluster(self, source):
        source.add(source.tag(name=SSOT_TAG_NAME, description=SSOT_TAG_DESCRIPTION))
        clustergroup = source.clustergroup(name="TestClusterGroup")
        cluster = source.cluster(
            name="TestCluster", cluster_type__name="Proxmox VE", cluster_group__name="TestClusterGroup"
        )
        source.add(clustergroup)
        source.add(cluster)
        clustergroup.add_child(cluster)

    def test_virtual_machine_delete(self):
        """A VM no longer present in the source is deleted; the cluster is preserved."""
        source = self._source()
        self._seed_cluster(source)
        vm = source.virtual_machine(**_get_virtual_machine_dict({"name": "web01"}))
        interface = source.interface(**_get_vm_interface_dict({"name": "net0", "virtual_machine__name": "web01"}))
        source.add(vm)
        source.add(interface)
        vm.add_child(interface)
        source.sync_to(self._nb_adapter())
        self.assertTrue(VirtualMachine.objects.filter(name="web01").exists())

        # Re-sync from a source that only has the cluster (no VM) -> VM is deleted.
        empty_source = self._source()
        self._seed_cluster(empty_source)
        empty_source.sync_to(self._nb_adapter())

        self.assertFalse(VirtualMachine.objects.filter(name="web01").exists())
        self.assertFalse(VMInterface.objects.filter(name="net0").exists())
        # Clusters use SKIP_UNMATCHED_DST, so they are preserved.
        self.assertTrue(Cluster.objects.filter(name="TestCluster").exists())

    def test_tag_model_delete(self):
        """A Tag no longer present in the source is deleted."""
        source = self._source()
        self._seed_cluster(source)
        tag = source.tag(name="custom-tag", description="temp")
        source.add(tag)
        source.sync_to(self._nb_adapter())
        self.assertTrue(Tag.objects.filter(name="custom-tag").exists())

        empty_source = self._source()
        self._seed_cluster(empty_source)
        empty_source.sync_to(self._nb_adapter())
        self.assertFalse(Tag.objects.filter(name="custom-tag").exists())
