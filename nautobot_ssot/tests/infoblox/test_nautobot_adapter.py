"""Nautobot Adapter tests."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from nautobot.extras.models import RelationshipAssociation, Status
from nautobot.ipam.models import Namespace, Prefix, VLAN, VLANGroup

from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.tests.infoblox.fixtures_infoblox import create_default_infoblox_config, create_prefix_relationship


class TestNautobotAdapter(TestCase):
    """Test cases for InfoBlox Nautobot adapter."""

    def setUp(self):
        active_status = Status.objects.get(name="Active")
        prefix_vlan_relationship = create_prefix_relationship()
        vlan_group1 = VLANGroup.objects.create(name="one")
        vlan_group2 = VLANGroup.objects.create(name="two")
        vlan10 = VLAN.objects.create(
            vid=10,
            name="ten",
            status=active_status,
        )
        VLAN.objects.create(
            vid=20,
            name="twenty",
            status=active_status,
            vlan_group=vlan_group1,
        )
        VLAN.objects.create(
            vid=30,
            name="thirty",
            status=active_status,
            vlan_group=vlan_group1,
        )
        VLAN.objects.create(
            vid=40,
            name="forty",
            status=active_status,
            vlan_group=vlan_group2,
        )
        VLAN.objects.create(
            vid=50,
            name="fifty",
            status=active_status,
            vlan_group=vlan_group2,
        )
        namespace_dev, _ = Namespace.objects.get_or_create(name="dev")
        prefix1 = Prefix.objects.create(
            prefix="10.0.0.0/24",
            status=active_status,
            type="Network",
        )
        RelationshipAssociation.objects.create(
            relationship_id=prefix_vlan_relationship.id,
            source_type=ContentType.objects.get_for_model(Prefix),
            source_id=prefix1.id,
            destination_type=ContentType.objects.get_for_model(VLAN),
            destination_id=vlan10.id,
        )
        prefix1.cf["dhcp_ranges"] = "10.0.0.50-10.0.0.254"
        prefix1.save()
        Prefix.objects.create(
            prefix="10.0.1.0/24",
            status=active_status,
            type="Network",
        )
        Prefix.objects.create(
            prefix="10.0.1.0/24",
            status=active_status,
            type="Network",
            namespace=namespace_dev,
        )
        Prefix.objects.create(
            prefix="10.2.1.0/24",
            status=active_status,
            type="Network",
            namespace=namespace_dev,
        )
        self.config = create_default_infoblox_config()
        self.sync_filters = self.config.infoblox_sync_filters
        self.nb_adapter = NautobotAdapter(config=self.config)

    def test_load_vlans_loads_expected_vlans(self):
        self.nb_adapter.load_vlans()
        expected_vlans = {"20__twenty__one", "30__thirty__one", "40__forty__two", "50__fifty__two"}
        actual_vlans = {vlan.get_unique_id() for vlan in self.nb_adapter.get_all("vlan")}
        self.assertEqual(expected_vlans, actual_vlans)

    def test_load_vlans_does_not_load_ungrouped_vlans(self):
        self.nb_adapter.load_vlans()
        actual_vlan_ids = {vlan.get_identifiers()["vid"] for vlan in self.nb_adapter.get_all("vlan")}
        self.assertFalse(10 in actual_vlan_ids)

    def test_load_prefixes_loads_prefixes(self):
        self.nb_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=self.sync_filters)
        actual_prefixes = {(prefix.network, prefix.namespace) for prefix in self.nb_adapter.get_all("prefix")}
        self.assertEqual(actual_prefixes, {("10.0.0.0/24", "Global"), ("10.0.1.0/24", "Global")})

    def test_load_prefixes_loads_prefixes_dev_namespace(self):
        sync_filters = [{"network_view": "dev"}]
        self.nb_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_prefixes = {(prefix.network, prefix.namespace) for prefix in self.nb_adapter.get_all("prefix")}
        self.assertEqual(
            actual_prefixes,
            {("10.0.1.0/24", "dev"), ("10.2.1.0/24", "dev")},
        )

    def test_load_prefixes_loads_prefixes_dev_namespace_ipv4_filter(self):
        sync_filters = [{"network_view": "dev", "prefixes_ipv4": ["10.0.0.0/16"]}]
        self.nb_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_prefixes = {(prefix.network, prefix.namespace) for prefix in self.nb_adapter.get_all("prefix")}
        self.assertEqual(
            actual_prefixes,
            {
                ("10.0.1.0/24", "dev"),
            },
        )

    def test_load_prefixes_loads_prefixes_and_vlan_relationship(self):
        self.nb_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=self.sync_filters)
        prefix_with_vlan = self.nb_adapter.get("prefix", {"network": "10.0.0.0/24", "namespace": "Global"})
        self.assertEqual({10: {"vid": 10, "name": "ten", "group": None}}, prefix_with_vlan.vlans)

    def test_load_prefixes_loads_ranges(self):
        self.nb_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=self.sync_filters)
        prefix_with_ranges = self.nb_adapter.get("prefix", {"network": "10.0.0.0/24", "namespace": "Global"})
        self.assertEqual(["10.0.0.50-10.0.0.254"], prefix_with_ranges.ranges)
