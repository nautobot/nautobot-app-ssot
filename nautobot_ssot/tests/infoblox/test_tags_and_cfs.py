"""Tests covering use of tags and custom fields in the plugin."""

import datetime
from unittest.mock import Mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Status, Tag
from nautobot.ipam.models import VLAN, IPAddress, Namespace, Prefix, VLANGroup

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices, FixedAddressTypeChoices
from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.tests.infoblox.fixtures_infoblox import create_prefix_relationship

from .fixtures_infoblox import create_default_infoblox_config


class TestTagging(TestCase):
    """Tests ensuring tagging is applied to objects synced from and to Infoblox."""

    def setUp(self):
        "Test class set up."
        self.tag_sync_from_infoblox, _ = Tag.objects.get_or_create(
            name="SSoT Synced from Infoblox",
            defaults={
                "name": "SSoT Synced from Infoblox",
                "description": "Object synced at some point from Infoblox",
                "color": "40bfae",
            },
        )
        for model in [IPAddress, Namespace, Prefix, VLAN]:
            self.tag_sync_from_infoblox.content_types.add(ContentType.objects.get_for_model(model))
        self.tag_sync_to_infoblox, _ = Tag.objects.get_or_create(
            name="SSoT Synced to Infoblox",
            defaults={
                "name": "SSoT Synced to Infoblox",
                "description": "Object synced at some point to Infoblox",
                "color": "40bfae",
            },
        )
        for model in [IPAddress, Prefix, VLAN]:
            self.tag_sync_to_infoblox.content_types.add(ContentType.objects.get_for_model(model))
        self.config = create_default_infoblox_config()

    def test_tags_have_correct_content_types_set(self):
        """Ensure tags have correct content types configured."""
        for model in (IPAddress, Prefix, VLAN):
            content_type = ContentType.objects.get_for_model(model)
            self.assertIn(content_type, self.tag_sync_to_infoblox.content_types.all())

        for model in (IPAddress, Namespace, Prefix, VLAN):
            content_type = ContentType.objects.get_for_model(model)
            self.assertIn(content_type, self.tag_sync_from_infoblox.content_types.all())

    def test_objects_synced_from_infoblox_are_tagged(self):
        """Ensure objects synced from Infoblox have 'SSoT Synced from Infoblox' tag applied."""
        self.config.dns_record_type = DNSRecordTypeChoices.A_RECORD
        self.config.fixed_address_type = FixedAddressTypeChoices.MAC_ADDRESS
        nautobot_adapter = NautobotAdapter(config=self.config)
        nautobot_adapter.job = Mock()
        nautobot_adapter.load()

        Namespace.objects.get_or_create(name="Global")

        infoblox_adapter = InfobloxAdapter(conn=Mock(), config=self.config)

        ds_namespace_global = infoblox_adapter.namespace(
            name="Global",
            ext_attrs={},
        )
        infoblox_adapter.add(ds_namespace_global)
        ds_namespace_dev = infoblox_adapter.namespace(
            name="dev",
            ext_attrs={},
        )
        infoblox_adapter.add(ds_namespace_dev)
        ds_prefix = infoblox_adapter.prefix(
            network="10.0.0.0/8",
            description="Test Network",
            network_type="network",
            ext_attrs={},
            vlans={},
            status="Active",
            namespace="Global",
        )
        infoblox_adapter.add(ds_prefix)
        ds_ipaddress = infoblox_adapter.ipaddress(
            description="Test IPAddress",
            address="10.0.0.1",
            status="Active",
            has_fixed_address=True,
            prefix="10.0.0.0/8",
            prefix_length=8,
            ip_addr_type="dhcp",
            ext_attrs={},
            namespace="Global",
        )
        infoblox_adapter.add(ds_ipaddress)
        ds_vlangroup = infoblox_adapter.vlangroup(name="TestVLANGroup", description="", ext_attrs={})
        infoblox_adapter.add(ds_vlangroup)
        ds_vlan = infoblox_adapter.vlan(
            vid=750,
            name="TestVLAN",
            description="Test VLAN",
            status="ASSIGNED",
            vlangroup="TestVLANGroup",
            ext_attrs={},
        )
        infoblox_adapter.add(ds_vlan)
        infoblox_adapter.sync_to(nautobot_adapter)

        namespace = Namespace.objects.get(name="dev")
        self.assertEqual(namespace.tags.all()[0], self.tag_sync_from_infoblox)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8")
        self.assertEqual(prefix.tags.all()[0], self.tag_sync_from_infoblox)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8")
        self.assertEqual(ipaddress.tags.all()[0], self.tag_sync_from_infoblox)

        vlan = VLAN.objects.get(vid=750)
        self.assertEqual(vlan.tags.all()[0], self.tag_sync_from_infoblox)

    def test_objects_synced_to_infoblox_are_tagged(self):
        """Ensure objects synced to Infoblox have 'SSoT Synced to Infoblox' tag applied."""
        create_prefix_relationship()
        nb_prefix = Prefix(
            network="10.0.0.0",
            prefix_length=8,
            description="Test Network",
            type="network",
            status=Status.objects.get_for_model(Prefix).first(),
        )
        nb_prefix.validated_save()
        nb_ipaddress = IPAddress(
            description="Test IPAddress",
            address="10.0.0.1/8",
            status=Status.objects.get_for_model(IPAddress).first(),
            type="host",
        )
        nb_ipaddress.validated_save()
        nb_vlangroup = VLANGroup(
            name="TestVLANGroup",
        )
        nb_vlangroup.validated_save()
        nb_vlan = VLAN(
            vid=750,
            name="VL750",
            description="Test VLAN",
            status=Status.objects.get_for_model(VLAN).first(),
            vlan_group=nb_vlangroup,
        )
        nb_vlan.validated_save()

        nautobot_adapter = NautobotAdapter(config=self.config)
        nautobot_adapter.job = Mock()
        nautobot_adapter.load()

        infoblox_adapter = InfobloxAdapter(conn=Mock(), config=self.config)
        infoblox_adapter.job = Mock()
        ds_namespace = infoblox_adapter.namespace(
            name="Global",
            ext_attrs={},
        )
        infoblox_adapter.add(ds_namespace)
        nautobot_adapter.sync_to(infoblox_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8")
        self.assertEqual(prefix.tags.all()[0], self.tag_sync_to_infoblox)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8")
        self.assertEqual(ipaddress.tags.all()[0], self.tag_sync_to_infoblox)

        vlan = VLAN.objects.get(vid=750)
        self.assertEqual(vlan.tags.all()[0], self.tag_sync_to_infoblox)


class TestCustomFields(TestCase):
    """Tests ensuring custom fields are updated for objects synced from and to Infoblox."""

    def setUp(self):
        """Test class set up."""
        self.today = datetime.date.today().isoformat()
        self.cf_synced_to_infoblox, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_DATE,
            key="ssot_synced_to_infoblox",
            defaults={
                "label": "Last synced to Infoblox on",
            },
        )
        for model in [IPAddress, Prefix, VLAN, VLANGroup]:
            self.cf_synced_to_infoblox.content_types.add(ContentType.objects.get_for_model(model))
        create_prefix_relationship()
        self.config = create_default_infoblox_config()

    def test_cfs_have_correct_content_types_set(self):
        """Ensure cfs have correct content types configured."""
        for model in (IPAddress, Prefix, VLAN, VLANGroup):
            content_type = ContentType.objects.get_for_model(model)
            self.assertIn(content_type, self.cf_synced_to_infoblox.content_types.all())

    def test_cf_updated_for_objects_synced_to_infoblox(self):
        """Ensure objects synced to Infoblox have cf 'ssot_synced_to_infoblox' correctly updated."""
        nb_prefix = Prefix(
            network="10.0.0.0",
            prefix_length=8,
            description="Test Network",
            type="network",
            status=Status.objects.get_for_model(Prefix).first(),
        )
        nb_prefix.validated_save()

        nb_ipaddress = IPAddress(
            description="Test IPAddress",
            address="10.0.0.1/8",
            status=Status.objects.get_for_model(IPAddress).first(),
            type="host",
        )
        nb_ipaddress.validated_save()

        nb_vlangroup = VLANGroup(
            name="TestVLANGroup",
        )
        nb_vlangroup.validated_save()
        nb_vlan = VLAN(
            vid=750,
            name="VL750",
            description="Test VLAN",
            status=Status.objects.get_for_model(VLAN).first(),
            vlan_group=nb_vlangroup,
        )
        nb_vlan.validated_save()

        nautobot_adapter = NautobotAdapter(config=self.config)
        nautobot_adapter.job = Mock()
        nautobot_adapter.load()

        conn = Mock()
        infoblox_adapter = InfobloxAdapter(conn=conn, config=self.config)
        infoblox_adapter.job = Mock()

        ds_namespace = infoblox_adapter.namespace(
            name="Global",
            ext_attrs={},
        )
        infoblox_adapter.add(ds_namespace)

        nautobot_adapter.sync_to(infoblox_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8")
        self.assertEqual(prefix.cf["ssot_synced_to_infoblox"], self.today)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8")
        self.assertEqual(ipaddress.cf["ssot_synced_to_infoblox"], self.today)

        vlangroup = VLANGroup.objects.get(name="TestVLANGroup")
        self.assertEqual(vlangroup.cf["ssot_synced_to_infoblox"], self.today)

        vlan = VLAN.objects.get(vid=750)
        self.assertEqual(vlan.cf["ssot_synced_to_infoblox"], self.today)
