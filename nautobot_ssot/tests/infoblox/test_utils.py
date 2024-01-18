"""Util tests that do not require Django."""
import unittest

from django.test import TestCase

from nautobot.extras.models import Status
from nautobot.ipam.models import VLAN, VLANGroup

from nautobot_ssot.integrations.infoblox.utils.diffsync import (
    get_vlan_view_name,
    nautobot_vlan_status,
    get_ext_attr_dict,
)
from nautobot_ssot.integrations.infoblox.utils.nautobot import build_vlan_map_from_relations


class TestUtils(unittest.TestCase):
    """Test Utils."""

    def test_vlan_view_name(self):
        """Test vlan_view_name util."""
        name = get_vlan_view_name(
            "vlan/ZG5zLnZsYW4kLmNvbS5pbmZvYmxveC5kbnMudmxhbl92aWV3JFZMVmlldzEuMTAuMjAuMTA:VLView1/VL10/10"
        )
        self.assertEqual(name, "VLView1")

    def nautobot_vlan_status(self):
        """Test nautobot_vlan_status."""
        status = nautobot_vlan_status("Active")
        self.assertEqual(status, "ASSIGNED")

    def test_get_ext_attr_dict(self):
        """Test get_ext_attr_dict."""
        test_dict = {"Site": {"value": "HQ"}, "Region": {"value": "Central"}}
        expected = {"site": "HQ", "region": "Central"}
        standardized_dict = get_ext_attr_dict(test_dict)
        self.assertEqual(standardized_dict, expected)


class TestNautobotUtils(TestCase):
    """Test infoblox.utils.nautobot.py."""

    def setUp(self):
        """Setup Test Cases."""
        active_status = Status.objects.get(name="Active")
        self.vlan_group_1 = VLANGroup.objects.create(name="one")
        self.vlan_group_2 = VLANGroup.objects.create(name="two")
        self.vlan_10 = VLAN.objects.create(
            vid=10,
            name="ten",
            status=active_status,
            vlan_group=self.vlan_group_1,
        )
        self.vlan_20 = VLAN.objects.create(
            vid=20,
            name="twenty",
            status=active_status,
            vlan_group=self.vlan_group_1,
        )
        self.vlan_30 = VLAN.objects.create(
            vid=30,
            name="thirty",
            status=active_status,
            vlan_group=self.vlan_group_2,
        )
        self.vlan_40 = VLAN.objects.create(
            vid=40,
            name="forty",
            status=active_status,
        )

    def test_build_vlan_map_from_relations(self):
        """Test VLAN map is built correctly."""

        actual = build_vlan_map_from_relations([self.vlan_10, self.vlan_20, self.vlan_30, self.vlan_40])
        expected = {
            10: {
                "vid": 10,
                "name": "ten",
                "group": "one",
            },
            20: {
                "vid": 20,
                "name": "twenty",
                "group": "one",
            },
            30: {
                "vid": 30,
                "name": "thirty",
                "group": "two",
            },
            40: {
                "vid": 40,
                "name": "forty",
                "group": None,
            },
        }
        self.assertEqual(actual, expected)
