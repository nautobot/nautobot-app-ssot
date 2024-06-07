# pylint: disable=too-many-lines,too-many-public-methods
"""Unit tests for the Infoblox Diffsync models."""
import unittest
from unittest.mock import Mock

from django.test import TestCase

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices, FixedAddressTypeChoices
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
        "namespace": "Global",
        "dns_name": "",
    }
    ipaddress_dict.update(attrs)

    return ipaddress_dict


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


class TestModelInfobloxIPAddressCreate(TestCase):
    """Tests correct Fixed Address and DNS record are created."""

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
    def test_ip_address_create_nothing_gets_created(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate nothing gets created if user selects DONT_CREATE_RECORD for DNS and Fixed Address options."""
        nb_ipaddress_atrs = {"dns_name": "server1.local.test.net", "mac_address": "52:1f:83:d4:9a:2e"}
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
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
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
    def test_ip_address_create_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate A Record is created."""
        nb_ipaddress_atrs = {"has_a_record": True, "dns_name": "server1.local.test.net"}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
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
    def test_ip_address_create_a_and_ptr_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate A and PTR records are created."""
        nb_ipaddress_atrs = {"has_a_record": True, "has_ptr_record": True, "dns_name": "server1.local.test.net"}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
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
    def test_ip_address_create_host_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate Host Record is created."""
        nb_ipaddress_atrs = {"has_host_record": True, "dns_name": "server1.local.test.net"}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
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
    def test_ip_address_create_no_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS record is not created if DNS name is missing."""
        nb_ipaddress_atrs = {"has_a_record": True, "dns_name": ""}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
            log_msg = "Cannot create Infoblox DNS record for IP Address 10.0.0.1. DNS name is not defined."
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
    def test_ip_address_create_invalid_dns_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS record is not created if DNS name is invalid."""
        nb_ipaddress_atrs = {"has_a_record": True, "dns_name": ".invalid-dns-name"}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
    def test_ip_address_create_fixed_address_reserved(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate Fixed Address type RESERVED is created."""
        nb_ipaddress_atrs = {
            "fixed_address_name": "FixedAddresReserved",
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
    def test_ip_address_create_fixed_address_reserved_no_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate Fixed Address type RESERVED is created with empty name."""
        nb_ipaddress_atrs = {
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
    def test_ip_address_create_fixed_address_mac(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate Fixed Address type MAC_ADDRESS is created."""
        nb_ipaddress_atrs = {
            "fixed_address_name": "FixedAddresReserved",
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
    def test_ip_address_create_fixed_address_mac_no_name(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate Fixed Address type MAC is created with empty name."""
        nb_ipaddress_atrs = {
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
    def test_ip_address_create_fixed_address_reserved_with_host_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Validate Fixed Address type RESERVED is created with DNS Host record."""
        nb_ipaddress_atrs = {
            "dns_name": "server1.local.test.net",
            "fixed_address_name": "FixedAddresReserved",
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
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
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
            infoblox_adapter.conn.create_host_record.assert_called_once()
            infoblox_adapter.conn.create_host_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
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
    def test_ip_address_create_fixed_address_reserved_with_a_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Validate Fixed Address type RESERVED is created with DNS A record."""
        nb_ipaddress_atrs = {
            "dns_name": "server1.local.test.net",
            "fixed_address_name": "FixedAddresReserved",
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
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
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
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
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
    def test_ip_address_create_fixed_address_reserved_with_a_and_ptr_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Validate Fixed Address type RESERVED is created with DNS A and PTR records."""
        nb_ipaddress_atrs = {
            "dns_name": "server1.local.test.net",
            "fixed_address_name": "FixedAddresReserved",
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
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
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
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
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
    def test_ip_address_create_fixed_address_mac_with_host_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Validate Fixed Address type MAC_ADDRESS is created with DNS Host record."""
        nb_ipaddress_atrs = {
            "dns_name": "server1.local.test.net",
            "fixed_address_name": "FixedAddresReserved",
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
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
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
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_called_once()
            infoblox_adapter.conn.create_host_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
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
    def test_ip_address_create_fixed_address_mac_with_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate Fixed Address type MAC_ADDRESS is created with DNS A record."""
        nb_ipaddress_atrs = {
            "dns_name": "server1.local.test.net",
            "fixed_address_name": "FixedAddresReserved",
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
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
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
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
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
    def test_ip_address_create_fixed_address_mac_with_a_and_ptr_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Validate Fixed Address type MAC_ADDRESS is created with DNS A and PTR records."""
        nb_ipaddress_atrs = {
            "dns_name": "server1.local.test.net",
            "fixed_address_name": "FixedAddresReserved",
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
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
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
            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server1.local.test.net", network_view="default"
            )


class TestModelInfobloxIPAddressUpdate(TestCase):
    """Tests validating IP Address Update scenarios."""

    def setUp(self):
        "Test class set up."
        self.config = create_default_infoblox_config()
        self.nb_adapter = NautobotAdapter(config=self.config)
        self.nb_adapter.job = Mock()

    ############
    # TEST Fixed Address record updates
    ###########

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fixed_address_type_reserved_name_and_comment(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address type RESERVED has name and comment updated."""
        nb_ipaddress_atrs = {
            "has_fixed_address": True,
            "fixed_address_name": "server2.local.test.net",
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
                "fixed_address_comment": "description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"name": "server2.local.test.net", "comment": "new description"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
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
    def test_ip_address_update_fixed_address_type_reserved_name_and_comment_empty(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address type RESERVED has name and comment set to empty string."""
        nb_ipaddress_atrs = {
            "has_fixed_address": True,
            "fixed_address_name": "",
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
                "fixed_address_name": "server1.local.test.net",
                "fixed_address_comment": "description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"name": "", "comment": ""}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
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
    def test_ip_address_update_fixed_address_type_mac_update_mac(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address type MAC has MAC address updated."""
        nb_ipaddress_atrs = {
            "dns_name": "server1.local.test.net",
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
                "dns_name": "server1.local.test.net",
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
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
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
    def test_ip_address_update_fixed_address_type_mac_name_and_comment(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address type MAC has name and comment updated."""
        nb_ipaddress_atrs = {
            "fixed_address_name": "server2.local.test.net",
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
                "fixed_address_name": "server1.local.test.net",
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
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
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
    def test_ip_address_update_fixed_address_type_mac_name_and_comment_empty(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address type MAC has name and comment set to empty string."""
        nb_ipaddress_atrs = {
            "has_fixed_address": True,
            "fixed_address_name": "",
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
                "fixed_address_name": "server1.local.test.net",
                "fixed_address_comment": "description",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"name": "", "comment": ""}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()

    ###########################
    # DNS Record Update tests
    ###########################

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_host_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure only Host record is updated."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_host_record": True, "has_fixed_address": False}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": True,
                "host_record_ref": "record:host/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
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
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_create_host_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure Host record is created during update if one doesn't exist. This can happen if fixed address currently exist and config was updated to enable host record creation."""
        nb_ipaddress_atrs = {"dns_name": "server1.local.test.net", "has_host_record": True, "has_fixed_address": False}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": False,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_host_record.assert_called_once()
            infoblox_adapter.conn.create_host_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
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
    def test_ip_address_update_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure only A record is updated."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_a_record": True, "has_fixed_address": False}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": True,
                "a_record_ref": "record:a/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
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
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_create_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure A record is created during update if one doesn't exist. This can happen if fixed address currently exist and config was updated to enable A record creation."""
        nb_ipaddress_atrs = {"dns_name": "server1.local.test.net", "has_a_record": True, "has_fixed_address": False}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": False,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
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
    def test_ip_address_update_create_ptr_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure PTR record is created if one doesn't currently exist."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "has_a_record": True,
            "has_ptr_record": True,
            "has_fixed_address": False,
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
            inf_ipaddress_atrs = {
                "dns_name": "server2.local.test.net",
                "has_a_record": True,
                "has_ptr_record": False,
                "a_record_ref": "record:a/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", comment="Test IPAddress", network_view="default"
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
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
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_a_and_ptr_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure A and PTR records are updated."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "has_a_record": True,
            "has_ptr_record": True,
            "has_fixed_address": False,
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
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
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": True,
                "has_ptr_record": True,
                "a_record_ref": "record:a/xyz",
                "ptr_record_ref": "record:ptr/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_ptr_record.assert_called_once()
            infoblox_adapter.conn.update_ptr_record.assert_called_with(
                ref="record:ptr/xyz", data={"ptrdname": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_a_record.assert_called_once()
            infoblox_adapter.conn.update_a_record.assert_called_with(
                ref="record:a/xyz", data={"name": "server2.local.test.net"}
            )
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
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fail_a_and_host_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure update fails if an A record is marked for update but Infoblox already has a Host record."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_a_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": True,
                "host_record_ref": "record:host/xyz",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()

            log_msg = "Cannot update A Record for IP Address, 10.0.0.1. It already has an existing Host Record."
            job_logger.warning.assert_called_with(log_msg)
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fail_ptr_and_host_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure update fails if PTR record is marked for update but Infoblox already has a Host record."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_ptr_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": True,
                "host_record_ref": "record:host/xyz",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()

            log_msg = (
                "Cannot create/update PTR Record for IP Address, 10.0.0.1. It already has an existing Host Record."
            )
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fail_host_and_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure update fails if Host record is marked for update but Infoblox already has an A record."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_host_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": True,
                "a_record_ref": "record:a/xyz",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()

            log_msg = "Cannot update Host Record for IP Address, 10.0.0.1. It already has an existing A Record."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fail_host_and_ptr_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure update fails if Host record is marked for update but Infoblox already has a PTR record."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_host_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_ptr_record": True,
                "ptr_record_ref": "record:ptr/xyz",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
            mock_validate_dns_name.assert_called_once()

            log_msg = "Cannot update Host Record for IP Address, 10.0.0.1. It already has an existing PTR Record."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_no_dns_updates(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure DNS update/create is not trigerred if user configures DONT_CREATE_RECORD for dns_record_type."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_a_record": True, "has_ptr_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
            self.config.dns_record_type = DNSRecordTypeChoices.DONT_CREATE_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            job_logger = Mock()
            infoblox_adapter.job.logger = job_logger
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": True,
                "has_ptr_record": True,
                "a_record_ref": "record:a/xyz",
                "ptr_record_ref": "record:ptr/xyz",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_fixed_address.assert_not_called()

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
    def test_ip_address_update_create_fixed_address_reserved(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure Fixed Address Reserved is created with DNS record in place, no FA in Infoblox, and config asking for Reserved IP creation."""
        nb_ipaddress_atrs = {
            "has_a_record": True,
            "has_fixed_address": True,
            "fixed_address_name": "FixedAddresReserved",
            "fixed_address_comment": "Fixed Address Reservation",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_a_record": True,
                "has_fixed_address": False,
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_fixed_address.assert_called_once()
            infoblox_adapter.conn.create_fixed_address.assert_called_with(
                ip_address="10.0.0.1",
                name="FixedAddresReserved",
                comment="Fixed Address Reservation",
                match_client="RESERVED",
                network_view="default",
            )
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
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
    def test_ip_address_update_create_fixed_address_mac(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure Fixed Address MAC is created with DNS record in place, no FA in Infoblox, and config asking for MAC IP creation."""
        nb_ipaddress_atrs = {
            "has_a_record": True,
            "mac_address": "52:1f:83:d4:9a:2e",
            "has_fixed_address": True,
            "fixed_address_name": "FixedAddresReserved",
            "fixed_address_comment": "Fixed Address Reservation",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "has_a_record": True,
                "has_fixed_address": False,
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_fixed_address.assert_called_once()
            infoblox_adapter.conn.create_fixed_address.assert_called_with(
                ip_address="10.0.0.1",
                name="FixedAddresReserved",
                mac_address="52:1f:83:d4:9a:2e",
                comment="Fixed Address Reservation",
                match_client="MAC_ADDRESS",
                network_view="default",
            )
            infoblox_adapter.conn.update_fixed_address.assert_not_called()
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()

    ##############
    # Update Fixed Address and Update/Create DNS Record
    ##############

    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.models.infoblox.validate_dns_name",
        autospec=True,
        return_value=True,
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot.NautobotMixin.tag_involved_objects",
        autospec=True,
    )
    def test_ip_address_update_fixed_address_reservation_and_host_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address RESERVED and Host records are updated together."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_host_record": True,
            "fixed_address_name": "new fa name",
            "fixed_address_comment": "new fa comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": True,
                "has_fixed_address": True,
                "host_record_ref": "record:host/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "description": "old description",
                "fixed_address_name": "old fa name",
                "fixed_address_comment": "old fa comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.update_host_record.assert_called_once()
            infoblox_adapter.conn.update_host_record.assert_called_with(
                ref="record:host/xyz", data={"comment": "new description", "name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "new fa comment", "name": "new fa name"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fixed_address_reservation_and_a_and_ptr_records(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address RESERVED and A+PTR records are updated together."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_a_record": True,
            "has_ptr_record": True,
            "fixed_address_name": "new fa name",
            "fixed_address_comment": "new fa comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": True,
                "has_ptr_record": True,
                "has_fixed_address": True,
                "a_record_ref": "record:a/xyz",
                "ptr_record_ref": "record:ptr/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "description": "old description",
                "fixed_address_name": "old fa name",
                "fixed_address_comment": "old fa comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.update_a_record.assert_called_once()
            infoblox_adapter.conn.update_a_record.assert_called_with(
                ref="record:a/xyz", data={"comment": "new description", "name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_ptr_record.assert_called_once()
            infoblox_adapter.conn.update_ptr_record.assert_called_with(
                ref="record:ptr/xyz", data={"comment": "new description", "ptrdname": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "new fa comment", "name": "new fa name"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fixed_address_mac_and_host_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address MAC and Host records are updated together."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_host_record": True,
            "fixed_address_name": "new fa name",
            "fixed_address_comment": "new fa comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": True,
                "has_fixed_address": True,
                "host_record_ref": "record:host/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
                "description": "old description",
                "fixed_address_name": "old fa name",
                "fixed_address_comment": "old fa comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.update_host_record.assert_called_once()
            infoblox_adapter.conn.update_host_record.assert_called_with(
                ref="record:host/xyz", data={"comment": "new description", "name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "new fa comment", "name": "new fa name"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fixed_address_mac_and_a_and_ptr_records(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address MAC and A+PTR records are updated together."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_a_record": True,
            "has_ptr_record": True,
            "fixed_address_name": "new fa name",
            "fixed_address_comment": "new fa comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": True,
                "has_ptr_record": True,
                "has_fixed_address": True,
                "a_record_ref": "record:a/xyz",
                "ptr_record_ref": "record:ptr/xyz",
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
                "description": "old description",
                "fixed_address_name": "old fa name",
                "fixed_address_comment": "old fa comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.update_a_record.assert_called_once()
            infoblox_adapter.conn.update_a_record.assert_called_with(
                ref="record:a/xyz", data={"comment": "new description", "name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_ptr_record.assert_called_once()
            infoblox_adapter.conn.update_ptr_record.assert_called_with(
                ref="record:ptr/xyz", data={"comment": "new description", "ptrdname": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "new fa comment", "name": "new fa name"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fixed_address_reservation_and_create_host_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address RESERVED is updated and Host record is created."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_host_record": True,
            "fixed_address_name": "new fa name",
            "fixed_address_comment": "new fa comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": False,
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "description": "old description",
                "fixed_address_name": "old fa name",
                "fixed_address_comment": "old fa comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_host_record.assert_called_once()
            infoblox_adapter.conn.create_host_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", comment="new description", network_view="default"
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "new fa comment", "name": "new fa name"}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fixed_address_reservation_and_create_a_and_ptr_records(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address RESERVED is updated and A+PTR records are created."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_a_record": True,
            "has_ptr_record": True,
            "fixed_address_name": "new fa name",
            "fixed_address_comment": "new fa comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": False,
                "has_ptr_record": False,
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "RESERVED",
                "description": "old description",
                "fixed_address_name": "old fa name",
                "fixed_address_comment": "old fa comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", comment="new description", network_view="default"
            )
            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", comment="new description", network_view="default"
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "new fa comment", "name": "new fa name"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_mac_address_reservation_and_create_host_record(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address MAC is updated and Host record is created."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_host_record": True,
            "fixed_address_name": "ReservedIP2",
            "fixed_address_comment": "New Comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_host_record": False,
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
                "description": "old description",
                "fixed_address_name": "ReservedIP1",
                "fixed_address_comment": "Old Comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_host_record.assert_called_once()
            infoblox_adapter.conn.create_host_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", comment="new description", network_view="default"
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "New Comment", "name": "ReservedIP2"}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_a_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
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
    def test_ip_address_update_fixed_address_mac_and_create_a_and_ptr_records(
        self, mock_tag_involved_objects, mock_validate_dns_name
    ):
        """Ensure Fixed Address MAC is updated and A+PTR records are created."""
        nb_ipaddress_atrs = {
            "dns_name": "server2.local.test.net",
            "description": "new description",
            "has_fixed_address": True,
            "has_a_record": True,
            "has_ptr_record": True,
            "fixed_address_name": "new fa name",
            "fixed_address_comment": "new fa comment",
        }
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
            self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
            infoblox_adapter = InfobloxAdapter(conn=mock_client, config=self.config)
            infoblox_adapter.job = Mock()
            inf_ds_namespace = infoblox_adapter.namespace(
                name="Global",
                ext_attrs={},
            )
            infoblox_adapter.add(inf_ds_namespace)
            inf_ipaddress_atrs = {
                "dns_name": "server1.local.test.net",
                "has_a_record": False,
                "has_ptr_record": False,
                "has_fixed_address": True,
                "fixed_address_ref": "fixedaddress/xyz",
                "fixed_address_type": "MAC_ADDRESS",
                "description": "old description",
                "fixed_address_name": "old fa name",
                "fixed_address_comment": "old fa comment",
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_a_record.assert_called_once()
            infoblox_adapter.conn.create_a_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", comment="new description", network_view="default"
            )
            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", comment="new description", network_view="default"
            )
            infoblox_adapter.conn.update_fixed_address.assert_called_once()
            infoblox_adapter.conn.update_fixed_address.assert_called_with(
                ref="fixedaddress/xyz", data={"comment": "new fa comment", "name": "new fa name"}
            )
            infoblox_adapter.conn.create_host_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
            )
