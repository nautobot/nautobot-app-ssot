# pylint: disable=too-many-lines,too-many-public-methods,R0801
"""Unit tests for the Infoblox Diffsync models."""
from unittest.mock import Mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Status, Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox.choices import (
    DNSRecordTypeChoices,
    FixedAddressTypeChoices,
    NautobotDeletableModelChoices,
)
from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.tests.infoblox.fixtures_infoblox import create_default_infoblox_config, create_prefix_relationship


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


def _get_dns_a_record_dict(attrs):
    """Build dict used for creating diffsync DNS A record."""
    dns_a_record_dict = {
        "description": "Test A Record",
        "address": "10.0.0.1",
        "status": "Active",
        "prefix": "10.0.0.0/8",
        "prefix_length": 8,
        "dns_name": "server1.nautobot.local.net",
        "ip_addr_type": "host",
        "namespace": "dev",
    }
    dns_a_record_dict.update(attrs)

    return dns_a_record_dict


def _get_dns_ptr_record_dict(attrs):
    """Build dict used for creating diffsync DNS PTR record."""
    dns_ptr_record_dict = {
        "description": "Test PTR Record",
        "address": "10.0.0.1",
        "status": "Active",
        "prefix": "10.0.0.0/8",
        "prefix_length": 8,
        "dns_name": "server1.local.test.net",
        "ip_addr_type": "host",
        "namespace": "dev",
    }
    dns_ptr_record_dict.update(attrs)

    return dns_ptr_record_dict


def _get_dns_host_record_dict(attrs):
    """Build dict used for creating diffsync DNS Host record."""
    dns_host_record_dict = {
        "description": "Test Host Record",
        "address": "10.0.0.1",
        "status": "Active",
        "prefix": "10.0.0.0/8",
        "prefix_length": 8,
        "dns_name": "server1.local.test.net",
        "ip_addr_type": "host",
        "namespace": "dev",
    }
    dns_host_record_dict.update(attrs)

    return dns_host_record_dict


def _get_network_dict(attrs):
    """Build dict used for creating diffsync network."""
    network_dict = {
        "network": "10.0.0.0/8",
        "description": "TestNetwork",
        "namespace": "dev",
        "status": "Active",
        "ext_attrs": {},
        "vlans": {},
    }
    network_dict.update(attrs)

    return network_dict


