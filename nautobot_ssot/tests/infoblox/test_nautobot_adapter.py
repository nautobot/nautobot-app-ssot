"""Nautobot Adapter tests."""
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from nautobot.extras.models import Relationship, RelationshipAssociation, Status
from nautobot.ipam.models import Prefix, VLAN, VLANGroup

from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter


class TestNautobotAdapter(TestCase):
    """Test cases for InfoBlox Nautobot adapter."""

    def setUp(self):
        active_status = Status.objects.get(name="Active")
        prefix_vlan_relationship = Relationship.objects.get(label="Prefix -> VLAN")
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
        self.nb_adapter = NautobotAdapter()

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
        self.nb_adapter.load_prefixes()
        actual_prefixes = {prefix.network for prefix in self.nb_adapter.get_all("prefix")}
        self.assertEqual(actual_prefixes, {"10.0.0.0/24", "10.0.1.0/24"})

    def test_load_prefixes_loads_prefixes_and_vlan_relationship(self):
        self.nb_adapter.load_prefixes()
        prefix_with_vlan = self.nb_adapter.get("prefix", {"network": "10.0.0.0/24"})
        self.assertEqual({10: {"vid": 10, "name": "ten", "group": None}}, prefix_with_vlan.vlans)

    def test_load_prefixes_loads_ranges(self):
        self.nb_adapter.load_prefixes()
        prefix_with_ranges = self.nb_adapter.get("prefix", {"network": "10.0.0.0/24"})
        self.assertEqual(["10.0.0.50-10.0.0.254"], prefix_with_ranges.ranges)
