"""Unit tests for the Infoblox DiffSync adapter class."""

import unittest

from nautobot_ssot.integrations.infoblox.choices import FixedAddressTypeChoices
from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter

from .fixtures_infoblox import create_default_infoblox_config


class TestInfobloxAdapter(unittest.TestCase):
    """Test cases for InfobloxAdapter."""

    def setUp(self):
        self.config = create_default_infoblox_config()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.infoblox_adapter = InfobloxAdapter(
                job=unittest.mock.Mock(),
                sync=unittest.mock.Mock(),
                conn=mock_client,
                config=self.config,
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={"attr1": "data"},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}, {"attr2": "value"}, {}],
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.build_vlan_map",
        autospec=True,
        side_effect=[{10: {"vid": 10, "name": "ten", "group": "group_a"}}],
    )
    def test_load_prefixes_no_infoblox_import_subnets(
        self,
        mock_build_vlan_map,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        self.infoblox_adapter.conn.get_network_containers.return_value = [
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:10.0.0.0/8/default",
                "comment": "root",
                "extattrs": {},
                "network": "10.0.0.0/8",
                "network_view": "default",
                "rir": "NONE",
            },
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:10.0.0.0/16/default",
                "comment": "",
                "extattrs": {},
                "network": "10.0.0.0/16",
                "network_view": "default",
                "rir": "NONE",
            },
        ]
        self.infoblox_adapter.conn.get_all_subnets.return_value = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.0.0.0/23/default",
                "extattrs": {"attr2": "value"},  # this is mocked out, but also present for clearer reading
                "network": "10.0.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [10],
                "ranges": ["10.0.0.150-10.0.0.254", "10.0.1.150-10.0.1.254"],
            },
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIwLjY0LjAvMjEvMA:10.0.100.0/24/default",
                "extattrs": {},
                "network": "10.0.100.0/24",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
                "ranges": [],
            },
        ]
        sync_filters = [{"network_view": "default"}]
        self.infoblox_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        self.infoblox_adapter.conn.get_tree_from_container.assert_not_called()
        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 4)
        mock_build_vlan_map.assert_called_once()
        self.assertEqual(len(self.infoblox_adapter.get_all("prefix")), 4)
        self.infoblox_adapter.conn.get_network_containers.assert_has_calls([unittest.mock.call(network_view="default")])
        self.infoblox_adapter.conn.get_all_subnets.assert_has_calls([unittest.mock.call(network_view="default")])
        subnet_with_attrs = self.infoblox_adapter.get("prefix", "10.0.0.0/23__Global")
        self.assertEqual(subnet_with_attrs.ext_attrs, {"attr1": "data", "attr2": "value"})
        self.assertEqual(subnet_with_attrs.vlans, {10: {"vid": 10, "name": "ten", "group": "group_a"}})
        self.assertEqual(subnet_with_attrs.ranges, ["10.0.0.150-10.0.0.254", "10.0.1.150-10.0.1.254"])
        subnet_without_attrs = self.infoblox_adapter.get("prefix", "10.0.100.0/24__Global")
        self.assertEqual(subnet_without_attrs.ext_attrs, {"attr1": "data"})
        self.assertEqual(subnet_without_attrs.vlans, {})
        self.assertEqual(subnet_without_attrs.ranges, [])

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}, {}, {}],
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.build_vlan_map",
        autospec=True,
    )
    def test_load_prefixes_with_infoblox_import_subnets(
        self,
        mock_build_vlan_map,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        ten_container = [
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDEwLjAuMC4wLzgvMA:10.0.0.0/8/default",
                "extattrs": {},
                "network": "10.0.0.0/8",
                "network_view": "default",
                "rir": "NONE",
                "status": "container",
            },
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDEwLjAuMC4wLzgvMA:10.0.0.0/16/default",
                "extattrs": {},
                "network": "10.0.0.0/16",
                "network_view": "default",
                "rir": "NONE",
                "status": "container",
            },
        ]
        self.infoblox_adapter.conn.get_tree_from_container.side_effect = [ten_container, []]
        ten_network = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuNTguMTI4LjAvMTgvMA:10.0.1.0/23/default",
                "extattrs": {},
                "network": "10.0.1.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
            },
        ]
        self.infoblox_adapter.conn.get_child_subnets_from_container.side_effect = [
            [],
            ten_network,
        ]
        one_nine_two_network = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuNTguMTI4LjAvMTgvMA:192.168.0.0/23/default",
                "extattrs": {},
                "network": "192.168.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
            },
        ]
        self.infoblox_adapter.conn.get_all_subnets.side_effect = [one_nine_two_network]
        sync_filters = [{"network_view": "default", "prefixes_ipv4": ["10.0.0.0/8", "192.168.0.0/16"]}]
        self.infoblox_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        self.infoblox_adapter.conn.get_tree_from_container.assert_has_calls(
            [
                unittest.mock.call(root_container="10.0.0.0/8", network_view="default"),
                unittest.mock.call(root_container="192.168.0.0/16", network_view="default"),
            ]
        )
        self.assertEqual(self.infoblox_adapter.conn.get_tree_from_container.call_count, 2)
        self.infoblox_adapter.conn.get_child_subnets_from_container.assert_has_calls(
            [
                unittest.mock.call(prefix="10.0.0.0/8", network_view="default"),
                unittest.mock.call(prefix="10.0.0.0/16", network_view="default"),
            ]
        )
        self.assertEqual(self.infoblox_adapter.conn.get_child_subnets_from_container.call_count, 2)
        self.infoblox_adapter.conn.get_all_subnets.assert_called_once()
        self.infoblox_adapter.conn.get_all_subnets.assert_called_with("192.168.0.0/16", network_view="default")
        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 4)
        mock_build_vlan_map.assert_not_called()
        self.assertEqual(len(self.infoblox_adapter.get_all("prefix")), 4)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}],
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.build_vlan_map",
        autospec=True,
    )
    def test_load_prefixes_add_duplicate_prefix(
        self,
        mock_build_vlan_map,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        self.infoblox_adapter.conn.get_network_containers.return_value = []
        self.infoblox_adapter.conn.get_all_subnets.return_value = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.0.0.0/23/default",
                "extattrs": {},
                "network": "10.0.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
                "ranges": [],
            },
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.0.0.0/23/default",
                "extattrs": {},
                "network": "10.0.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
                "ranges": [],
            },
        ]
        error_message = "Duplicate prefix found: 10.0.0.0/23__Global."
        sync_filters = [{"network_view": "default"}]
        self.infoblox_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        self.infoblox_adapter.job.logger.warning.assert_called_once()
        self.infoblox_adapter.job.logger.warning.assert_called_with(error_message)
        mock_build_vlan_map.assert_not_called()
        self.assertEqual(mock_extra_attr_dict.call_count, 2)
        mock_default_extra_attrs.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={"attr1": "data"},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}, {}, {}, {}, {}],
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.build_vlan_map",
        autospec=True,
        side_effect=[{10: {"vid": 10, "name": "ten", "group": "group_a"}}],
    )
    def test_load_prefixes_ipv6_subnets(
        self,
        mock_build_vlan_map,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        self.infoblox_adapter.conn.get_network_containers.side_effect = [
            [
                {
                    "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:10.0.0.0/8/default",
                    "comment": "root",
                    "extattrs": {},
                    "network": "10.0.0.0/8",
                    "network_view": "default",
                    "rir": "NONE",
                },
                {
                    "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:10.0.0.0/16/default",
                    "comment": "",
                    "extattrs": {},
                    "network": "10.0.0.0/16",
                    "network_view": "default",
                    "rir": "NONE",
                },
            ],
            [
                {
                    "_ref": "ipv6networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDIwMDE6NWIwOjQxMDA6Oi80MC8w:2001%3A5b0%3A4100%3A%3A/40/Gateway%201",
                    "comment": "Gateway 1",
                    "extattrs": {},
                    "network": "2001:5b0:4100::/40",
                    "network_view": "default",
                    "rir": "NONE",
                    "status": "container",
                },
            ],
        ]
        self.infoblox_adapter.conn.get_all_subnets.side_effect = [
            [
                {
                    "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.0.0.0/23/default",
                    "extattrs": {},
                    "network": "10.0.0.0/23",
                    "network_view": "default",
                    "rir": "NONE",
                    "vlans": [10],
                    "ranges": ["10.0.0.150-10.0.0.254", "10.0.1.150-10.0.1.254"],
                },
                {
                    "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIwLjY0LjAvMjEvMA:10.0.100.0/24/default",
                    "extattrs": {},
                    "network": "10.0.100.0/24",
                    "network_view": "default",
                    "rir": "NONE",
                    "vlans": [],
                    "ranges": [],
                },
            ],
            [
                {
                    "_ref": "ipv6networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDIwMDE6NWIwOjQxMDA6Oi80MC8w:2001%3A5b0%3A4100%3A%3A/48/Gateway%201",
                    "extattrs": {},
                    "network": "2001:5b0:4100::/48",
                    "network_view": "default",
                    "rir": "NONE",
                    "vlans": [],
                },
            ],
        ]
        sync_filters = [{"network_view": "default"}]
        self.infoblox_adapter.load_prefixes(include_ipv4=True, include_ipv6=True, sync_filters=sync_filters)
        self.infoblox_adapter.conn.get_tree_from_container.assert_not_called()
        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 6)
        mock_build_vlan_map.assert_called_once()
        self.assertEqual(len(self.infoblox_adapter.get_all("prefix")), 6)
        self.infoblox_adapter.conn.get_network_containers.assert_has_calls(
            [unittest.mock.call(network_view="default"), unittest.mock.call(network_view="default", ipv6=True)]
        )
        self.infoblox_adapter.conn.get_all_subnets.assert_has_calls(
            [unittest.mock.call(network_view="default"), unittest.mock.call(network_view="default", ipv6=True)]
        )
        ipv6_subnet = self.infoblox_adapter.get("prefix", "2001:5b0:4100::/40__Global")
        self.assertEqual(ipv6_subnet.ext_attrs, {"attr1": "data"})
        self.assertEqual(ipv6_subnet.vlans, {})
        self.assertEqual(ipv6_subnet.ranges, [])

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}],
    )
    def test_load_ip_addresses_fixed_only(
        self,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        """Test loading IP Addresses with one fixed address only."""
        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            infoblox_adapter = InfobloxAdapter(
                job=unittest.mock.Mock(),
                sync=unittest.mock.Mock(),
                conn=mock_client,
                config=self.config,
            )
        infoblox_adapter.conn.get_ipaddr_status.return_value = "Active"
        infoblox_adapter.conn.get_all_ipv4address_networks.side_effect = [
            [
                {
                    "_ref": "ipv4address/Li5pcHY0X2FkZHJlc3MkMTAuMjIwLjAuMTAwLzA:10.220.0.100",
                    "extattrs": {"Usage": {"value": "TACACS"}},
                    "ip_address": "10.0.0.2",
                    "is_conflict": "false",
                    "lease_state": "FREE",
                    "mac_address": "",
                    "names": [],
                    "network": "10.0.0.0/24",
                    "network_view": "dev",
                    "objects": ["fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjIuMi4u:10.0.0.2/dev"],
                    "status": "USED",
                    "types": ["RESERVATION"],
                    "usage": ["DHCP"],
                },
            ]
        ]
        infoblox_adapter.conn.get_fixed_address_by_ref.return_value = {
            "_ref": "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjIuMi4u:10.0.0.2/dev",
            "ipv4addr": "10.0.0.2",
            "extattrs": {},
            "name": "fa-server1",
            "comment": "fa server",
            "network": "10.0.0.0/24",
            "network_view": "dev",
        }
        infoblox_adapter.load_ipaddresses()
        ip_address = infoblox_adapter.get(
            "ipaddress",
            {"address": "10.0.0.2", "prefix": "10.0.0.0/24", "prefix_length": 24, "namespace": "dev"},
        )

        self.assertEqual("10.0.0.2", ip_address.address)
        self.assertEqual("10.0.0.0/24", ip_address.prefix)
        self.assertEqual(24, ip_address.prefix_length)
        self.assertEqual("dev", ip_address.namespace)
        self.assertEqual("fa-server1", ip_address.description)
        self.assertEqual("dhcp", ip_address.ip_addr_type)
        self.assertEqual({}, ip_address.ext_attrs)
        self.assertEqual("", ip_address.mac_address)
        self.assertEqual("fa server", ip_address.fixed_address_comment)
        self.assertEqual(False, ip_address.has_a_record)
        self.assertEqual(False, ip_address.has_ptr_record)
        self.assertEqual(False, ip_address.has_host_record)

        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 1)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}, {}],
    )
    def test_load_ip_addresses_fixed_dns_a_dns_ptr(  # pylint: disable=too-many-statements
        self,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        """Test loading IP Addresses with one fixed address, one A record and one PTR record."""
        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            infoblox_adapter = InfobloxAdapter(
                job=unittest.mock.Mock(),
                sync=unittest.mock.Mock(),
                conn=mock_client,
                config=self.config,
            )
        infoblox_adapter.conn.get_ipaddr_status.return_value = "Active"
        infoblox_adapter.conn.get_all_ipv4address_networks.side_effect = [
            [
                {
                    "_ref": "ipv4address/Li5pcHY0X2FkZHJlc3MkMTAuMC4wLjQvMg:10.0.0.4/dev",
                    "ip_address": "10.0.0.4",
                    "is_conflict": "false",
                    "mac_address": "",
                    "names": ["fa1 add", "server11.nautobot.local.test"],
                    "network": "10.0.0.0/24",
                    "network_view": "dev",
                    "objects": [
                        "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjIuMi4u:10.0.0.4/dev",
                        "record:a/ZG5zLmJpbmRfYSQuMi50ZXN0LmxvY2FsLm5hdXRvYm90LHNlcnZlcjExLDEwLjAuMC40:server11.nautobot.local.test/default.dev",
                        "record:ptr/ZG5zLmJpbmRfcHRyJC4yLmFycGEuaW4tYWRkci4xMC4wLjAuNC5zZXJ2ZXIxMS5uYXV0b2JvdC5sb2NhbC50ZXN0:4.0.0.10.in-addr.arpa/default.dev",
                    ],
                    "status": "USED",
                    "types": ["RESERVATION", "A", "PTR"],
                    "usage": ["DHCP", "DNS"],
                }
            ]
        ]
        infoblox_adapter.conn.get_fixed_address_by_ref.return_value = {
            "_ref": "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjIuMi4u:10.0.0.4/dev",
            "ipv4addr": "10.0.0.4",
            "extattrs": {},
            "name": "fa-server1",
            "comment": "fa server",
            "network": "10.0.0.0/24",
            "network_view": "dev",
        }
        infoblox_adapter.conn.get_a_record_by_ref.return_value = {
            "_ref": "record:a/ZG5zLmJpbmRfYSQuMi50ZXN0LmxvY2FsLm5hdXRvYm90LHNlcnZlcjExLDEwLjAuMC40:server11.nautobot.local.test/default.dev",
            "ipv4addr": "10.0.0.4",
            "name": "server11.nautobot.local.test",
            "comment": "a record comment",
            "view": "default",
        }
        infoblox_adapter.conn.get_ptr_record_by_ref.return_value = {
            "_ref": "record:ptr/ZG5zLmJpbmRfcHRyJC4yLmFycGEuaW4tYWRkci4xMC4wLjAuNC5zZXJ2ZXIxMS5uYXV0b2JvdC5sb2NhbC50ZXN0:4.0.0.10.in-addr.arpa/default.dev",
            "ipv4addr": "10.0.0.4",
            "ipv6addr": "",
            "name": "4.0.0.10.in-addr.arpa",
            "ptrdname": "server11.nautobot.local.test",
            "comment": "ptr record comment",
            "view": "default.dev",
        }
        infoblox_adapter.load_ipaddresses()
        ip_address = infoblox_adapter.get(
            "ipaddress",
            {"address": "10.0.0.4", "prefix": "10.0.0.0/24", "prefix_length": 24, "namespace": "dev"},
        )
        self.assertEqual("10.0.0.4", ip_address.address)
        self.assertEqual("10.0.0.0/24", ip_address.prefix)
        self.assertEqual(24, ip_address.prefix_length)
        self.assertEqual("dev", ip_address.namespace)
        self.assertEqual("Active", ip_address.status)
        self.assertEqual("fa-server1", ip_address.description)
        self.assertEqual("dhcp", ip_address.ip_addr_type)
        self.assertEqual({}, ip_address.ext_attrs)
        self.assertEqual("", ip_address.mac_address)
        self.assertEqual(True, ip_address.has_fixed_address)
        self.assertEqual("fa server", ip_address.fixed_address_comment)
        self.assertEqual("RESERVED", ip_address.fixed_address_type)
        self.assertEqual(
            "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjIuMi4u:10.0.0.4/dev", ip_address.fixed_address_ref
        )
        self.assertEqual(True, ip_address.has_a_record)
        self.assertEqual(True, ip_address.has_ptr_record)
        self.assertEqual(False, ip_address.has_host_record)

        a_record = infoblox_adapter.get(
            "dnsarecord",
            {"address": "10.0.0.4", "prefix": "10.0.0.0/24", "prefix_length": 24, "namespace": "dev"},
        )
        self.assertEqual("10.0.0.4", a_record.address)
        self.assertEqual("10.0.0.0/24", a_record.prefix)
        self.assertEqual(24, a_record.prefix_length)
        self.assertEqual("dev", a_record.namespace)
        self.assertEqual("Active", a_record.status)
        self.assertEqual("a record comment", a_record.description)
        self.assertEqual("dhcp", a_record.ip_addr_type)
        self.assertEqual({}, a_record.ext_attrs)
        self.assertEqual("server11.nautobot.local.test", a_record.dns_name)
        self.assertEqual(
            "record:a/ZG5zLmJpbmRfYSQuMi50ZXN0LmxvY2FsLm5hdXRvYm90LHNlcnZlcjExLDEwLjAuMC40:server11.nautobot.local.test/default.dev",
            a_record.ref,
        )

        ptr_record = infoblox_adapter.get(
            "dnsptrrecord",
            {"address": "10.0.0.4", "prefix": "10.0.0.0/24", "prefix_length": 24, "namespace": "dev"},
        )
        self.assertEqual("10.0.0.4", ptr_record.address)
        self.assertEqual("10.0.0.0/24", ptr_record.prefix)
        self.assertEqual(24, ptr_record.prefix_length)
        self.assertEqual("dev", ptr_record.namespace)
        self.assertEqual("Active", ptr_record.status)
        self.assertEqual("ptr record comment", ptr_record.description)
        self.assertEqual("dhcp", ptr_record.ip_addr_type)
        self.assertEqual({}, ptr_record.ext_attrs)
        self.assertEqual("server11.nautobot.local.test", ptr_record.dns_name)
        self.assertEqual(
            "record:ptr/ZG5zLmJpbmRfcHRyJC4yLmFycGEuaW4tYWRkci4xMC4wLjAuNC5zZXJ2ZXIxMS5uYXV0b2JvdC5sb2NhbC50ZXN0:4.0.0.10.in-addr.arpa/default.dev",
            ptr_record.ref,
        )

        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 3)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}],
    )
    def test_load_ip_addresses_fixed_dns_host(
        self,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        """Test loading IP Addresses with one fixed address and one Host record."""
        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            infoblox_adapter = InfobloxAdapter(
                job=unittest.mock.Mock(),
                sync=unittest.mock.Mock(),
                conn=mock_client,
                config=self.config,
            )
        infoblox_adapter.conn.get_ipaddr_status.return_value = "Active"
        infoblox_adapter.conn.get_all_ipv4address_networks.side_effect = [
            [
                {
                    "_ref": "ipv4address/Li5pcHY0X2FkZHJlc3MkMTAuMC4wLjMvMg:10.0.0.4/dev",
                    "ip_address": "10.0.0.4",
                    "is_conflict": "false",
                    "mac_address": "",
                    "names": ["server1.nautobot.local.test"],
                    "network": "10.0.0.0/24",
                    "network_view": "dev",
                    "objects": [
                        "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjQuMi4u:10.0.0.4/dev",
                        "record:host/ZG5zLmhvc3QkLjIudGVzdC5sb2NhbC5uYXV0b2JvdC5zZXJ2ZXIx:server1.nautobot.local.test/default.dev",
                    ],
                    "status": "USED",
                    "types": ["HOST", "RESERVATION"],
                    "usage": [
                        "DHCP",
                        "DNS",
                    ],
                }
            ]
        ]
        infoblox_adapter.conn.get_fixed_address_by_ref.return_value = {
            "_ref": "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjQuMi4u:10.0.0.4/dev",
            "ipv4addr": "10.0.0.4",
            "extattrs": {},
            "name": "fa-server1",
            "comment": "fa server",
            "network": "10.0.0.0/24",
            "network_view": "dev",
        }
        infoblox_adapter.conn.get_host_record_by_ref.return_value = {
            "_ref": "record:host/ZG5zLmhvc3QkLl9kZWZhdWx0LnRlc3QudGVzdGRldmljZTE:testdevice1.test/default",
            "ipv4addr": "10.0.0.4",
            "ipv4addrs": [
                {
                    "_ref": "record:host/ZG5zLmhvc3QkLjIudGVzdC5sb2NhbC5uYXV0b2JvdC5zZXJ2ZXIx:server1.nautobot.local.test/default.dev",
                    "configure_for_dhcp": "true",
                    "host": "server1.nautobot.local.test",
                    "ipv4addr": "10.0.0.4",
                    "mac": "",
                }
            ],
            "name": "server1.nautobot.local.test",
            "view": "default",
            "comment": "host record comment",
        }
        infoblox_adapter.load_ipaddresses()
        ip_address = infoblox_adapter.get(
            "ipaddress",
            {"address": "10.0.0.4", "prefix": "10.0.0.0/24", "prefix_length": 24, "namespace": "dev"},
        )
        self.assertEqual("10.0.0.4", ip_address.address)
        self.assertEqual("10.0.0.0/24", ip_address.prefix)
        self.assertEqual(24, ip_address.prefix_length)
        self.assertEqual("dev", ip_address.namespace)
        self.assertEqual("Active", ip_address.status)
        self.assertEqual("fa-server1", ip_address.description)
        self.assertEqual("dhcp", ip_address.ip_addr_type)
        self.assertEqual({}, ip_address.ext_attrs)
        self.assertEqual("", ip_address.mac_address)
        self.assertEqual(True, ip_address.has_fixed_address)
        self.assertEqual("fa server", ip_address.fixed_address_comment)
        self.assertEqual("RESERVED", ip_address.fixed_address_type)
        self.assertEqual(
            "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLjQuMi4u:10.0.0.4/dev", ip_address.fixed_address_ref
        )
        self.assertEqual(False, ip_address.has_a_record)
        self.assertEqual(False, ip_address.has_ptr_record)
        self.assertEqual(True, ip_address.has_host_record)

        host_record = infoblox_adapter.get(
            "dnshostrecord",
            {"address": "10.0.0.4", "prefix": "10.0.0.0/24", "prefix_length": 24, "namespace": "dev"},
        )
        self.assertEqual("10.0.0.4", host_record.address)
        self.assertEqual("10.0.0.0/24", host_record.prefix)
        self.assertEqual(24, host_record.prefix_length)
        self.assertEqual("dev", host_record.namespace)
        self.assertEqual("Active", host_record.status)
        self.assertEqual("host record comment", host_record.description)
        self.assertEqual("dhcp", host_record.ip_addr_type)
        self.assertEqual({}, host_record.ext_attrs)
        self.assertEqual("server1.nautobot.local.test", host_record.dns_name)
        self.assertEqual(
            "record:host/ZG5zLmhvc3QkLjIudGVzdC5sb2NhbC5uYXV0b2JvdC5zZXJ2ZXIx:server1.nautobot.local.test/default.dev",
            host_record.ref,
        )

        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 2)
