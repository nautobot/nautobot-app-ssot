"""Unit tests for the Infoblox Diffsync models."""
import unittest
from unittest.mock import Mock

from django.test import TestCase

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter

from .fixtures_infoblox import create_default_infoblox_config


def _get_ip_address_dict(attrs):
    ipaddress_dict = dict(  # pylint: disable=use-dict-literal
        description="Test IPAddress",
        address="10.0.0.1",
        status="Active",
        prefix="10.0.0.0/8",
        prefix_length=8,
        ip_addr_type="host",
        namespace="Global",
        dns_name="",
    )
    ipaddress_dict.update(attrs)

    return ipaddress_dict


class TestModelInfobloxIPAddressCreate(TestCase):
    """Tests correct DNS record is created."""

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
    def test_ip_address_create_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Validate A Record is created."""
        nb_ipaddress_atrs = {"has_a_record": True, "dns_name": "server1.local.test.net"}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_a_record = True
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
                fqdn="server1.local.test.net", ip_address="10.0.0.1", network_view="default"
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
            self.config.create_host_record = False
            self.config.create_a_record = True
            self.config.create_ptr_record = True
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
                fqdn="server1.local.test.net", ip_address="10.0.0.1", network_view="default"
            )
            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server1.local.test.net", ip_address="10.0.0.1", network_view="default"
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
            self.config.create_host_record = True
            self.config.create_a_record = False
            self.config.create_ptr_record = False
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
                fqdn="server1.local.test.net", ip_address="10.0.0.1", network_view="default"
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
        """Ensure no record is created if DNS name is missing."""
        nb_ipaddress_atrs = {"has_a_record": True, "dns_name": ""}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_host_record = False
            self.config.create_a_record = True
            self.config.create_ptr_record = False
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
            log_msg = "Cannot create Infoblox record for IP Address 10.0.0.1. DNS name is not defined."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_not_called()


class TestModelInfobloxIPAddressUpdate(TestCase):
    """Tests validating IP Address Update scenarios."""

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
    def test_ip_address_update_host_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure Host record is updated."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_host_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_a_record = False
            self.config.create_ptr_record = False
            self.config.create_host_record = True
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
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_host_record.assert_called_once()
            infoblox_adapter.conn.update_host_record.assert_called_with(
                ref="record:host/xyz", data={"name": "server2.local.test.net"}
            )
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
    def test_ip_address_update_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure A record is updated."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_a_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_host_record = False
            self.config.create_a_record = True
            self.config.create_ptr_record = False
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
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_a_record.assert_called_once()
            infoblox_adapter.conn.update_a_record.assert_called_with(
                ref="record:a/xyz", data={"name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
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
    def test_ip_address_create_ptr_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure PTR record is created if one doesn't currently exist."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_a_record": True, "has_ptr_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_host_record = False
            self.config.create_a_record = True
            self.config.create_ptr_record = True
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
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)

            infoblox_adapter.conn.create_ptr_record.assert_called_once()
            infoblox_adapter.conn.create_ptr_record.assert_called_with(
                fqdn="server2.local.test.net", ip_address="10.0.0.1", network_view="default"
            )
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
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
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_a_record": True, "has_ptr_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_host_record = False
            self.config.create_a_record = True
            self.config.create_ptr_record = True
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
            }
            inf_ds_ipaddress = infoblox_adapter.ipaddress(**_get_ip_address_dict(inf_ipaddress_atrs))
            infoblox_adapter.add(inf_ds_ipaddress)
            self.nb_adapter.sync_to(infoblox_adapter)
            infoblox_adapter.conn.update_ptr_record.assert_called_once()
            infoblox_adapter.conn.update_ptr_record.assert_called_with(
                ref="record:ptr/xyz", data={"name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_a_record.assert_called_once()
            infoblox_adapter.conn.update_a_record.assert_called_with(
                ref="record:a/xyz", data={"name": "server2.local.test.net"}
            )
            infoblox_adapter.conn.update_host_record.assert_not_called()
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
    def test_ip_address_update_fail_host_and_a_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure update fails if an A record is marked for update but Infoblox already has a Host record."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_a_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_host_record = False
            self.config.create_a_record = True
            self.config.create_ptr_record = False
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
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()

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
            self.config.create_host_record = False
            self.config.create_a_record = True
            self.config.create_ptr_record = True
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
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()

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
    def test_ip_address_update_fail_a_and_host_record(self, mock_tag_involved_objects, mock_validate_dns_name):
        """Ensure update fails if Host record is marked for update but Infoblox already has an A record."""
        nb_ipaddress_atrs = {"dns_name": "server2.local.test.net", "has_host_record": True}
        nb_ds_ipaddress = self.nb_adapter.ipaddress(**_get_ip_address_dict(nb_ipaddress_atrs))
        self.nb_adapter.add(nb_ds_ipaddress)
        self.nb_adapter.load()

        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.config.create_host_record = True
            self.config.create_a_record = False
            self.config.create_ptr_record = False
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
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()

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
            self.config.create_host_record = True
            self.config.create_a_record = False
            self.config.create_ptr_record = False
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
            infoblox_adapter.conn.update_a_record.assert_not_called()
            infoblox_adapter.conn.update_host_record.assert_not_called()
            infoblox_adapter.conn.create_ptr_record.assert_not_called()
            infoblox_adapter.conn.update_ptr_record.assert_not_called()
            mock_validate_dns_name.assert_called_once()

            log_msg = "Cannot update Host Record for IP Address, 10.0.0.1. It already has an existing PTR Record."
            job_logger.warning.assert_called_with(log_msg)

            mock_tag_involved_objects.assert_called_once()
            mock_validate_dns_name.assert_called_once()
            mock_validate_dns_name.assert_called_with(
                infoblox_client=mock_client, dns_name="server2.local.test.net", network_view="default"
            )
