# pylint: disable=too-many-lines,too-many-public-methods,R0801
"""Unit tests for the Infoblox Diffsync models."""

from unittest.mock import Mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Relationship, RelationshipAssociation, Role, Status, Tag
from nautobot.ipam.models import VLAN, IPAddress, Namespace, Prefix, VLANGroup
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.infoblox.choices import (
    DNSRecordTypeChoices,
    FixedAddressTypeChoices,
    NautobotDeletableModelChoices,
)
from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.infoblox.diffsync.models.nautobot import process_ext_attrs
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
        self.location_type, _ = LocationType.objects.get_or_create(name="Test LocationType 1")
        self.location_type.content_types.add(ContentType.objects.get_for_model(Prefix))
        self.location, _ = Location.objects.get_or_create(
            name="Test Location 1", location_type=self.location_type, status=self.status_active
        )
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
        inf_network_atrs = {
            "network_type": "network",
            "namespace": "dev",
            "ext_attrs": {"location": self.location.name},
        }
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True)
        with self.captureOnCommitCallbacks(execute=True):
            nb_adapter.load()
            self.infoblox_adapter.sync_to(nb_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8", namespace__name="dev")

        self.assertEqual("10.0.0.0/8", str(prefix.prefix))
        self.assertEqual("dev", prefix.namespace.name)
        self.assertEqual("Active", prefix.status.name)
        self.assertEqual("TestNetwork", prefix.description)
        self.assertEqual("network", prefix.type)
        self.assertIn(self.tag_sync_from_infoblox, prefix.tags.all())
        self.assertQuerysetEqualAndNotEmpty([self.location], prefix.locations.all())

    def test_network_update_network(self):
        """Validate network gets updated, including VLAN relationships."""
        # Create VLAN and VLANGroup for testing the relationship
        vg, _ = VLANGroup.objects.get_or_create(name="Test Group", location=self.location)
        vlan, _ = VLAN.objects.get_or_create(vid=10, name="Test VLAN", vlan_group=vg, status=self.status_active)

        # Add VLAN and VLANGroup to infoblox_adapter to prevent them from being deleted during sync
        inf_ds_vlangroup = self.infoblox_adapter.vlangroup(name="Test Group", description="", ext_attrs={})
        self.infoblox_adapter.add(inf_ds_vlangroup)
        inf_ds_vlan = self.infoblox_adapter.vlan(
            vid=10,
            name="Test VLAN",
            vlangroup="Test Group",
            status="ASSIGNED",
            description="",
            ext_attrs={},
        )
        self.infoblox_adapter.add(inf_ds_vlan)

        inf_network_atrs = {
            "network_type": "network",
            "namespace": "dev",
            "ext_attrs": {"vlan": "10"},
            "description": "New description",
            "vlans": {"10": {"vid": 10, "name": "Test VLAN", "group": "Test Group"}},
        }
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="Old description",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True, logger=Mock())
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8", namespace__name="dev")

        self.assertEqual("10.0.0.0/8", str(prefix.prefix))
        self.assertEqual("dev", prefix.namespace.name)
        self.assertEqual("Active", prefix.status.name)
        self.assertEqual("New description", prefix.description)
        self.assertEqual("network", prefix.type)
        self.assertEqual({"vlan": "10"}, prefix.custom_field_data)

        # Verify RelationshipAssociation is created (Regression test for line 258 fix)
        rel = Relationship.objects.get(label="Prefix -> VLAN")
        assoc = RelationshipAssociation.objects.filter(relationship=rel, source_id=prefix.id, destination_id=vlan.id)
        self.assertTrue(assoc.exists())
        self.assertTrue(
            any(
                "Adding VLAN" in call.args[0]
                for call in nb_adapter.job.logger.debug.call_args_list
                if call.args and isinstance(call.args[0], str)
            )
        )

    def test_network_update_network_vlan_not_found(self):
        """Validate network update handles missing VLAN gracefully."""
        # Ensure vlan_map is populated while the requested VLAN remains missing.
        vg, _ = VLANGroup.objects.get_or_create(name="Test Group", location=self.location)
        VLAN.objects.get_or_create(vid=10, name="Existing VLAN", vlan_group=vg, status=self.status_active)

        # Keep existing VLAN objects present in source to avoid unrelated delete paths.
        inf_ds_vlangroup = self.infoblox_adapter.vlangroup(name="Test Group", description="", ext_attrs={})
        self.infoblox_adapter.add(inf_ds_vlangroup)
        inf_ds_vlan = self.infoblox_adapter.vlan(
            vid=10,
            name="Existing VLAN",
            vlangroup="Test Group",
            status="ASSIGNED",
            description="",
            ext_attrs={},
        )
        self.infoblox_adapter.add(inf_ds_vlan)

        inf_network_atrs = {
            "network_type": "network",
            "namespace": "dev",
            "vlans": {"20": {"vid": 20, "name": "Missing VLAN", "group": "Test Group"}},
        }
        inf_ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(inf_ds_network)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True, logger=Mock())
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8", namespace__name="dev")
        rel = Relationship.objects.get(label="Prefix -> VLAN")
        self.assertFalse(RelationshipAssociation.objects.filter(relationship=rel, source_id=prefix.id).exists())
        self.assertTrue(
            any(
                "Unable to find VLAN" in call.args[0]
                for call in nb_adapter.job.logger.debug.call_args_list
                if call.args and isinstance(call.args[0], str)
            )
        )

    def test_network_update_network_no_debug(self):
        """Validate network gets updated when debug is disabled (Regression test for Truthy Mock)."""
        vg, _ = VLANGroup.objects.get_or_create(name="Test Group", location=self.location)
        VLAN.objects.get_or_create(vid=10, name="Test VLAN", vlan_group=vg, status=self.status_active)

        # Add necessary objects to source adapter to prevent them from being deleted during sync
        inf_ds_vlangroup = self.infoblox_adapter.vlangroup(name="Test Group", description="", ext_attrs={})
        self.infoblox_adapter.add(inf_ds_vlangroup)
        inf_ds_vlan = self.infoblox_adapter.vlan(
            vid=10, name="Test VLAN", vlangroup="Test Group", status="ASSIGNED", description="", ext_attrs={}
        )
        self.infoblox_adapter.add(inf_ds_vlan)

        inf_network_atrs = {
            "network_type": "network",
            "namespace": "dev",
            "description": "No debug update",
            "vlans": {"10": {"vid": 10, "name": "Test VLAN", "group": "Test Group"}},
        }
        ds_network = self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs))
        self.infoblox_adapter.add(ds_network)

        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            status=self.status_active,
            type="network",
            description="Old description",
            namespace=self.namespace_dev,
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=False)
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8", namespace__name="dev")
        self.assertEqual("No debug update", prefix.description)
        rel = Relationship.objects.get(label="Prefix -> VLAN")
        self.assertTrue(RelationshipAssociation.objects.filter(relationship=rel, source_id=prefix.id).exists())

    def test_network_create_network_with_ranges_and_partial_vlan_map(self):
        """Validate network create handles ranges and partially missing VLAN mappings."""
        vg, _ = VLANGroup.objects.get_or_create(name="Create Group", location=self.location)
        vlan, _ = VLAN.objects.get_or_create(vid=30, name="Create VLAN", vlan_group=vg, status=self.status_active)

        # Keep source VLAN objects to avoid unrelated delete paths in sync.
        self.infoblox_adapter.add(self.infoblox_adapter.vlangroup(name="Create Group", description="", ext_attrs={}))
        self.infoblox_adapter.add(
            self.infoblox_adapter.vlan(
                vid=30,
                name="Create VLAN",
                vlangroup="Create Group",
                status="ASSIGNED",
                description="",
                ext_attrs={},
            )
        )

        inf_network_atrs = {
            "network_type": "network",
            "namespace": "dev",
            "ranges": ["10.0.0.10-10.0.0.20"],
            "vlans": {
                "30": {"vid": 30, "name": "Create VLAN", "group": "Create Group"},
                "999": {"vid": 999, "name": "Missing VLAN", "group": "Missing Group"},
            },
        }
        self.infoblox_adapter.add(self.infoblox_adapter.prefix(**_get_network_dict(inf_network_atrs)))

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True, logger=Mock())
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8", namespace__name="dev")
        rel = Relationship.objects.get(label="Prefix -> VLAN")
        assoc = RelationshipAssociation.objects.filter(relationship=rel, source_id=prefix.id, destination_id=vlan.id)

        self.assertEqual("10.0.0.10-10.0.0.20", prefix.custom_field_data.get("dhcp_ranges"))
        self.assertTrue(assoc.exists())
        self.assertTrue(
            any(
                "Unable to find VLAN 999 Missing VLAN in Missing Group" in call.args[0]
                for call in nb_adapter.job.logger.warning.call_args_list
                if call.args and isinstance(call.args[0], str)
            )
        )


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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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
        nb_adapter.job = Mock(debug=True)
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


