# pylint: disable=too-many-lines,too-many-public-methods,R0801
"""Unit tests for the Infoblox Diffsync models."""
from unittest.mock import Mock

from django.test import TestCase
from nautobot.extras.models import Status, Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter

from .fixtures_infoblox import create_default_infoblox_config


def _get_ip_address_dict(attrs):
    """Build dict used for creating diffsync IP address."""
    ipaddress_dict = {
        "description": "Test IPAddress",
        "address": "10.0.0.1",
        "status": "Active",
        "prefix": "10.0.0.0/8",
        "prefix_length": 8,
        "ip_addr_type": "host",
        "namespace": "dev",
        "dns_name": "",
        "ext_attrs": {},
    }
    ipaddress_dict.update(attrs)

    return ipaddress_dict


def _get_network_dict(attrs):
    """Build dict used for creating diffsync network."""
    network_dict = {
        "network": "10.0.0.0/8",
        "description": "TestNetwork",
        "namespace": "dev",
        "status": "Active",
        "ext_attrs": {},
    }
    network_dict.update(attrs)

    return network_dict


class TestModelNautobotNetwork(TestCase):
    """Tests correct network record is created."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.config.infoblox_sync_filters = [{"network_view": "default"}, {"network_view": "dev"}]
        self.namespace_dev, _ = Namespace.objects.get_or_create(name="dev")
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.tag_sync_from_infoblox, _ = Tag.objects.get_or_create(name="SSoT Synced from Infoblox")
        self.infoblox_adapter = InfobloxAdapter(conn=Mock(), config=self.config)
        inf_ds_namespace = self.infoblox_adapter.namespace(
            name="Global",
            ext_attrs={},
        )
        self.infoblox_adapter.add(inf_ds_namespace)
        inf_ds_namespace = self.infoblox_adapter.namespace(
            name="dev",
            ext_attrs={},
        )
        self.infoblox_adapter.add(inf_ds_namespace)

    def test_network_create_network(self):
        """Validate network gets created."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8", namespace__name="dev")

        self.assertEqual("10.0.0.0/8", str(prefix.prefix))
        self.assertEqual("dev", prefix.namespace.name)
        self.assertEqual("Active", prefix.status.name)
        self.assertEqual("TestNetwork", prefix.description)
        self.assertEqual("network", prefix.type)
        self.assertIn(self.tag_sync_from_infoblox, prefix.tags.all())

    def test_network_update_network(self):
        """Validate network gets updated."""
        inf_network_atrs = {
            "network_type": "network",
            "namespace": "dev",
            "ext_attrs": {"vlan": "10"},
            "description": "New description",
        }
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/24",
            status=self.status_active,
            type="network",
            description="Old description",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8", namespace__name="dev")

        self.assertEqual("10.0.0.0/8", str(prefix.prefix))
        self.assertEqual("dev", prefix.namespace.name)
        self.assertEqual("Active", prefix.status.name)
        self.assertEqual("New description", prefix.description)
        self.assertEqual("network", prefix.type)
        self.assertEqual({"vlan": "10"}, prefix.custom_field_data)
        self.assertIn(self.tag_sync_from_infoblox, prefix.tags.all())


