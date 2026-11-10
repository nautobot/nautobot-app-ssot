"""Delete-path tests for the Proxmox VE DiffSync models (DB-backed)."""

from nautobot.apps.testing import TestCase
from nautobot.extras.models import Tag
from nautobot.virtualization.models import Cluster, VirtualMachine, VMInterface

from .proxmox_fixtures import (
    ProxmoxSyncTestMixin,
    _get_virtual_machine_dict,
    _get_vm_interface_dict,
)


class TestProxmoxDiffSyncModelsDelete(ProxmoxSyncTestMixin, TestCase):
    """Delete-path tests: objects absent from the source are removed from Nautobot."""

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

        # Re-sync without the VM.
        empty_source = self._source()
        self._seed_cluster(empty_source)
        empty_source.sync_to(self._nb_adapter())

        self.assertFalse(VirtualMachine.objects.filter(name="web01").exists())
        self.assertFalse(VMInterface.objects.filter(name="net0").exists())
        # Clusters use SKIP_UNMATCHED_DST, so they are preserved.
        self.assertTrue(Cluster.objects.filter(name="TestCluster").exists())

    def test_tag_model_not_deleted(self):
        """A Tag no longer present in the source is kept, since tags are shared."""
        source = self._source()
        self._seed_cluster(source)
        tag = source.tag(name="custom-tag", description="temp")
        source.add(tag)
        source.sync_to(self._nb_adapter())
        self.assertTrue(Tag.objects.filter(name="custom-tag").exists())

        empty_source = self._source()
        self._seed_cluster(empty_source)
        empty_source.sync_to(self._nb_adapter())
        self.assertTrue(Tag.objects.filter(name="custom-tag").exists())

    def test_virtual_machine_in_other_cluster_not_deleted(self):
        """A VM in a Cluster this sync does not read from is kept."""
        source = self._source()
        self._seed_cluster(source)
        other_cluster = source.cluster(
            name="OtherCluster", cluster_type__name="Proxmox VE", cluster_group__name="TestClusterGroup"
        )
        source.add(other_cluster)
        source.get("clustergroup", "TestClusterGroup").add_child(other_cluster)
        source.add(
            source.virtual_machine(**_get_virtual_machine_dict({"name": "other01", "cluster__name": "OtherCluster"}))
        )
        source.sync_to(self._nb_adapter())
        self.assertTrue(VirtualMachine.objects.filter(name="other01").exists())

        empty_source = self._source()
        self._seed_cluster(empty_source)
        empty_source.sync_to(self._nb_adapter(cluster_name="TestCluster"))
        self.assertTrue(VirtualMachine.objects.filter(name="other01").exists())

    def test_skipped_virtual_machine_not_deleted(self):
        """A VM the source adapter could not read is kept."""
        source = self._source()
        self._seed_cluster(source)
        source.add(source.virtual_machine(**_get_virtual_machine_dict({"name": "web01"})))
        source.sync_to(self._nb_adapter())

        empty_source = self._source()
        self._seed_cluster(empty_source)
        empty_source.sync_to(self._nb_adapter(cluster_name="TestCluster", skipped_vm_names={"web01"}))
        self.assertTrue(VirtualMachine.objects.filter(name="web01").exists())
