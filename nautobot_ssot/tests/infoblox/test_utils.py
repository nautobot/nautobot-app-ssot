"""Util tests that do not require Django."""
import unittest

from nautobot_ssot_infoblox.utils.diffsync import get_vlan_view_name, nautobot_vlan_status, get_ext_attr_dict


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
