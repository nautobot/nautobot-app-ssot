"""Tests for syncing a switchport's 802.1Q mode and the VLANs it carries.

The mapping from IP Fabric's switchport table to Nautobot's `mode`, `untagged_vlan` and
`tagged_vlans` is the subject, along with what happens to a VLAN ID the Location has no VLAN for.
"""

import unittest.mock
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.choices import InterfaceModeChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import VLAN

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import switchport_vlans, vlan_id_of
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import set_interface_vlans
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache, parse_vlan_ranges
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    NETWORKS_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)


class TestVlanRangeParsing(TestCase):
    """The trunk VLAN list is reported the way the device configures it."""

    def test_ranges_and_singles(self):
        for reported, expected in (
            ("110-119,999", [110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 999]),
            ("10", [10]),
            (" 3 , 4 ", [3, 4]),
            ("", []),
            (None, []),
        ):
            with self.subTest(reported=reported):
                self.assertEqual(parse_vlan_ranges(reported), expected)

    def test_a_part_that_is_not_a_vlan_is_skipped_rather_than_guessed_at(self):
        self.assertEqual(parse_vlan_ranges("5,junk,7"), [5, 7])
        self.assertEqual(parse_vlan_ranges("20-10"), [], "A range counting backwards names nothing.")

    def test_ids_outside_the_vlan_range_are_dropped(self):
        """Nautobot will not hold them, and 4095 is how some platforms say 'all'."""
        self.assertEqual(parse_vlan_ranges("4090-4100"), [4090, 4091, 4092, 4093, 4094])


class TestSwitchportMapping(TestCase):
    """What Nautobot mode and VLANs a switchport row describes."""

    def test_an_access_port_carries_one_untagged_vlan(self):
        self.assertEqual(
            switchport_vlans({"mode": "access", "accVlan": 10}),
            (InterfaceModeChoices.MODE_ACCESS, 10, []),
        )

    def test_a_trunk_carries_its_native_vlan_untagged_and_the_rest_tagged(self):
        self.assertEqual(
            switchport_vlans({"mode": "trunk", "nativeVlan": 1, "trunkVlan": "10,20"}),
            (InterfaceModeChoices.MODE_TAGGED, 1, [10, 20]),
        )

    def test_a_trunk_carrying_every_vlan_is_one_mode_rather_than_four_thousand_vlans(self):
        for reported in ("1-4094", "1-4095"):
            with self.subTest(reported=reported):
                self.assertEqual(
                    switchport_vlans({"mode": "trunk", "nativeVlan": 99, "trunkVlan": reported}),
                    (InterfaceModeChoices.MODE_TAGGED_ALL, 99, []),
                )

    def test_a_mode_nautobot_has_no_equivalent_for_is_refused(self):
        """Refused rather than guessed at, so the caller can report it."""
        for reported in ("dot1q-tunnel", "", None):
            with self.subTest(reported=reported):
                self.assertIsNone(switchport_vlans({"mode": reported}))

    def test_a_vlan_id_that_is_not_one_is_read_as_none(self):
        for reported in (None, "", "n/a", 0, 4095):
            with self.subTest(reported=reported):
                self.assertIsNone(vlan_id_of(reported))
        self.assertEqual(vlan_id_of("10"), 10, "IP Fabric may report the ID as a string.")


