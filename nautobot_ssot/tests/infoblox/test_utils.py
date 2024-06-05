"""Util tests that do not require Django."""

import unittest
import unittest.mock

from django.test import TestCase
from nautobot.extras.models import Status
from nautobot.ipam.models import VLAN, VLANGroup

from nautobot_ssot.integrations.infoblox.utils.diffsync import (
    get_default_custom_fields,
    get_ext_attr_dict,
    get_valid_custom_fields,
    get_vlan_view_name,
    map_network_view_to_namespace,
    nautobot_vlan_status,
    validate_dns_name,
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

    def test_get_ext_attr_dict_slugify(self):
        """Test get_ext_attr_dict slugifies keys."""
        test_dict = {"Site-Loc": {"value": "NTC"}, "Region": {"value": "Central"}}
        expected = {"site_loc": "NTC", "region": "Central"}
        standardized_dict = get_ext_attr_dict(test_dict)
        self.assertEqual(standardized_dict, expected)

    def test_get_ext_attr_dict_exclusion_list(self):
        """Test get_ext_attr_dict correctly excludes attributes."""
        test_dict = {"Site": {"value": "HQ"}, "Region": {"value": "Central"}, "Tenant": {"value": "NTC"}}
        excluded_attrs = ["Tenant"]
        expected = {"site": "HQ", "region": "Central"}
        standardized_dict = get_ext_attr_dict(extattrs=test_dict, excluded_attrs=excluded_attrs)
        self.assertEqual(standardized_dict, expected)

    def test_validate_dns_name(self):
        """Test validate_dns_name."""
        client = unittest.mock.Mock()
        client.get_dns_view_for_network_view = unittest.mock.Mock(return_value="default.dev")
        client.get_authoritative_zones_for_dns_view = unittest.mock.Mock(
            return_value=[
                {
                    "fqdn": "nautobot.local.dev",
                },
                {
                    "fqdn": "nautobot.local.test",
                },
            ]
        )

        valid_name = "server1.nautobot.local.dev"
        invalid_name = "server1.nautobot.local.prod"

        self.assertEqual(False, validate_dns_name(client, invalid_name, "dev"))
        self.assertEqual(True, validate_dns_name(client, valid_name, "dev"))

    def test_map_network_view_to_namespace(self):
        """Test map_network_view_to_namespace."""
        network_view1 = "dev"
        network_view2 = "default"

        namespace1 = "test"
        namespace2 = "Global"

        self.assertEqual("dev", map_network_view_to_namespace(value=network_view1, direction="nv_to_ns"))
        self.assertEqual("Global", map_network_view_to_namespace(value=network_view2, direction="nv_to_ns"))
        self.assertEqual("test", map_network_view_to_namespace(value=namespace1, direction="ns_to_nv"))
        self.assertEqual("default", map_network_view_to_namespace(value=namespace2, direction="ns_to_nv"))

    def test_get_valid_custom_fields(self):
        """Test get_valid_custom_fields."""
        excluded_cfs = ["synced_to_snow"]

        cfs1 = {"ssot_synced_to_infoblox": True, "dhcp_ranges": [], "mac_address": "", "vlan": 100}
        cfs2 = {"tenant": "NTC", "synced_to_snow": True}

        expected1 = {"vlan": 100}
        expected2 = {"tenant": "NTC"}

        self.assertEqual(expected1, get_valid_custom_fields(cfs=cfs1))
        self.assertEqual(expected2, get_valid_custom_fields(cfs=cfs2, excluded_cfs=excluded_cfs))

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.utils.diffsync.CustomField",
        autospec=True,
    )
    def test_get_default_custom_fields(self, custom_field):
        """Test get_default_custom_fields."""
        content_type = unittest.mock.Mock()
        cf1 = unittest.mock.Mock()
        cf2 = unittest.mock.Mock()
        cf_def_excl1 = unittest.mock.Mock()
        cf_def_excl2 = unittest.mock.Mock()
        cf1.key = "tenant"
        cf2.key = "site"
        cf_def_excl1.key = "ssot_synced_to_infoblox"
        cf_def_excl2.key = "dhcp_ranges"

        custom_field.objects.filter.return_value = [cf1, cf2, cf_def_excl1, cf_def_excl2]

        expected = {"tenant": None, "site": None}

        result = get_default_custom_fields(cf_contenttype=content_type)
        self.assertEqual(expected, result)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.utils.diffsync.CustomField",
        autospec=True,
    )
    def test_get_default_custom_fields_excluded(self, custom_field):
        """Test get_default_custom_fields with excluded cfs."""
        content_type = unittest.mock.Mock()
        cf1 = unittest.mock.Mock()
        cf2 = unittest.mock.Mock()
        cf3 = unittest.mock.Mock()
        cf4 = unittest.mock.Mock()
        cf1.key = "tenant"
        cf2.key = "site"
        cf3.key = "snow_synced"
        cf4.key = "vlan"
        excluded_cfs = ["snow_synced", "vlan"]
        custom_field.objects.filter.return_value = [cf1, cf2, cf3, cf4]

        expected = {"tenant": None, "site": None}

        result = get_default_custom_fields(cf_contenttype=content_type, excluded_cfs=excluded_cfs)
        self.assertEqual(expected, result)


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