class TestModelNautobotIPAddress(TestCase):
    """Tests correct IP address record is created or updated."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.config.infoblox_sync_filters = [{"network_view": "default"}, {"network_view": "dev"}]
        self.namespace_dev, _ = Namespace.objects.get_or_create(name="dev")
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.tag_sync_from_infoblox, _ = Tag.objects.get_or_create(name="SSoT Synced from Infoblox")
        self.infoblox_adapter = InfobloxAdapter(conn=Mock(), config=self.config)
        inf_ds_namespace = self.infoblox_adapter.namespace(
            name="Global",
            ext_attrs={},
        )
        self.infoblox_adapter.add(inf_ds_namespace)
        inf_ds_namespace = self.infoblox_adapter.namespace(
            name="dev",
            ext_attrs={},
        )
        self.infoblox_adapter.add(inf_ds_namespace)

    def test_ip_address_create_address_from_fixed_address_reserved(self):
        """Validate ip address gets created from Infoblox fixed address reservation."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "fixed_address_name": "FixedAddressReserved",
            "fixed_address_comment": "Created From FA Reserved",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressReserved", ipaddress.description)
        self.assertEqual("dhcp", ipaddress.type)
        self.assertEqual("Created From FA Reserved", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    def test_ip_address_create_address_from_fixed_address_mac(self):
        """Validate ip address gets created from Infoblox fixed address with mac address."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "fixed_address_name": "FixedAddressMAC",
            "fixed_address_comment": "Created From FA MAC",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressMAC", ipaddress.description)
        self.assertEqual("dhcp", ipaddress.type)
        self.assertEqual("52:1f:83:d4:9a:2e", ipaddress.custom_field_data.get("mac_address"))
        self.assertEqual("Created From FA MAC", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    def test_ip_address_create_address_from_dns_record(self):
        """Validate ip address gets created from Infoblox DNS host record. This also applies to A record."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "host",
            "has_host_record": True,
            "dns_name": "server1.nautobot.local.net",
            "description": "Server1",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")
        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("server1.nautobot.local.net", ipaddress.dns_name)
        self.assertEqual("Server1", ipaddress.description)
        self.assertEqual("host", ipaddress.type)
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    def test_ip_address_create_address_from_fixed_address_mac_and_dns_record(self):
        """Validate ip address gets created from Infoblox Fixed Address MAC + A host record.
        Fixed address name takes precedence and is recorded in the description field of Nautobot IP Address.
        """
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_a_record": True,
            "dns_name": "server1.nautobot.local.net",
            "description": "Server1",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "fixed_address_name": "FixedAddressMAC",
            "fixed_address_comment": "Created From FA MAC",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")
        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("server1.nautobot.local.net", ipaddress.dns_name)
        self.assertEqual("FixedAddressMAC", ipaddress.description)
        self.assertEqual("dhcp", ipaddress.type)
        self.assertEqual("52:1f:83:d4:9a:2e", ipaddress.custom_field_data.get("mac_address"))
        self.assertEqual("Created From FA MAC", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    ############
    # IP Address updates
    ###########

    def test_ip_address_update_address_from_fixed_address_reserved(self):
        """Validate ip address gets updated from Infoblox fixed address reservation."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev", "ext_attrs": {"vlans": {}}}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "fixed_address_name": "FixedAddressMAC",
            "fixed_address_comment": "Created From FA MAC",
            "ext_attrs": {"gateway": "10.0.0.254"},
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)

        parent_pfx, _ = Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )
        IPAddress.objects.get_or_create(
            address="10.0.0.1/8",
            status=self.status_active,
            type="host",
            description="OldDescription",
            parent=parent_pfx,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressMAC", ipaddress.description)
        self.assertEqual("dhcp", ipaddress.type)
        self.assertEqual("Created From FA MAC", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertEqual("10.0.0.254", ipaddress.custom_field_data.get("gateway"))

    def test_ip_address_update_address_from_fixed_address_mac(self):
        """Validate ip address gets created from Infoblox fixed address with mac address."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "fixed_address_name": "FixedAddressMAC",
            "fixed_address_comment": "Created From FA MAC",
            "ext_attrs": {"gateway": "10.0.0.254"},
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)

        parent_pfx, _ = Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )
        IPAddress.objects.get_or_create(
            address="10.0.0.1/8",
            status=self.status_active,
            type="host",
            parent=parent_pfx,
            defaults={
                "description": "OldDescription",
                "_custom_field_data": {"mac_address": "52:1f:83:d4:9a:2a"},
            },
        )
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressMAC", ipaddress.description)
        self.assertEqual("dhcp", ipaddress.type)
        self.assertEqual("52:1f:83:d4:9a:2e", ipaddress.custom_field_data.get("mac_address"))
        self.assertEqual("Created From FA MAC", ipaddress.custom_field_data.get("fixed_address_comment"))

    def test_ip_address_update_address_from_dns_record(self):
        """Validate ip address gets created from Infoblox DNS record."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "host",
            "has_a_record": True,
            "dns_name": "server1.nautobot.local.net",
            "description": "Server1",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)

        parent_pfx, _ = Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )
        IPAddress.objects.get_or_create(
            address="10.0.0.1/8",
            status=self.status_active,
            type="host",
            parent=parent_pfx,
            defaults={
                "dns_name": "server.nautobot.local.net",
                "description": "OldDescription",
                "_custom_field_data": {"mac_address": "52:1f:83:d4:9a:2a"},
            },
        )
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("Server1", ipaddress.description)
        self.assertEqual("server1.nautobot.local.net", ipaddress.dns_name)
        self.assertEqual("host", ipaddress.type)