class TestModelNautobotVlanGroupNamespaceVlan(TestCase):
    """Tests VLANGroup, Namespace and VLAN model update/delete behaviors."""

    def setUp(self):
        """Test class set up."""
        create_prefix_relationship()
        self.config = create_default_infoblox_config()
        self.config.infoblox_sync_filters = [{"network_view": "default"}, {"network_view": "dev"}]
        self.config.infoblox_network_view_to_namespace_map = {"default": "Global", "dev": "dev"}

        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.status_deprecated, _ = Status.objects.get_or_create(name="Deprecated")
        self.status_reserved, _ = Status.objects.get_or_create(name="Reserved")
        for status in [self.status_active, self.status_deprecated, self.status_reserved]:
            status.content_types.add(ContentType.objects.get_for_model(VLAN))

        self.location_type, _ = LocationType.objects.get_or_create(name="Test LocationType 2")
        self.location_type.content_types.add(ContentType.objects.get_for_model(VLAN))
        self.location_type.content_types.add(ContentType.objects.get_for_model(VLANGroup))
        self.location, _ = Location.objects.get_or_create(
            name="Test Location 2", location_type=self.location_type, status=self.status_active
        )

        Namespace.objects.get_or_create(name="Global")
        Namespace.objects.get_or_create(name="dev")
        self.infoblox_adapter = InfobloxAdapter(conn=Mock(), config=self.config)

    def _add_source_namespaces(self, include_dev=True):
        """Add source namespaces used in most sync scenarios."""
        self.infoblox_adapter.add(self.infoblox_adapter.namespace(name="Global", ext_attrs={}))
        if include_dev:
            self.infoblox_adapter.add(self.infoblox_adapter.namespace(name="dev", ext_attrs={}))

    def test_vlangroup_update_ext_attrs(self):
        """Validate VLANGroup update applies ext attrs via sync."""
        self._add_source_namespaces(include_dev=True)
        VLANGroup.objects.get_or_create(name="VG-Update")

        ds_vlangroup = self.infoblox_adapter.vlangroup(
            name="VG-Update", description="", ext_attrs={"department": "Network"}
        )
        self.infoblox_adapter.add(ds_vlangroup)

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True)
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        self.assertTrue(VLANGroup.objects.filter(name="VG-Update").exists())
        self.assertTrue(CustomField.objects.filter(key="department").exists())

    def test_vlangroup_delete(self):
        """Validate VLANGroup object is deleted when absent from source."""
        self._add_source_namespaces(include_dev=True)
        VLANGroup.objects.get_or_create(name="VG-To-Delete")

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True)
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        self.assertFalse(VLANGroup.objects.filter(name="VG-To-Delete").exists())

    def test_namespace_update_ext_attrs(self):
        """Validate Namespace update applies ext attrs via sync."""
        self._add_source_namespaces(include_dev=False)
        ds_namespace = self.infoblox_adapter.namespace(name="dev", ext_attrs={"department": "Engineering"})
        self.infoblox_adapter.add(ds_namespace)

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True)
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        namespace = Namespace.objects.get(name="dev")
        self.assertEqual("Engineering", namespace.custom_field_data.get("department"))

    def test_namespace_delete_not_allowed(self):
        """Validate Namespace delete path raises NotImplementedError."""
        self._add_source_namespaces(include_dev=False)

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True)
        nb_adapter.load()

        with self.assertRaises(NotImplementedError):
            self.infoblox_adapter.sync_to(nb_adapter)

    def test_vlan_update_status_description_ext_attrs_and_group_location(self):
        """Validate VLAN update applies mapped status, description, ext attrs and group location."""
        self._add_source_namespaces(include_dev=True)
        vg, _ = VLANGroup.objects.get_or_create(name="VG-VLAN-Update")
        VLAN.objects.get_or_create(
            vid=200,
            name="VLAN200",
            vlan_group=vg,
            defaults={
                "status": self.status_deprecated,
                "description": "Old VLAN description",
                "location": self.location,
            },
        )

        self.infoblox_adapter.add(self.infoblox_adapter.vlangroup(name="VG-VLAN-Update", description="", ext_attrs={}))
        self.infoblox_adapter.add(
            self.infoblox_adapter.vlan(
                vid=200,
                name="VLAN200",
                vlangroup="VG-VLAN-Update",
                status="ASSIGNED",
                description="Updated VLAN description",
                ext_attrs={"department": "Operations"},
            )
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True)
        nb_adapter.load()
        self.infoblox_adapter.sync_to(nb_adapter)

        vlan = VLAN.objects.get(vid=200, name="VLAN200", vlan_group__name="VG-VLAN-Update")
        vg.refresh_from_db()
        self.assertEqual("Active", vlan.status.name)
        self.assertEqual("Updated VLAN description", vlan.description)
        self.assertEqual("Operations", vlan.custom_field_data.get("department"))
        self.assertEqual(self.location.id, vg.location_id)


