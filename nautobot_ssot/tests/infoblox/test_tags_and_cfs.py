"""Tests covering use of tags and custom fields in the plugin."""

import datetime
from unittest.mock import Mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models import CustomField, Status, Tag
from nautobot.ipam.models import VLAN, IPAddress, Prefix, VLANGroup

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter


class TestTagging(TestCase):
    """Tests ensuring tagging is applied to objects synced from and to Infoblox."""

    def setUp(self):
        "Test class set up."
        self.tag_sync_from_infoblox = Tag.objects.get(name="SSoT Synced from Infoblox")
        self.tag_sync_to_infoblox = Tag.objects.get(name="SSoT Synced to Infoblox")

    def test_tags_have_correct_content_types_set(self):
        """Ensure tags have correct content types configured."""
        for model in (IPAddress, Prefix, VLAN):
            content_type = ContentType.objects.get_for_model(model)
            self.assertIn(content_type, self.tag_sync_from_infoblox.content_types.all())
            self.assertIn(content_type, self.tag_sync_to_infoblox.content_types.all())

    def test_objects_synced_from_infoblox_are_tagged(self):
        """Ensure objects synced from Infoblox have 'SSoT Synced from Infoblox' tag applied."""
        nb_diffsync = NautobotAdapter()
        nb_diffsync.job = Mock()
        nb_diffsync.load()

        infoblox_adapter = InfobloxAdapter(conn=Mock())

        ds_prefix = infoblox_adapter.prefix(
            network="10.0.0.0/8",
            description="Test Network",
            network_type="network",
            status="Active",
        )
        infoblox_adapter.add(ds_prefix)
        ds_ipaddress = infoblox_adapter.ipaddress(
            description="Test IPAddress",
            address="10.0.0.1",
            status="Active",
            dns_name="",
            prefix="10.0.0.0/8",
            prefix_length=8,
            ip_addr_type="host",
        )
        infoblox_adapter.add(ds_ipaddress)
        ds_vlangroup = infoblox_adapter.vlangroup(
            name="TestVLANGroup",
            description="",
        )
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

        nb_diffsync.sync_from(infoblox_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8")
        self.assertEqual(prefix.tags.all()[0], self.tag_sync_from_infoblox)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8")
        self.assertEqual(ipaddress.tags.all()[0], self.tag_sync_from_infoblox)

        vlan = VLAN.objects.get(vid=750)
        self.assertEqual(vlan.tags.all()[0], self.tag_sync_from_infoblox)

    def test_objects_synced_to_infoblox_are_tagged(self):
        """Ensure objects synced to Infoblox have 'SSoT Synced to Infoblox' tag applied."""
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

        nautobot_adapter = NautobotAdapter()
        nautobot_adapter.job = Mock()
        nautobot_adapter.load()

        infoblox_adapter = InfobloxAdapter(conn=Mock())
        infoblox_adapter.job = Mock()
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
        self.cf_synced_to_infoblox = CustomField.objects.get(key="ssot_synced_to_infoblox")

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

        nautobot_adapter = NautobotAdapter()
        nautobot_adapter.job = Mock()
        nautobot_adapter.load()

        conn = Mock()
        infoblox_adapter = InfobloxAdapter(conn=conn)
        infoblox_adapter.job = Mock()
        nautobot_adapter.sync_to(infoblox_adapter)

        prefix = Prefix.objects.get(network="10.0.0.0", prefix_length="8")
        self.assertEqual(prefix.cf["ssot_synced_to_infoblox"], self.today)

        ipaddress = IPAddress.objects.get(address="10.0.0.1/8")
        self.assertEqual(ipaddress.cf["ssot_synced_to_infoblox"], self.today)

        vlangroup = VLANGroup.objects.get(name="TestVLANGroup")
        self.assertEqual(vlangroup.cf["ssot_synced_to_infoblox"], self.today)

        vlan = VLAN.objects.get(vid=750)
        self.assertEqual(vlan.cf["ssot_synced_to_infoblox"], self.today)
