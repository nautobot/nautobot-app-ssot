"""Update-path tests for the Proxmox VE DiffSync models (DB-backed)."""

from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, Interface, Location, LocationType
from nautobot.extras.models import Status, Tag
from nautobot.virtualization.models import VirtualMachine

from nautobot_ssot.integrations.proxmox.constants import SSOT_TAG_NAME

from .proxmox_fixtures import (
    ProxmoxSyncTestMixin,
    _get_device_interface_dict,
    _get_node_device_dict,
    _get_virtual_machine_dict,
    _get_vm_interface_dict,
)


class TestProxmoxDiffSyncModelsUpdate(ProxmoxSyncTestMixin, TestCase):
    """Update-path tests: sync, then re-sync changed source models and assert ORM updates."""

    def test_virtual_machine_update(self):
        """Changing a VM's resources updates the Nautobot VirtualMachine."""
        source = self._source()
        self._seed_cluster(source)
        source.add(source.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "memory": 4096})))
        source.sync_to(self._nb_adapter())
        self.assertEqual(VirtualMachine.objects.get(name="web01").memory, 4096)

        source2 = self._source()
        self._seed_cluster(source2)
        source2.add(source2.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "memory": 8192})))
        source2.sync_to(self._nb_adapter())

        self.assertEqual(VirtualMachine.objects.get(name="web01").memory, 8192)

    def test_device_interface_update(self):
        """Changing a node interface's MTU updates the Nautobot Interface."""
        source = self._source()
        self._seed_cluster(source)
        device = source.device(**_get_node_device_dict({"name": "pve1"}))
        interface = source.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "mtu": 1500})
        )
        source.add(device)
        source.add(interface)
        device.add_child(interface)
        source.sync_to(self._nb_adapter())
        self.assertEqual(Interface.objects.get(device__name="pve1", name="eth0").mtu, 1500)

        source2 = self._source()
        self._seed_cluster(source2)
        device2 = source2.device(**_get_node_device_dict({"name": "pve1"}))
        interface2 = source2.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "mtu": 9000})
        )
        source2.add(device2)
        source2.add(interface2)
        device2.add_child(interface2)
        source2.sync_to(self._nb_adapter())

        self.assertEqual(Interface.objects.get(device__name="pve1", name="eth0").mtu, 9000)
        self.assertIn(SSOT_TAG_NAME, [tag.name for tag in Interface.objects.get(name="eth0").device.tags.all()])

    def test_update_virtual_machine_primary_ip(self):
        """Changing a VM's primary IPv4 to a different existing IP updates the Nautobot VirtualMachine."""
        source = self._source()
        self._seed_cluster(source)
        vm = source.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "primary_ip4__host": "10.0.10.50"}))
        interface = source.interface(**_get_vm_interface_dict({"name": "net0", "virtual_machine__name": "web01"}))
        ip_address = source.ip_address(
            host="10.0.10.50",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "net0", "virtual_machine__name": "web01"}],
            interfaces=[],
        )
        prefix = source.prefix(
            network="10.0.10.0", prefix_length=24, namespace__name="Global", status__name="Active", type="network"
        )
        for item in (vm, interface, ip_address, prefix):
            source.add(item)
        vm.add_child(interface)
        source.sync_to(self._nb_adapter())
        self.assertEqual(VirtualMachine.objects.get(name="web01").primary_ip.host, "10.0.10.50")

        source2 = self._source()
        self._seed_cluster(source2)
        vm2 = source2.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "primary_ip4__host": "10.0.10.51"}))
        interface2 = source2.interface(**_get_vm_interface_dict({"name": "net0", "virtual_machine__name": "web01"}))
        ip_address2 = source2.ip_address(
            host="10.0.10.51",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "net0", "virtual_machine__name": "web01"}],
            interfaces=[],
        )
        prefix2 = source2.prefix(
            network="10.0.10.0", prefix_length=24, namespace__name="Global", status__name="Active", type="network"
        )
        for item in (vm2, interface2, ip_address2, prefix2):
            source2.add(item)
        vm2.add_child(interface2)
        source2.sync_to(self._nb_adapter())

        self.assertEqual(VirtualMachine.objects.get(name="web01").primary_ip.host, "10.0.10.51")

    def test_update_device_interface_link(self):
        """Adding a bridge relationship on re-sync links the two existing node Interfaces."""
        source = self._source()
        self._seed_cluster(source)
        device = source.device(**_get_node_device_dict({"name": "pve1"}))
        eth0 = source.device_interface(**_get_device_interface_dict({"name": "eth0", "device__name": "pve1"}))
        vmbr0 = source.device_interface(
            **_get_device_interface_dict({"name": "vmbr0", "device__name": "pve1", "type": "bridge"})
        )
        source.add(device)
        source.add(eth0)
        source.add(vmbr0)
        device.add_child(eth0)
        device.add_child(vmbr0)
        source.sync_to(self._nb_adapter())
        self.assertIsNone(Interface.objects.get(device__name="pve1", name="eth0").bridge)

        source2 = self._source()
        self._seed_cluster(source2)
        device2 = source2.device(**_get_node_device_dict({"name": "pve1"}))
        eth0_2 = source2.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "bridge__name": "vmbr0"})
        )
        vmbr0_2 = source2.device_interface(
            **_get_device_interface_dict({"name": "vmbr0", "device__name": "pve1", "type": "bridge"})
        )
        source2.add(device2)
        source2.add(eth0_2)
        source2.add(vmbr0_2)
        device2.add_child(eth0_2)
        device2.add_child(vmbr0_2)
        source2.sync_to(self._nb_adapter())

        updated_eth0 = Interface.objects.get(device__name="pve1", name="eth0")
        self.assertEqual(updated_eth0.bridge.name, "vmbr0")

    def test_update_virtual_machine_primary_ip_removed(self):
        """Removing the primary IPv4 while changing the primary IPv6 clears the IPv4 and sets the new IPv6."""

        def build(source, ip4, ip6):
            self._seed_cluster(source)
            vm = source.virtual_machine(
                **_get_virtual_machine_dict({"name": "web01", "primary_ip4__host": ip4, "primary_ip6__host": ip6})
            )
            interface = source.interface(**_get_vm_interface_dict({"name": "net0", "virtual_machine__name": "web01"}))
            source.add(vm)
            source.add(interface)
            vm.add_child(interface)
            assigned = [{"name": "net0", "virtual_machine__name": "web01"}]
            for host, mask, network in ((ip4, 24, "10.0.10.0"), (ip6, 64, "2001:db8::")):
                if host is None:
                    continue
                source.add(
                    source.ip_address(
                        host=host, mask_length=mask, status__name="Active", vm_interfaces=assigned, interfaces=[]
                    )
                )
                source.add(
                    source.prefix(
                        network=network,
                        prefix_length=mask,
                        namespace__name="Global",
                        status__name="Active",
                        type="network",
                    )
                )

        source = self._source()
        build(source, ip4="10.0.10.50", ip6="2001:db8::50")
        source.sync_to(self._nb_adapter())
        vm = VirtualMachine.objects.get(name="web01")
        self.assertEqual(vm.primary_ip4.host, "10.0.10.50")
        self.assertEqual(vm.primary_ip6.host, "2001:db8::50")

        source2 = self._source()
        build(source2, ip4=None, ip6="2001:db8::51")
        source2.sync_to(self._nb_adapter())

        vm = VirtualMachine.objects.get(name="web01")
        self.assertIsNone(vm.primary_ip4)
        self.assertEqual(vm.primary_ip6.host, "2001:db8::51")

    def test_update_device_interface_link_keeps_other_links(self):
        """Removing one link on re-sync leaves the interface's other links in place."""

        def build(source, bridge):
            self._seed_cluster(source)
            device = source.device(**_get_node_device_dict({"name": "pve1"}))
            source.add(device)
            for attrs in (
                {"name": "eth0"},
                {"name": "vmbr0", "type": "bridge"},
                {"name": "eth0.10", "type": "virtual", "parent_interface__name": "eth0", "bridge__name": bridge},
            ):
                interface = source.device_interface(**_get_device_interface_dict({"device__name": "pve1", **attrs}))
                source.add(interface)
                device.add_child(interface)

        source = self._source()
        build(source, bridge="vmbr0")
        source.sync_to(self._nb_adapter())
        vlan = Interface.objects.get(device__name="pve1", name="eth0.10")
        self.assertEqual(vlan.bridge.name, "vmbr0")
        self.assertEqual(vlan.parent_interface.name, "eth0")

        source2 = self._source()
        build(source2, bridge=None)
        source2.sync_to(self._nb_adapter())
        vlan = Interface.objects.get(device__name="pve1", name="eth0.10")
        self.assertIsNone(vlan.bridge)
        self.assertEqual(vlan.parent_interface.name, "eth0")

    def test_device_uses_config_location_when_name_is_shared(self):
        """The node Device gets the config's Location even when another Location has the same name."""
        active = Status.objects.get(name="Active")
        region_type = LocationType.objects.create(name="Test Region")
        site_type = LocationType.objects.create(name="Test Site", parent=region_type)
        region = Location.objects.create(name="Test Region 1", location_type=region_type, status=active)
        Location.objects.create(
            name=self.config.default_location.name, location_type=site_type, parent=region, status=active
        )

        source = self._source()
        self._seed_cluster(source)
        source.add(source.device(**_get_node_device_dict({"name": "pve1"})))
        source.sync_to(self._nb_adapter())

        self.assertEqual(Device.objects.get(name="pve1").location, self.config.default_location)

    def test_tag_model_update(self):
        """Changing a Tag's description on re-sync updates the Nautobot Tag."""
        source = self._source()
        self._seed_cluster(source)
        tag = source.tag(name="custom-tag", description="v1")
        source.add(tag)
        source.sync_to(self._nb_adapter())
        self.assertEqual(Tag.objects.get(name="custom-tag").description, "v1")

        source2 = self._source()
        self._seed_cluster(source2)
        tag2 = source2.tag(name="custom-tag", description="v2")
        source2.add(tag2)
        source2.sync_to(self._nb_adapter())
        self.assertEqual(Tag.objects.get(name="custom-tag").description, "v2")