class TestModelNautobotBranchMatrix(TestCase):
    """Additional branch-matrix tests for Infoblox Nautobot model coverage."""

    def setUp(self):
        """Test class set up."""
        create_prefix_relationship()
        self.config = create_default_infoblox_config()
        self.config.infoblox_sync_filters = [{"network_view": "default"}, {"network_view": "dev"}]
        self.config.infoblox_network_view_to_namespace_map = {"default": "Global", "dev": "dev"}

        self.namespace_dev, _ = Namespace.objects.get_or_create(name="dev")
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.infoblox_adapter = InfobloxAdapter(conn=Mock(), config=self.config)

    def _base_prefix(self, prefix="10.99.0.0/24"):
        """Create a base prefix for IP and ext-attr tests."""
        pfx = Prefix(
            prefix=prefix,
            status=self.status_active,
            type="network",
            namespace=self.namespace_dev,
            description="Branch Matrix Prefix",
        )
        pfx.validated_save()
        return pfx

    def test_process_ext_attrs_success_matrix_for_ip(self):
        """Validate process_ext_attrs success branches for role/tenant/custom-field mapping."""
        prefix = self._base_prefix()
        tenant = Tenant(name="Tenant Matrix")
        tenant.validated_save()
        role = Role(name="Matrix IP Role")
        role.validated_save()

        ip = IPAddress(address="10.99.0.1/24", status=self.status_active, type="host", parent=prefix)
        ip.validated_save()

        adapter = Mock()
        adapter.job = Mock(logger=Mock())
        adapter.tenant_map = {"Tenant Matrix": tenant.id}
        adapter.role_map = {"Matrix IP Role": role.id}
        adapter.location_map = {}
        adapter.vrf_map = {}

        process_ext_attrs(
            adapter=adapter,
            obj=ip,
            extattrs={
                "role": "Matrix IP Role",
                "tenant": "Tenant Matrix",
                "department": "Operations",
            },
        )

        self.assertEqual(role.id, ip.role_id)
        self.assertEqual(tenant.id, ip.tenant_id)
        self.assertEqual("Operations", ip.custom_field_data.get("department"))

    def test_process_ext_attrs_warning_matrix_for_prefix(self):
        """Validate process_ext_attrs warning branches for missing maps and unhashable values."""
        prefix = self._base_prefix(prefix="10.99.1.0/24")

        adapter = Mock()
        adapter.job = Mock(logger=Mock())
        adapter.location_map = {}
        adapter.vrf_map = {}
        adapter.role_map = {}
        adapter.tenant_map = {}

        process_ext_attrs(
            adapter=adapter,
            obj=prefix,
            extattrs={
                "location": "Missing Location",
                "vrf": ["Missing VRF"],
                "role": ["Role One", "Role Two"],
                "tenant": ["Tenant One"],
            },
        )

        self.assertGreaterEqual(adapter.job.logger.warning.call_count, 4)
        self.assertEqual("Missing Location", prefix.custom_field_data.get("location"))
        self.assertEqual("['Missing VRF']", prefix.custom_field_data.get("vrf"))
        self.assertEqual("['Role One', 'Role Two']", prefix.custom_field_data.get("role"))
        self.assertEqual("['Tenant One']", prefix.custom_field_data.get("tenant"))

    def test_dns_host_record_update_paths(self):
        """Validate Host record update both in configured and non-configured modes."""
        self.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
        prefix = self._base_prefix(prefix="10.99.2.0/24")
        IPAddress.objects.create(
            address="10.99.2.1/24",
            status=self.status_active,
            type="host",
            parent=prefix,
            dns_name="old-host.example.net",
            _custom_field_data={"dns_host_record_comment": "Old Host Comment"},
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True, logger=Mock())
        nb_adapter.load()

        host_record = next(iter(nb_adapter.get_all("dnshostrecord")))
        host_record.update({"dns_name": "new-host.example.net", "description": "New Host Comment"})

        ip = IPAddress.objects.get(address="10.99.2.1/24", parent__namespace__name="dev")
        self.assertEqual("new-host.example.net", ip.dns_name)
        self.assertEqual("New Host Comment", ip.custom_field_data.get("dns_host_record_comment"))

        host_record.adapter.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
        host_record.update({"dns_name": "ignored.example.net", "description": "Ignored"})
        self.assertTrue(host_record.adapter.job.logger.warning.called)

    def test_dns_ptr_record_update_paths(self):
        """Validate PTR record update both in configured and non-configured modes."""
        self.config.dns_record_type = DNSRecordTypeChoices.A_AND_PTR_RECORD
        prefix = self._base_prefix(prefix="10.99.3.0/24")
        IPAddress.objects.create(
            address="10.99.3.1/24",
            status=self.status_active,
            type="host",
            parent=prefix,
            dns_name="ptr.example.net",
            _custom_field_data={"dns_ptr_record_comment": "Old PTR Comment"},
        )

        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True, logger=Mock())
        nb_adapter.load()

        ptr_record = next(iter(nb_adapter.get_all("dnsptrrecord")))
        ptr_record.update({"description": "New PTR Comment"})

        ip = IPAddress.objects.get(address="10.99.3.1/24", parent__namespace__name="dev")
        self.assertEqual("New PTR Comment", ip.custom_field_data.get("dns_ptr_record_comment"))

        ptr_record.adapter.config.dns_record_type = DNSRecordTypeChoices.HOST_RECORD
        ptr_record.update({"description": "Ignored PTR"})
        self.assertTrue(ptr_record.adapter.job.logger.warning.called)

    def test_ip_address_update_branch_matrix(self):
        """Validate key IPAddress.update branch paths for fixed-address handling and fallbacks."""
        prefix = self._base_prefix(prefix="10.99.4.0/24")
        ip = IPAddress.objects.create(
            address="10.99.4.1/24",
            status=self.status_active,
            type="host",
            parent=prefix,
            description="Original Description",
            _custom_field_data={"fixed_address_comment": "Original Comment"},
        )

        self.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        nb_adapter = NautobotAdapter(config=self.config)
        nb_adapter.job = Mock(debug=True, logger=Mock())
        nb_adapter.load()

        ds_ip = next(iter(nb_adapter.get_all("ipaddress")))

        # Covers description=="" branch and fixed_address_comment update path.
        ds_ip.update({"description": "", "fixed_address_comment": "Cleared Comment"})
        ip.refresh_from_db()
        self.assertEqual("", ip.description)
        self.assertEqual("Cleared Comment", ip.custom_field_data.get("fixed_address_comment"))

        # Covers DONT_CREATE_RECORD guard branch.
        ds_ip.adapter.config.fixed_address_type = FixedAddressTypeChoices.DONT_CREATE_RECORD
        ds_ip.update({"description": "Blocked update"})
        ip.refresh_from_db()
        self.assertEqual("", ip.description)

        # Covers status fallback, invalid ip type fallback, and ext/cf update branches.
        ds_ip.adapter.config.fixed_address_type = FixedAddressTypeChoices.RESERVED
        ds_ip.update(
            {
                "status": "UnknownStatus",
                "ip_addr_type": "unsupported-type",
                "description": "Final Description",
                "ext_attrs": {"department": "Matrix Team"},
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "fixed_address_comment": "Final Comment",
            }
        )
        ip.refresh_from_db()
        self.assertEqual(self.config.default_status.id, ip.status_id)
        self.assertEqual("host", ip.type)
        self.assertEqual("Final Description", ip.description)
        self.assertEqual("aa:bb:cc:dd:ee:ff", ip.custom_field_data.get("mac_address"))
        self.assertEqual("Final Comment", ip.custom_field_data.get("fixed_address_comment"))
        self.assertEqual("Matrix Team", ip.custom_field_data.get("department"))
