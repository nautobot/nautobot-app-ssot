"""Nautobot Adapter tests."""

from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models import RelationshipAssociation, Status
from nautobot.ipam.models import VLAN, IPAddress, Namespace, Prefix, VLANGroup

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices
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
        namespace_test, _ = Namespace.objects.get_or_create(name="test")
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
        prefix2 = Prefix.objects.create(
            prefix="10.0.1.0/24",
            status=active_status,
            type="Network",
        )
        prefix3 = Prefix.objects.create(
            prefix="10.0.1.0/24",
            status=active_status,
            type="Network",
            namespace=namespace_dev,
        )
        prefix4 = Prefix.objects.create(
            prefix="10.2.1.0/24",
            status=active_status,
            type="Network",
            namespace=namespace_dev,
        )
        prefix5 = Prefix.objects.create(
            prefix="10.2.1.0/25",
            status=active_status,
            type="Network",
            namespace=namespace_test,
        )
        prefix6 = Prefix.objects.create(
            prefix="10.5.1.0/25",
            status=active_status,
            type="Network",
            namespace=namespace_test,
        )
        ipv6prefix1 = Prefix.objects.create(
            prefix="2001:5b0:4100::/48",
            status=active_status,
            type="Network",
        )
        IPAddress.objects.create(
            description="Test IPAddress 1",
            address="10.0.1.1/24",
            status=active_status,
            type="host",
            dns_name="server1.nautobot.test.com",
            parent_id=prefix2.id,
        )
        IPAddress.objects.create(
            description="Test IPAddress 2",
            address="10.0.1.2/24",
            status=active_status,
            type="host",
            dns_name="server2.nautobot.test.com",
            parent_id=prefix2.id,
        )
        IPAddress.objects.create(
            description="Test IPAddress 3",
            address="10.0.1.1/24",
            status=active_status,
            type="host",
            dns_name="server10.nautobot.test.com",
            parent_id=prefix3.id,
        )
        IPAddress.objects.create(
            description="Test IPAddress 4",
            address="10.2.1.1/24",
            status=active_status,
            type="host",
            dns_name="server11.nautobot.test.com",
            parent_id=prefix4.id,
        )
        IPAddress.objects.create(
            description="Test IPAddress 5",
            address="10.2.1.10/25",
            status=active_status,
            type="host",
            dns_name="server20.nautobot.test.com",
            parent_id=prefix5.id,
        )
        IPAddress.objects.create(
            description="Test IPAddress 6",
            address="10.5.1.5/25",
            status=active_status,
            type="host",
            dns_name="server21.nautobot.test.com",
            parent_id=prefix6.id,
        )
        IPAddress.objects.create(
            description="Test IPv6Address 1",
            address="2001:5b0:4100::1/48",
            status=active_status,
            type="host",
            dns_name="v6server1.nautobot.test.com",
            parent_id=ipv6prefix1.id,
        )
        self.config = create_default_infoblox_config()
        self.sync_filters = self.config.infoblox_sync_filters
        self.nb_adapter = NautobotAdapter(config=self.config)
        self.nb_adapter.job = mock.Mock()

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

    def test_load_prefixes_loads_prefixes_multiple_filters(self):
        sync_filters = [
            {"network_view": "dev", "prefixes_ipv4": ["10.0.0.0/16"]},
            {"network_view": "test", "prefixes_ipv4": ["10.0.0.0/8"]},
        ]
        self.nb_adapter.load_prefixes(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_prefixes = {(prefix.network, prefix.namespace) for prefix in self.nb_adapter.get_all("prefix")}
        self.assertEqual(
            actual_prefixes,
            {
                ("10.0.1.0/24", "dev"),
                ("10.2.1.0/25", "test"),
                ("10.5.1.0/25", "test"),
            },
        )

    def test_load_prefixes_loads_prefixes_ipv6(self):
        sync_filters = [{"network_view": "default"}]
        self.nb_adapter.load_prefixes(include_ipv4=False, include_ipv6=True, sync_filters=sync_filters)
        actual_prefixes = {(prefix.network, prefix.namespace) for prefix in self.nb_adapter.get_all("prefix")}
        self.assertEqual(
            actual_prefixes,
            {
                ("2001:5b0:4100::/48", "Global"),
            },
        )

    def test_load_prefixes_loads_prefixes_ipv4_and_ipv6(self):
        sync_filters = [{"network_view": "default"}]
        self.nb_adapter.load_prefixes(include_ipv4=True, include_ipv6=True, sync_filters=sync_filters)
        actual_prefixes = {(prefix.network, prefix.namespace) for prefix in self.nb_adapter.get_all("prefix")}
        self.assertEqual(
            actual_prefixes,
            {
                ("10.0.0.0/24", "Global"),
                ("10.0.1.0/24", "Global"),
                ("2001:5b0:4100::/48", "Global"),
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

    def test_load_ipaddresses_loads_ips_default_namespace(self):
        sync_filters = [{"network_view": "default"}]
        self.nb_adapter.load_ipaddresses(sync_filters=sync_filters, include_ipv4=True, include_ipv6=False)
        actual_ipaddresses = {(ipaddr.address, ipaddr.namespace) for ipaddr in self.nb_adapter.get_all("ipaddress")}
        self.assertEqual(
            actual_ipaddresses,
            {("10.0.1.1", "Global"), ("10.0.1.2", "Global")},
        )

    def test_load_ipaddresses_loads_ips_dev_namespace(self):
        sync_filters = [{"network_view": "dev"}]
        self.nb_adapter.load_ipaddresses(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_ipaddresses = {(ipaddr.address, ipaddr.namespace) for ipaddr in self.nb_adapter.get_all("ipaddress")}
        self.assertEqual(
            actual_ipaddresses,
            {("10.0.1.1", "dev"), ("10.2.1.1", "dev")},
        )

    def test_load_ipaddresses_loads_ips_dev_namespace_filtered(self):
        sync_filters = [{"network_view": "dev", "prefixes_ipv4": ["10.0.1.0/24"]}]
        self.nb_adapter.load_ipaddresses(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_ipaddresses = {(ipaddr.address, ipaddr.namespace) for ipaddr in self.nb_adapter.get_all("ipaddress")}
        self.assertEqual(
            actual_ipaddresses,
            {
                ("10.0.1.1", "dev"),
            },
        )

    def test_load_ipaddresses_loads_ips_multiple_filters(self):
        sync_filters = [
            {"network_view": "dev", "prefixes_ipv4": ["10.0.0.0/16"]},
            {"network_view": "test", "prefixes_ipv4": ["10.5.0.0/16"]},
        ]
        self.nb_adapter.load_ipaddresses(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_ipaddresses = {(ipaddr.address, ipaddr.namespace) for ipaddr in self.nb_adapter.get_all("ipaddress")}
        self.assertEqual(
            actual_ipaddresses,
            {
                ("10.0.1.1", "dev"),
                ("10.5.1.5", "test"),
            },
        )

    def test_load_ipaddresses_loads_ips_ipv6(self):
        sync_filters = [{"network_view": "default"}]
        self.nb_adapter.load_ipaddresses(include_ipv4=False, include_ipv6=True, sync_filters=sync_filters)
        actual_ipaddresses = {(ipaddr.address, ipaddr.namespace) for ipaddr in self.nb_adapter.get_all("ipaddress")}
        self.assertEqual(
            actual_ipaddresses,
            {
                ("2001:5b0:4100::1", "Global"),
            },
        )

    def test_load_ipaddresses_loads_ips_ipv4_and_ipv6(self):
        sync_filters = [{"network_view": "default"}]
        self.nb_adapter.load_ipaddresses(include_ipv4=True, include_ipv6=True, sync_filters=sync_filters)
        actual_ipaddresses = {(ipaddr.address, ipaddr.namespace) for ipaddr in self.nb_adapter.get_all("ipaddress")}
        self.assertEqual(
            actual_ipaddresses,
            {
                ("10.0.1.1", "Global"),
                ("10.0.1.2", "Global"),
                ("2001:5b0:4100::1", "Global"),
            },
        )

    def test_load_ipaddresses_load_host_records(self):
        self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = mock.Mock()
        sync_filters = [{"network_view": "default"}]
        nb_adapter.load_ipaddresses(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_records = {
            (hostr.address, hostr.namespace, hostr.dns_name) for hostr in nb_adapter.get_all("dnshostrecord")
        }
        self.assertEqual(
            actual_records,
            {
                ("10.0.1.1", "Global", "server1.nautobot.test.com"),
                ("10.0.1.2", "Global", "server2.nautobot.test.com"),
            },
        )

    def test_load_ipaddresses_load_a_records(self):
        self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = mock.Mock()
        sync_filters = [{"network_view": "dev"}]
        nb_adapter.load_ipaddresses(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_records = {
            (hostr.address, hostr.namespace, hostr.dns_name) for hostr in nb_adapter.get_all("dnsarecord")
        }
        self.assertEqual(
            actual_records,
            {
                ("10.0.1.1", "dev", "server10.nautobot.test.com"),
                ("10.2.1.1", "dev", "server11.nautobot.test.com"),
            },
        )

    def test_load_ipaddresses_load_ptr_records(self):
        self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = mock.Mock()
        sync_filters = [{"network_view": "test"}]
        nb_adapter.load_ipaddresses(include_ipv4=True, include_ipv6=False, sync_filters=sync_filters)
        actual_records = {
            (hostr.address, hostr.namespace, hostr.dns_name) for hostr in nb_adapter.get_all("dnsptrrecord")
        }
        self.assertEqual(
            actual_records,
            {
                ("10.5.1.5", "test", "server21.nautobot.test.com"),
                ("10.2.1.10", "test", "server20.nautobot.test.com"),
            },
        )
