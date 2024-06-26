# pylint: disable=too-many-lines,too-many-public-methods
"""Unit tests for the Infoblox Diffsync models."""
import unittest
from unittest.mock import Mock

from django.test import TestCase

from nautobot_ssot.integrations.infoblox.choices import (
    DNSRecordTypeChoices,
    FixedAddressTypeChoices,
    InfobloxDeletableModelChoices,
)
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
        "ip_addr_type": "dhcp",
        "namespace": "Global",
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
        "dns_name": "server1.local.test.net",
        "ip_addr_type": "host",
        "namespace": "Global",
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
        "namespace": "Global",
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
        "namespace": "Global",
    }
    dns_host_record_dict.update(attrs)

    return dns_host_record_dict


def _get_network_dict(attrs):
    """Build dict used for creating diffsync network."""
    network_dict = {
        "network": "10.0.0.0/8",
        "description": "TestNetwork",
        "namespace": "Global",
        "status": "Active",
    }
    network_dict.update(attrs)

    return network_dict


class TestModelInfobloxNetwork(TestCase):
    """Tests correct network record is created."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.nb_adapter = NautobotAdapter(config=self.config)
        self.nb_adapter.job = Mock()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_network_create_network(self, mock_tag_involved_objects):
        """Validate network gets created."""
        nb_network_atrs = {"network_type": "network"}
        nb_ds_network = self.nb_adapter.prefix(**_get_network_dict(nb_network_atrs))
        self.nb_adapter.add(nb_ds_network)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_network.assert_called_once()
            infoblox_adapter.conn.create_network.assert_called_with(
                prefix="10.0.0.0/8", comment="TestNetwork", network_view="default"
            )
            infoblox_adapter.conn.create_network_container.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_network_create_network_container(self, mock_tag_involved_objects):
        """Validate network container gets created."""
        nb_network_atrs = {"network_type": "container"}
        nb_ds_network = self.nb_adapter.prefix(**_get_network_dict(nb_network_atrs))
        self.nb_adapter.add(nb_ds_network)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_network_container.assert_called_once()
            infoblox_adapter.conn.create_network_container.assert_called_with(
                prefix="10.0.0.0/8", comment="TestNetwork", network_view="default"
            )
            infoblox_adapter.conn.create_network.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_network_update_network(self, mock_tag_involved_objects):
        """Validate network gets updated."""
        nb_network_atrs = {
            "description": "New Description",
        }
        nb_ds_network = self.nb_adapter.prefix(**_get_network_dict(nb_network_atrs))
        self.nb_adapter.add(nb_ds_network)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_network_atrs = {
                "description": "Old Description",
            }
            inf_ds_network = infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
            infoblox_adapter.add(inf_ds_network)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_network.assert_called_once()
            infoblox_adapter.conn.update_network.assert_called_with(
                prefix="10.0.0.0/8", comment="New Description", network_view="default"
            )
            mock_tag_involved_objects.assert_called_once()


class TestModelInfobloxIPAddress(TestCase):
    """Tests Fixed Address record operations."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.nb_adapter = NautobotAdapter(config=self.config)
        self.nb_adapter.job = Mock()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_create_nothing_gets_created(self, mock_tag_involved_objects):
        """Validate nothing gets created if user selects DONT_CREATE_RECORD for DNS and Fixed Address options."""
        nb_ipaddress_atrs = {"has_fixed_address": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_fixed_address.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_create_fixed_address_reserved(self, mock_tag_involved_objects):
        """Validate Fixed Address type RESERVED is created."""
        nb_ipaddress_atrs = {
            "description": "FixedAddresReserved",
            "fixed_address_comment": "Fixed Address Reservation",
            "has_fixed_address": True,
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_fixed_address.assert_called_once()
            infoblox_adapter.conn.create_fixed_address.assert_called_with(
                ip_address="10.0.0.1",
                name="FixedAddresReserved",
                comment="Fixed Address Reservation",
                match_client="RESERVED",
                network_view="default",
            )
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_create_fixed_address_reserved_no_name(self, mock_tag_involved_objects):
        """Validate Fixed Address type RESERVED is created with empty name."""
        nb_ipaddress_atrs = {
            "description": "",
            "has_fixed_address": True,
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_fixed_address.assert_called_once()
            infoblox_adapter.conn.create_fixed_address.assert_called_with(
                ip_address="10.0.0.1",
                name="",
                comment="",
                match_client="RESERVED",
                network_view="default",
            )
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_create_fixed_address_mac(self, mock_tag_involved_objects):
        """Validate Fixed Address type MAC_ADDRESS is created."""
        nb_ipaddress_atrs = {
            "description": "FixedAddresReserved",
            "fixed_address_comment": "Fixed Address Reservation",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_fixed_address.assert_called_once()
            infoblox_adapter.conn.create_fixed_address.assert_called_with(
                ip_address="10.0.0.1",
                name="FixedAddresReserved",
                comment="Fixed Address Reservation",
                mac_address="52:1f:83:d4:9a:2e",
                match_client="MAC_ADDRESS",
                network_view="default",
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_create_fixed_address_mac_no_name(self, mock_tag_involved_objects):
        """Validate Fixed Address type MAC is created with empty name."""
        nb_ipaddress_atrs = {
            "description": "",
            "fixed_address_comment": "",
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:2e",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_fixed_address.assert_called_once()
            infoblox_adapter.conn.create_fixed_address.assert_called_with(
                ip_address="10.0.0.1",
                name="",
                comment="",
                mac_address="52:1f:83:d4:9a:2e",
                match_client="MAC_ADDRESS",
                network_view="default",
            )
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fixed_address_type_reserved_name_and_comment(self, mock_tag_involved_objects):
        """Ensure Fixed Address type RESERVED has name and comment updated."""
        nb_ipaddress_atrs = {
            "has_fixed_address": True,
            "description": "server2.local.test.net",
            "fixed_address_comment": "new description",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "fixed_address_name": "server1.local.test.net",
                "fixed_address_comment": "old description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"name": "server2.local.test.net", "comment": "new description"}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fixed_address_type_reserved_name_and_comment_empty(self, mock_tag_involved_objects):
        """Ensure Fixed Address type RESERVED has name and comment set to empty string."""
        nb_ipaddress_atrs = {
            "has_fixed_address": True,
            "description": "",
            "fixed_address_comment": "",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "description": "server1.local.test.net",
                "fixed_address_comment": "description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"name": "", "comment": ""}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fixed_address_type_mac_update_mac(self, mock_tag_involved_objects):
        """Ensure Fixed Address type MAC has MAC address updated."""
        nb_ipaddress_atrs = {
            "has_fixed_address": True,
            "mac_address": "52:1f:83:d4:9a:ab",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
                "mac_address": "52:1f:83:d4:9a:2e",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"mac": "52:1f:83:d4:9a:ab"}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fixed_address_type_mac_name_and_comment(self, mock_tag_involved_objects):
        """Ensure Fixed Address type MAC has name and comment updated."""
        nb_ipaddress_atrs = {
            "description": "server2.local.test.net",
            "has_fixed_address": True,
            "fixed_address_comment": "new description",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "description": "server1.local.test.net",
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
                "fixed_address_comment": "old description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"name": "server2.local.test.net", "comment": "new description"}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fixed_address_type_mac_name_and_comment_empty(self, mock_tag_involved_objects):
        """Ensure Fixed Address type MAC has name and comment set to empty string."""
        nb_ipaddress_atrs = {
            "has_fixed_address": True,
            "description": "",
            "fixed_address_comment": "",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
                "description": "server1.local.test.net",
                "fixed_address_comment": "description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"name": "", "comment": ""}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_delete_fail(self, mock_tag_involved_objects):
        """Ensure Fixed Address is not deleted if object deletion is not enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.infoblox_deletable_models = []
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "description": "server1.local.test.net",
                "fixed_address_comment": "description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_fixed_address_record_by_ref.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_delete_success(self, mock_tag_involved_objects):
        """Ensure Fixed Address is deleted if object deletion is enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.infoblox_deletable_models = [InfobloxDeletableModelChoices.FIXED_ADDRESS]
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "description": "server1.local.test.net",
                "fixed_address_comment": "description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_fixed_address_record_by_ref.assert_called_once()
            infoblox_adapter.conn.delete_fixed_address_record_by_ref.assert_called_with(ref="fixedaddress/xyz")
            mock_tag_involved_objects.assert_called_once()


class TestModelInfobloxDnsARecord(TestCase):
    """Tests DNS A model operations."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.nb_adapter = NautobotAdapter(config=self.config)
        self.nb_adapter.job = Mock()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_create_nothing_gets_created(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate nothing gets created if user selects DONT_CREATE_RECORD for DNS and Fixed Address options."""
        nb_dnsarecord_atrs = {"has_fixed_address": "True"}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_dnsarecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_fixed_address.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_create(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate A Record is created."""
        nb_dnsarecord_atrs = {}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_dnsarecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test A Record", network_view="default"
            )
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server1.local.test.net", network_view="default"
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_create_no_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS A record is not created if DNS name is missing."""
        nb_arecord_atrs = {"dns_name": ""}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Cannot create Infoblox DNS A record for IP Address 10.0.0.1. DNS name is not defined."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=False,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_create_invalid_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS A record is not created if DNS name is invalid."""
        nb_arecord_atrs = {"dns_name": ".invalid-dns-name"}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Invalid zone fqdn in DNS name `.invalid-dns-name` for IP Address 10.0.0.1."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name=".invalid-dns-name", network_view="default"
            )
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_update(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure only A record is updated."""
        nb_arecord_atrs = {"dns_name": "server2.local.test.net"}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:a/xyz",
            }
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_a_record.assert_called_once()
            infoblox_adapter.conn.update_a_record.assert_called_with(
                ref="record:a/xyz", data={"name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=False,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_update_invalid_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS A record is not updated if DNS name is invalid."""
        nb_arecord_atrs = {"dns_name": ".invalid-dns-name"}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:a/xyz",
            }
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Invalid zone fqdn in DNS name `.invalid-dns-name` for IP Address 10.0.0.1."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name=".invalid-dns-name", network_view="default"
            )
            infoblox_adapter.conn.update_a_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_delete_fail(self, mock_tag_involved_objects):
        """Ensure DNS A record is not deleted if object deletion is not enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            self.config.infoblox_deletable_models = []
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:a/xyz",
            }
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_a_record_by_ref.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_a_record_delete_success(self, mock_tag_involved_objects):
        """Ensure DNS A record is deleted if object deletion is enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            self.config.infoblox_deletable_models = [InfobloxDeletableModelChoices.DNS_A_RECORD]
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:a/xyz",
            }
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_a_record_by_ref.assert_called_once()
            infoblox_adapter.conn.delete_a_record_by_ref.assert_called_with(ref="record:a/xyz")
            mock_tag_involved_objects.assert_called_once()


class TestModelInfobloxDnsHostRecord(TestCase):
    """Tests DNS Host model operations."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.nb_adapter = NautobotAdapter(config=self.config)
        self.nb_adapter.job = Mock()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_create_nothing_gets_created(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate nothing gets created if user selects DONT_CREATE_RECORD for DNS and Fixed Address options."""
        nb_dnshostrecord_atrs = {"has_fixed_address": "True"}
        nb_ds_hostrecord = self.nb_adapter.dnshostrecord(**_get_dns_host_record_dict(nb_dnshostrecord_atrs))
        self.nb_adapter.add(nb_ds_hostrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_fixed_address.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_create(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate Host Record is created."""
        nb_dnshostrecord_atrs = {"has_fixed_address": "True"}
        nb_ds_hostrecord = self.nb_adapter.dnshostrecord(**_get_dns_host_record_dict(nb_dnshostrecord_atrs))
        self.nb_adapter.add(nb_ds_hostrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_called_once()
            infoblox_adapter.conn.create_host_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test Host Record", network_view="default"
            )
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server1.local.test.net", network_view="default"
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_create_no_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS Host record is not created if DNS name is missing."""
        nb_dnshostrecord_atrs = {"dns_name": ""}
        nb_ds_hostrecord = self.nb_adapter.dnshostrecord(**_get_dns_host_record_dict(nb_dnshostrecord_atrs))
        self.nb_adapter.add(nb_ds_hostrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Cannot create Infoblox DNS Host record for IP Address 10.0.0.1. DNS name is not defined."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=False,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_create_invalid_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS Host record is not created if DNS name is invalid."""
        nb_dnshostrecord_atrs = {"dns_name": ".invalid-dns-name"}
        nb_ds_hostrecord = self.nb_adapter.dnshostrecord(**_get_dns_host_record_dict(nb_dnshostrecord_atrs))
        self.nb_adapter.add(nb_ds_hostrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Invalid zone fqdn in DNS name `.invalid-dns-name` for IP Address 10.0.0.1."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name=".invalid-dns-name", network_view="default"
            )
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_update(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure only Host record is updated."""
        nb_dnshostrecord_atrs = {"dns_name": "server2.local.test.net"}
        nb_ds_hostrecord = self.nb_adapter.dnshostrecord(**_get_dns_host_record_dict(nb_dnshostrecord_atrs))
        self.nb_adapter.add(nb_ds_hostrecord)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_hostrecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:host/xyz",
            }
            inf_ds_hostrecord = infoblox_adapter.dnshostrecord(**_get_dns_host_record_dict(inf_hostrecord_atrs))
            infoblox_adapter.add(inf_ds_hostrecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_host_record.assert_called_once()
            infoblox_adapter.conn.update_host_record.assert_called_with(
                ref="record:host/xyz", data={"name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=False,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_update_invalid_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS Host record is not updated if DNS name is invalid."""
        nb_dnshostrecord_atrs = {"dns_name": ".invalid-dns-name"}
        nb_ds_hostrecord = self.nb_adapter.dnshostrecord(**_get_dns_host_record_dict(nb_dnshostrecord_atrs))
        self.nb_adapter.add(nb_ds_hostrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_hostrecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:host/xyz",
            }
            inf_ds_hostrecord = infoblox_adapter.dnshostrecord(**_get_dns_host_record_dict(inf_hostrecord_atrs))
            infoblox_adapter.add(inf_ds_hostrecord)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Invalid zone fqdn in DNS name `.invalid-dns-name` for IP Address 10.0.0.1."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name=".invalid-dns-name", network_view="default"
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_delete_fail(self, mock_tag_involved_objects):
        """Ensure DNS Host record is not deleted if object deletion is not enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            self.config.infoblox_deletable_models = []
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_hostrecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:host/xyz",
            }
            inf_ds_hostrecord = infoblox_adapter.dnshostrecord(**_get_dns_host_record_dict(inf_hostrecord_atrs))
            infoblox_adapter.add(inf_ds_hostrecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_host_record_by_ref.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_host_record_delete_success(self, mock_tag_involved_objects):
        """Ensure DNS Host record is deleted if object deletion is enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            self.config.infoblox_deletable_models = [InfobloxDeletableModelChoices.DNS_HOST_RECORD]
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_hostrecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:host/xyz",
            }
            inf_ds_hostrecord = infoblox_adapter.dnshostrecord(**_get_dns_host_record_dict(inf_hostrecord_atrs))
            infoblox_adapter.add(inf_ds_hostrecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_host_record_by_ref.assert_called_once()
            infoblox_adapter.conn.delete_host_record_by_ref.assert_called_with(ref="record:host/xyz")
            mock_tag_involved_objects.assert_called_once()


class TestModelInfobloxDnsPTRRecord(TestCase):
    """Tests DNS PTR model operations."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.nb_adapter = NautobotAdapter(config=self.config)
        self.nb_adapter.job = Mock()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ptr_record_create(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate PTR record is created."""
        nb_arecord_atrs = {}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        nb_ptrrecord_atrs = {}
        nb_ds_ptrrecord = self.nb_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(nb_ptrrecord_atrs))
        self.nb_adapter.add(nb_ds_ptrrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {}
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test PTR Record", network_view="default"
            )
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server1.local.test.net", network_view="default"
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ptr_record_create_no_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS PTR record is not created if DNS name is missing."""
        nb_arecord_atrs = {}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        nb_ptrrecord_atrs = {"dns_name": ""}
        nb_ds_ptrrecord = self.nb_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(nb_ptrrecord_atrs))
        self.nb_adapter.add(nb_ds_ptrrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {}
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Cannot create Infoblox PTR DNS record for IP Address 10.0.0.1. DNS name is not defined."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=False,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ptr_record_create_invalid_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS PTR record is not created if DNS name is invalid."""
        nb_arecord_atrs = {}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        nb_ptrrecord_atrs = {"dns_name": ".invalid-dns-name"}
        nb_ds_ptrrecord = self.nb_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(nb_ptrrecord_atrs))
        self.nb_adapter.add(nb_ds_ptrrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {}
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Invalid zone fqdn in DNS name `.invalid-dns-name` for IP Address 10.0.0.1."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name=".invalid-dns-name", network_view="default"
            )
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ptr_record_update(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure PTR records is updated."""
        nb_arecord_atrs = {}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        nb_ptrrecord_atrs = {"dns_name": "server2.local.test.net"}
        nb_ds_ptrrecord = self.nb_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(nb_ptrrecord_atrs))
        self.nb_adapter.add(nb_ds_ptrrecord)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {}
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            inf_ptrrecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:ptr/xyz",
            }
            inf_ds_ptrrecord = infoblox_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(inf_ptrrecord_atrs))
            infoblox_adapter.add(inf_ds_ptrrecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_ptr_record.assert_called_once()
            infoblox_adapter.conn.update_ptr_record.assert_called_with(
                ref="record:ptr/xyz", data={"ptrdname": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=False,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ptr_record_update_invalid_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS PTR record is not updated if DNS name is invalid."""
        nb_arecord_atrs = {}
        nb_ds_arecord = self.nb_adapter.dnsarecord(**_get_dns_a_record_dict(nb_arecord_atrs))
        self.nb_adapter.add(nb_ds_arecord)
        nb_ptrrecord_atrs = {"dns_name": ".invalid-dns-name"}
        nb_ds_ptrrecord = self.nb_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(nb_ptrrecord_atrs))
        self.nb_adapter.add(nb_ds_ptrrecord)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_arecord_atrs = {}
            inf_ds_arecord = infoblox_adapter.dnsarecord(**_get_dns_a_record_dict(inf_arecord_atrs))
            infoblox_adapter.add(inf_ds_arecord)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            log_msg = "Invalid zone fqdn in DNS name `.invalid-dns-name` for IP Address 10.0.0.1."
            job_logger.warning.assert_called_with(log_msg)

            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name=".invalid-dns-name", network_view="default"
            )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ptr_record_delete_fail(self, mock_tag_involved_objects):
        """Ensure DNS PTR record is not deleted if object deletion is not enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            self.config.infoblox_deletable_models = []
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ptrrecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:ptr/xyz",
            }
            inf_ds_ptrrecord = infoblox_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(inf_ptrrecord_atrs))
            infoblox_adapter.add(inf_ds_ptrrecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_ptr_record_by_ref.assert_not_called()
            mock_tag_involved_objects.assert_called_once()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ptr_record_delete_success(self, mock_tag_involved_objects):
        """Ensure DNS PTR record is deleted if object deletion is enabled in the config."""
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            self.config.infoblox_deletable_models = [InfobloxDeletableModelChoices.DNS_PTR_RECORD]
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ptrrecord_atrs = {
                "dns_name": "server1.local.test.net",
                "ref": "record:ptr/xyz",
            }
            inf_ds_ptrrecord = infoblox_adapter.dnsptrrecord(**_get_dns_ptr_record_dict(inf_ptrrecord_atrs))
            infoblox_adapter.add(inf_ds_ptrrecord)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.delete_ptr_record_by_ref.assert_called_once()
            infoblox_adapter.conn.delete_ptr_record_by_ref.assert_called_with(ref="record:ptr/xyz")
            mock_tag_involved_objects.assert_called_once()