class _InterfaceVlanTestCase(TestCase):
    """A Device with an Interface at a Location that holds two VLANs."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="vlan-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="vlan-site")
        location_type.content_types.add(device_ct, ContentType.objects.get_for_model(VLAN))
        self.location = Location.objects.create(name="vlan-site1", location_type=location_type, status=self.active)
        manufacturer = Manufacturer.objects.create(name="vlan-vendor")
        device_type = DeviceType.objects.create(model="vlan-model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="vlan-dev1",
            status=self.active,
            role=role,
            location=self.location,
            device_type=device_type,
        )
        self.interface = Interface.objects.create(
            device=self.device, name="eth0", status=self.active, type="1000base-t"
        )
        self.vlans = {}
        for vid in (10, 20):
            vlan = VLAN.objects.create(name=f"vlan{vid}", vid=vid, status=self.active)
            vlan.locations.add(self.location)
            self.vlans[vid] = vlan


class TestWritingInterfaceVlans(_InterfaceVlanTestCase):
    """What `set_interface_vlans` puts on the Interface."""

    def write(self, mode, untagged_vid=None, tagged_vids=(), logger=None):
        """Set this test's Interface to the given mode and VLANs."""
        return set_interface_vlans(
            device_name=self.device.name,
            interface_name=self.interface.name,
            mode=mode,
            untagged_vid=untagged_vid,
            tagged_vids=tagged_vids,
            tagged_only=False,
            logger=logger,
        )

    def test_an_access_port_gets_its_mode_and_untagged_vlan(self):
        self.assertTrue(self.write(InterfaceModeChoices.MODE_ACCESS, untagged_vid=10))

        self.interface.refresh_from_db()
        self.assertEqual(self.interface.mode, InterfaceModeChoices.MODE_ACCESS)
        self.assertEqual(self.interface.untagged_vlan, self.vlans[10])

    def test_a_trunk_gets_its_tagged_vlans(self):
        self.assertTrue(self.write(InterfaceModeChoices.MODE_TAGGED, untagged_vid=10, tagged_vids=[20]))

        self.interface.refresh_from_db()
        self.assertEqual(self.interface.mode, InterfaceModeChoices.MODE_TAGGED)
        self.assertEqual(self.interface.untagged_vlan, self.vlans[10])
        self.assertEqual(list(self.interface.tagged_vlans.all()), [self.vlans[20]])

    def test_a_vlan_the_location_does_not_have_is_reported_and_left_out(self):
        """Nautobot has nothing to point the Interface at, which a Site Filter makes ordinary."""
        logger = unittest.mock.MagicMock()

        self.assertTrue(self.write(InterfaceModeChoices.MODE_TAGGED, untagged_vid=999, tagged_vids=[20, 998]))

        self.interface.refresh_from_db()
        self.assertIsNone(self.interface.untagged_vlan)
        self.assertEqual(list(self.interface.tagged_vlans.all()), [self.vlans[20]])

        logger = unittest.mock.MagicMock()
        self.write(InterfaceModeChoices.MODE_TAGGED, untagged_vid=999, tagged_vids=[998], logger=logger)
        reported = str(logger.warning.call_args_list)
        self.assertIn("999", reported)
        self.assertIn("998", reported)

    def test_clearing_takes_the_interface_out_of_802_1q_without_deleting_anything(self):
        self.write(InterfaceModeChoices.MODE_TAGGED, untagged_vid=10, tagged_vids=[20])

        self.assertTrue(self.write("", untagged_vid=None, tagged_vids=[]))

        self.interface.refresh_from_db()
        self.assertEqual(self.interface.mode, "")
        self.assertIsNone(self.interface.untagged_vlan)
        self.assertEqual(list(self.interface.tagged_vlans.all()), [])
        self.assertEqual(VLAN.objects.filter(vid__in=(10, 20)).count(), 2, "The VLANs themselves remain.")


class TestLoadingInterfaceVlans(_InterfaceVlanTestCase):
    """What the Nautobot adapter reads back."""

    def adapter(self):
        """Return a Nautobot adapter that has loaded this test's Device."""
        job = unittest.mock.MagicMock()
        job.debug = False
        adapter = NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS),
        )
        adapter.load_interface_vlans(Device.objects.filter(pk=self.device.pk))
        return adapter

    def test_an_interface_in_a_mode_is_loaded_with_its_vlans(self):
        self.interface.mode = InterfaceModeChoices.MODE_TAGGED
        self.interface.untagged_vlan = self.vlans[10]
        self.interface.validated_save()
        self.interface.tagged_vlans.add(self.vlans[20])

        loaded = self.adapter().get_all("interface_vlan")

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].mode, InterfaceModeChoices.MODE_TAGGED)
        self.assertEqual(loaded[0].untagged_vid, 10)
        self.assertEqual(loaded[0].tagged_vids, [20])

    def test_an_interface_in_no_mode_is_not_loaded(self):
        """Only switchports carry one of these, matching what IP Fabric's table reports."""
        self.assertEqual(self.adapter().get_all("interface_vlan"), [])


