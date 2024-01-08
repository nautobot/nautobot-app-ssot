"""Nautobot Adapter tests."""
from django.test import TestCase

from nautobot.extras.models import Status
from nautobot.ipam.models import VLAN, VLANGroup

from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter


class TestNautobotAdapter(TestCase):
    """Test cases for InfoBlox Nautobot adapter."""

    def setUp(self):
        active_status = Status.objects.get(name="Active")
        vlan_group1 = VLANGroup.objects.create(name="one")
        vlan_group2 = VLANGroup.objects.create(name="two")
        VLAN.objects.create(
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
