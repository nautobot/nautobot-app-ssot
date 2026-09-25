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