class TestModelNautobotNetwork(TestCase):
    """Tests correct network record is created."""

    def setUp(self):
        "Test class set up."
        create_prefix_relationship()
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
        create_prefix_relationship()
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

        mac_address_custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="mac_address",
            defaults={
                "label": "MAC Address",
            },
        )
        mac_address_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

        fixed_address_comment_custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="fixed_address_comment",
            defaults={
                "label": "Fixed Address Comment",
            },
        )
        fixed_address_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

        dns_a_record_comment_custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="dns_a_record_comment",
            defaults={
                "label": "DNS A Record Comment",
            },
        )
        dns_a_record_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

        dns_host_record_comment_custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="dns_host_record_comment",
            defaults={
                "label": "DNS Host Record Comment",
            },
        )
        dns_host_record_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

        dns_ptr_record_comment_custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="dns_ptr_record_comment",
            defaults={
                "label": "DNS PTR Record Comment",
            },
        )
        dns_ptr_record_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

    def test_ip_address_create_from_fixed_address_reserved(self):
        """Validate ip address gets created from Infoblox fixed address reservation."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "description": "FixedAddressReserved",
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

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
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

    def test_ip_address_create_from_fixed_address_mac(self):
        """Validate ip address gets created from Infoblox fixed address with mac address."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "description": "FixedAddressMAC",
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

        self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
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

    def test_ip_address_create_from_dns_a_record(self):
        """Validate ip address gets created from Infoblox DNS A record."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_arecord_atrs = {
            "dns_name": "server1.nautobot.local.net",
            "ref": "record:a/xyz",
        }
        inf_ds_arecord = self.infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
        self.infoblox_adapter.add(inf_ds_arecord)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
        self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")
        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("server1.nautobot.local.net", ipaddress.dns_name)
        self.assertEqual("Test A Record", ipaddress.custom_field_data.get("dns_a_record_comment"))
        self.assertEqual("", ipaddress.description)
        self.assertEqual("host", ipaddress.type)
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    def test_ip_address_create_from_dns_host_record(self):
        """Validate ip address gets created from Infoblox DNS Host record."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_hostrecord_atrs = {
            "address": "10.0.0.2",
            "dns_name": "server1.nautobot.local.net",
            "ref": "record:host/xyz",
        }
        inf_ds_hostrecord = self.infoblox_adapter.dnshostrecord(**_get_dns_host_record_dict(inf_hostrecord_atrs))
        self.infoblox_adapter.add(inf_ds_hostrecord)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
        self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.2/8", parent__namespace__name="dev")
        self.assertEqual("10.0.0.2/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("server1.nautobot.local.net", ipaddress.dns_name)
        self.assertEqual("Test Host Record", ipaddress.custom_field_data.get("dns_host_record_comment"))
        self.assertEqual("", ipaddress.description)
        self.assertEqual("host", ipaddress.type)
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    def test_ip_address_create_from_fixed_address_reserved_and_dns_a_record(self):
        """Validate ip address gets created from Infoblox Fixed Address MAC and updated with DNS A record data."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_a_record": True,
            "description": "FixedAddressMAC",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "fixed_address_comment": "Created From FA MAC",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)
        inf_arecord_atrs = {
            "dns_name": "server1.nautobot.local.net",
            "ref": "record:a/xyz",
        }
        inf_ds_arecord = self.infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
        self.infoblox_adapter.add(inf_ds_arecord)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
        self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
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
        self.assertEqual("Test A Record", ipaddress.custom_field_data.get("dns_a_record_comment"))
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    def test_ip_address_create_from_fixed_address_mac_and_dns_a_ptr_records(self):
        """Validate ip address gets created from Infoblox Fixed Address MAC and updated with DNS A and PTR records data."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_a_record": True,
            "description": "FixedAddressMAC",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "fixed_address_comment": "Created From FA MAC",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)
        inf_arecord_atrs = {
            "dns_name": "server1.nautobot.local.net",
            "ref": "record:a/xyz",
        }
        inf_ds_arecord = self.infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
        self.infoblox_adapter.add(inf_ds_arecord)
        inf_ptrrecord_atrs = {
            "dns_name": "server1.nautobot.local.net",
            "ref": "record:ptr/xyz",
        }
        inf_ds_ptrrecord = self.infoblox_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(inf_ptrrecord_atrs))
        self.infoblox_adapter.add(inf_ds_ptrrecord)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
        self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
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
        self.assertEqual("Test A Record", ipaddress.custom_field_data.get("dns_a_record_comment"))
        self.assertEqual("Test PTR Record", ipaddress.custom_field_data.get("dns_ptr_record_comment"))
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    def test_ip_address_create_from_fixed_address_mac_and_dns_host_record(self):
        """Validate ip address gets created from Infoblox Fixed Address MAC and updated with DNS host record data."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_a_record": True,
            "description": "FixedAddressMAC",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "fixed_address_comment": "Created From FA MAC",
        }
        inf_ds_ipaddress = self.infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_address_atrs))
        self.infoblox_adapter.add(inf_ds_ipaddress)
        inf_hostrecord_atrs = {
            "dns_name": "server1.nautobot.local.net",
            "ref": "record:host/xyz",
        }
        inf_ds_hostrecord = self.infoblox_adapter.dnshostrecord(**_get_dns_host_record_dict(inf_hostrecord_atrs))
        self.infoblox_adapter.add(inf_ds_hostrecord)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="TestNetwork",
            namespace=self.namespace_dev,
        )

        self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
        self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
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
        self.assertEqual("Test Host Record", ipaddress.custom_field_data.get("dns_host_record_comment"))
        self.assertIn(self.tag_sync_from_infoblox, ipaddress.tags.all())

    ############
    # IP Address updates
    ###########

    def test_ip_address_update_from_fixed_address_reserved(self):
        """Validate ip address gets updated from Infoblox fixed address reservation."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "description": "FixedAddressReserved",
            "fixed_address_comment": "Created From FA Reserved",
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

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
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
            "description": "FixedAddressMAC",
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

        self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
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

    def test_ip_address_update_address_from_dns_a_record(self):
        """Validate ip address gets created from Infoblox DNS A record."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_arecord_atrs = {
            "dns_name": "server1.nautobot.local.net",
            "ref": "record:a/xyz",
        }
        inf_ds_arecord = self.infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
        self.infoblox_adapter.add(inf_ds_arecord)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "description": "FixedAddressReserved",
            "fixed_address_comment": "Created From FA Reserved",
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
                "dns_name": "server.nautobot.local.net",
                "description": "OldDescription",
                "_custom_field_data": {
                    "mac_address": "52:1f:83:d4:9a:2a",
                    "fixed_address_comment": "Old FA comment",
                    "dns_a_record_comment": "Old A record comment",
                },
            },
        )

        self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressReserved", ipaddress.description)
        self.assertEqual("server1.nautobot.local.net", ipaddress.dns_name)
        self.assertEqual("Created From FA Reserved", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertEqual("Test A Record", ipaddress.custom_field_data.get("dns_a_record_comment"))
        self.assertEqual("dhcp", ipaddress.type)

    ############
    # IP Address deletes
    ###########

    def test_ip_address_delete_fail(self):
        """Validate ip address is not deleted if object deletion is not enabled in the config."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)

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
            type="dhcp",
            parent=parent_pfx,
            defaults={
                "description": "OldDescription",
                "_custom_field_data": {
                    "mac_address": "52:1f:83:d4:9a:2a",
                    "fixed_address_comment": "Old FA comment",
                },
            },
        )

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        self.config.nautobot_deletable_models = []
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("OldDescription", ipaddress.description)
        self.assertEqual("dhcp", ipaddress.type)
        self.assertEqual("Old FA comment", ipaddress.custom_field_data.get("fixed_address_comment"))

    def test_ip_address_delete_success(self):
        """Validate ip address is deleted if object deletion is enabled in the config."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)

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

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        self.config.nautobot_deletable_models = [NautobotDeletableModelChoices.IP_ADDRESS]
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        with self.assertRaises(IPAddress.DoesNotExist):
            IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

    def test_ip_address_delete_a_record(self):
        """Validate A record data for ip address is deleted if object deletion is enabled in the config."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "description": "FixedAddressReserved",
            "fixed_address_comment": "Created From FA Reserved",
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
            type="dhcp",
            parent=parent_pfx,
            defaults={
                "description": "FixedAddressReserved",
                "dns_name": "server1.nautobot.local.net",
                "_custom_field_data": {
                    "fixed_address_comment": "Created From FA Reserved",
                    "dns_a_record_comment": "Created From A Record",
                },
            },
        )

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
        self.config.nautobot_deletable_models = [NautobotDeletableModelChoices.DNS_A_RECORD]
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressReserved", ipaddress.description)
        self.assertEqual("", ipaddress.dns_name)
        self.assertEqual("Created From FA Reserved", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertEqual("", ipaddress.custom_field_data.get("dns_a_record_comment"))
        self.assertEqual("dhcp", ipaddress.type)

    def test_ip_address_delete_host_record(self):
        """Validate Host record data for ip address is deleted if object deletion is enabled in the config."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "description": "FixedAddressReserved",
            "fixed_address_comment": "Created From FA Reserved",
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
            type="dhcp",
            parent=parent_pfx,
            defaults={
                "description": "FixedAddressReserved",
                "dns_name": "server1.nautobot.local.net",
                "_custom_field_data": {
                    "fixed_address_comment": "Created From FA Reserved",
                    "dns_host_record_comment": "Created From Host Record",
                },
            },
        )

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
        self.config.nautobot_deletable_models = [NautobotDeletableModelChoices.DNS_HOST_RECORD]
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressReserved", ipaddress.description)
        self.assertEqual("", ipaddress.dns_name)
        self.assertEqual("Created From FA Reserved", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertEqual("", ipaddress.custom_field_data.get("dns_host_record_comment"))
        self.assertEqual("dhcp", ipaddress.type)

    def test_ip_address_delete_a_ptr_records(self):
        """Validate A and PTR record data for ip address is deleted if object deletion is enabled in the config."""
        inf_network_atrs = {"network_type": "network", "namespace": "dev"}
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)
        inf_address_atrs = {
            "ip_addr_type": "dhcp",
            "has_fixed_address": True,
            "description": "FixedAddressReserved",
            "fixed_address_comment": "Created From FA Reserved",
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
            type="dhcp",
            parent=parent_pfx,
            defaults={
                "description": "FixedAddressReserved",
                "dns_name": "server1.nautobot.local.net",
                "_custom_field_data": {
                    "fixed_address_comment": "Created From FA Reserved",
                    "dns_a_record_comment": "Created From A Record",
                    "dns_ptr_record_comment": "Created From PTR Record",
                },
            },
        )

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
        self.config.nautobot_deletable_models = [
            NautobotDeletableModelChoices.DNS_A_RECORD,
            NautobotDeletableModelChoices.DNS_PTR_RECORD,
        ]
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock()
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8", parent__namespace__name="dev")

        self.assertEqual("10.0.0.1/8", str(ipaddress.address))
        self.assertEqual("dev", ipaddress.parent.namespace.name)
        self.assertEqual("Active", ipaddress.status.name)
        self.assertEqual("FixedAddressReserved", ipaddress.description)
        self.assertEqual("", ipaddress.dns_name)
        self.assertEqual("Created From FA Reserved", ipaddress.custom_field_data.get("fixed_address_comment"))
        self.assertEqual("", ipaddress.custom_field_data.get("dns_a_record_comment"))
        self.assertEqual("", ipaddress.custom_field_data.get("dns_ptr_record_comment"))
        self.assertEqual("dhcp", ipaddress.type)