class TestInterfaceVlanScope(TestCase):
    """The job option that governs all of this."""

    def test_it_is_off_by_default_and_needs_the_vlans_themselves(self):
        entry = next(syncable for syncable in SYNCABLE_OBJECTS if syncable.key == "interface_vlans")

        self.assertFalse(entry.default, "No existing sync should change on upgrade.")
        self.assertEqual(set(entry.requires), {"interfaces", "vlans"})


class InterfaceVlanLoadTestCase(TestCase):
    """What the switchport table and the managed address table each contribute."""

    @staticmethod
    def _client(switchports=(), vlan_id=None):
        """Return a mock client serving the given switchport rows, and an addressed Gi4."""
        client = mock_ipfabric_client()
        client.technology.interfaces.switchport.all.return_value = list(switchports)
        client.technology.addressing.managed_ip_ipv4.all.return_value = [
            {**NETWORKS_FIXTURE[0], **({"vlanId": vlan_id} if vlan_id is not None else {})}
        ]
        return client

    def _loaded(self, **kwargs):
        adapter = build_adapter(client=self._client(**kwargs), sync_interface_vlans=True)
        return {(model.device_name, model.interface_name): model for model in adapter.get_all("interface_vlan")}

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def test_a_switchport_carries_the_mode_and_vlans_it_reports(self):
        loaded = self._loaded(
            switchports=[
                {
                    "hostname": "jcy-rtr-02",
                    "sn": "a000a02",
                    "intName": "Gi4",
                    "mode": "trunk",
                    "nativeVlan": 1,
                    "trunkVlan": "10,20",
                },
            ]
        )

        model = loaded[("jcy-rtr-02", "GigabitEthernet4")]
        self.assertEqual(model.mode, "tagged")
        self.assertEqual(model.untagged_vid, 1)
        self.assertEqual(model.tagged_vids, [10, 20])

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def test_an_addressed_interface_takes_the_vlan_its_address_reports(self):
        """A routed interface is not a switchport, so the address table is where its VLAN is named."""
        loaded = self._loaded(vlan_id=30)

        model = loaded[("jcy-rtr-02", "GigabitEthernet4")]
        self.assertEqual(model.mode, "access")
        self.assertEqual(model.untagged_vid, 30)

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def test_the_switchport_table_wins_where_both_speak(self):
        """It is the direct statement of the port's configuration."""
        loaded = self._loaded(
            switchports=[
                {"hostname": "jcy-rtr-02", "sn": "a000a02", "intName": "Gi4", "mode": "access", "accVlan": 10},
            ],
            vlan_id=30,
        )

        self.assertEqual(loaded[("jcy-rtr-02", "GigabitEthernet4")].untagged_vid, 10)

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def test_a_mode_with_no_nautobot_equivalent_is_reported_once_per_mode(self):
        client = self._client(
            switchports=[
                {"hostname": "jcy-rtr-02", "sn": "a000a02", "intName": "Gi4", "mode": "dot1q-tunnel"},
                {"hostname": "nyc-leaf-01", "sn": "5254.0029.fbf2", "intName": "Et15", "mode": "dot1q-tunnel"},
            ]
        )

        with self.assertLogs("nautobot.jobs", level="WARNING") as logs:
            adapter = build_adapter(client=client, sync_interface_vlans=True)

        self.assertEqual(adapter.get_all("interface_vlan"), [])
        reported = [line for line in logs.output if "dot1q-tunnel" in line]
        self.assertEqual(len(reported), 1, f"Expected one report for the mode, got {reported}")
        self.assertIn("2 Interfaces", " ".join(reported))

    def test_out_of_scope_loads_none(self):
        adapter = build_adapter(
            client=self._client(
                switchports=[
                    {"hostname": "jcy-rtr-02", "sn": "a000a02", "intName": "Gi4", "mode": "access", "accVlan": 10},
                ]
            ),
            sync_interface_vlans=False,
        )

        self.assertEqual(adapter.get_all("interface_vlan"), [])
