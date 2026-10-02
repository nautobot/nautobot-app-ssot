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

from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import switchport_vlans, vlan_id_of
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import InterfaceVlan as InterfaceVlanModel
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import create_interface, create_vlan, set_interface_vlans
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache, parse_vlan_ranges
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    INTERFACE_FIXTURE,
    NETWORKS_FIXTURE,
    VLAN_FIXTURE,
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


class TestTheSviVlanWithoutAddressesInScope(TestCase):
    """An SVI's VLAN comes from the address table, which is read for the VLAN as well as the address.

    Sourcing it only when IP Addresses are in scope left the Nautobot side reporting an SVI the
    source said nothing about, so a run with Interface VLANs on and IP Addresses off cleared what an
    earlier run had written.
    """

    def test_the_address_table_is_read_for_the_vlan_alone(self):
        client = mock_ipfabric_client()
        adapter = build_adapter(
            client=client,
            sync_interface_vlans=True,
            sync_interfaces=True,
            sync_vlans=True,
            sync_ip_addresses=False,
        )

        client.technology.addressing.managed_ip_ipv4.all.assert_called()
        self.assertEqual(adapter.get_all("interface_address"), [], "No addresses are synced by it.")

    def test_an_addressed_interface_still_reports_its_vlan(self):
        client = mock_ipfabric_client()
        client.technology.addressing.managed_ip_ipv4.all.return_value = [
            {"sn": record["sn"], "intName": record["intName"], "net": "10.0.0.0/24", "ip": "10.0.0.1", "vlanId": 77}
            for record in INTERFACE_FIXTURE[:1]
        ]

        adapter = build_adapter(
            client=client,
            sync_interface_vlans=True,
            sync_interfaces=True,
            sync_vlans=True,
            sync_ip_addresses=False,
        )

        self.assertIn(
            77,
            [model.untagged_vid for model in adapter.get_all("interface_vlan")],
            "The VLAN the address table reports has to survive IP Addresses being out of scope.",
        )


class TestAVlanThisRunCannotReach(TestCase):
    """A trunk names the VLANs a port allows, which need not all exist at that Location.

    Nothing can point an Interface at a VLAN that is not there, so reporting one would leave the
    difference diffed on every run and never applied.
    """

    def loaded(self, trunk, native=1):
        """Load a trunk allowing `trunk`, with only VLAN 1 present at the Device's Location."""
        client = switchport_client(
            switchports=[
                {
                    "hostname": "jcy-rtr-02",
                    "sn": "a000a02",
                    "intName": "Gi4",
                    "mode": "trunk",
                    "nativeVlan": native,
                    "trunkVlan": trunk,
                }
            ],
            vlans_at=(),
        )
        # Only VLAN 1, so anything else the trunk allows is out of this run's reach.
        client.fetch_all = unittest.mock.MagicMock(
            side_effect=lambda table: (
                [{"siteName": "JCY-RTR-02_1", "vlanName": "v1", "vlanId": 1, "dscr": ""}]
                if table == "tables/vlan/site-summary"
                else ""
            )
        )
        logger = unittest.mock.MagicMock()
        adapter = build_adapter(client=client, logger=logger, sync_interface_vlans=True)
        model = {(m.device_name, m.interface_name): m for m in adapter.get_all("interface_vlan")}
        return model[("jcy-rtr-02", "GigabitEthernet4")], str(logger.warning.call_args_list)

    def test_a_tagged_vlan_that_is_not_there_is_left_out_rather_than_asked_for(self):
        model, warnings = self.loaded("1,10,20")

        self.assertEqual(model.tagged_vids, [1], "Only the VLAN this run loaded can be asked for.")
        self.assertIn("switchports allow", warnings)

    def test_a_native_vlan_that_is_not_there_leaves_the_port_untagged_by_none(self):
        model, _ = self.loaded("1", native=99)

        self.assertIsNone(model.untagged_vid)


class TestInterfaceVlanScope(TestCase):
    """The job option that governs all of this."""

    def test_it_is_off_by_default_and_needs_the_vlans_themselves(self):
        entry = next(syncable for syncable in SYNCABLE_OBJECTS if syncable.key == "interface_vlans")

        self.assertFalse(entry.default, "No existing sync should change on upgrade.")
        self.assertEqual(set(entry.requires), {"interfaces", "vlans"})


def switchport_client(switchports=(), vlan_id=None, vlans_at=("JCY-RTR-02_1",)):
    """Return a mock client serving the given switchport rows, and an addressed Gi4.

    The VLAN table is served with a row for every VLAN ID the switchports and the address name, at
    the Locations given: the sync only puts an Interface in a VLAN this run loaded, so a test that
    names one has to supply it.
    """
    client = mock_ipfabric_client()
    client.technology.interfaces.switchport.all.return_value = list(switchports)
    client.technology.addressing.managed_ip_ipv4.all.return_value = [
        {**NETWORKS_FIXTURE[0], **({"vlanId": vlan_id} if vlan_id is not None else {})}
    ]
    named = set()
    for row in switchports:
        named.update(parse_vlan_ranges(str(row.get("trunkVlan") or "")))
        for key in ("nativeVlan", "accVlan"):
            if isinstance(row.get(key), int):
                named.add(row[key])
    if vlan_id is not None:
        named.add(vlan_id)
    extra = [
        {"siteName": site, "vlanName": f"v{vid}", "vlanId": vid, "dscr": ""}
        for site in vlans_at
        for vid in sorted(named)
    ]
    client.fetch_all = unittest.mock.MagicMock(
        side_effect=lambda table: (VLAN_FIXTURE + extra) if table == "tables/vlan/site-summary" else ""
    )
    return client


class InterfaceVlanLoadTestCase(TestCase):
    """What the switchport table and the managed address table each contribute."""

    def _loaded(self, **kwargs):
        adapter = build_adapter(client=switchport_client(**kwargs), sync_interface_vlans=True)
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
        client = switchport_client(
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
            client=switchport_client(
                switchports=[
                    {"hostname": "jcy-rtr-02", "sn": "a000a02", "intName": "Gi4", "mode": "access", "accVlan": 10},
                ]
            ),
            sync_interface_vlans=False,
        )

        self.assertEqual(adapter.get_all("interface_vlan"), [])


class TestInterfaceVlansUnderBulkWriteMode(_InterfaceVlanTestCase):
    """Bulk Write Mode leaves a new Interface in the queue, so its VLANs have to find it there.

    Sync Cables is the only thing that forces a full flush before the VLAN phase, and it is off by
    default, so on a modest sync the Interface is still queued when its VLANs are written.
    """

    def bulk_adapter(self):
        """A real adapter in Bulk Write Mode, since the model validates the one it is handed."""
        job = unittest.mock.MagicMock()
        job.debug = False
        return NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            bulk_write_mode=True,
        )

    def queue_interface(self, pending, name="eth9"):
        """Queue a new Interface on this test's Device, as a bulk mode sync would."""
        create_interface(
            device_obj=self.device,
            interface_details={"name": name, "type": "1000base-t"},
            pending=pending,
        )
        self.assertFalse(
            Interface.objects.filter(device=self.device, name=name).exists(),
            "The Interface is meant to be queued rather than written at this point.",
        )

    def test_creating_reaches_the_queued_interface(self):
        """Regression: the model has to hand the queue down, or this falls back to the database."""
        adapter = self.bulk_adapter()
        pending = adapter.pending
        self.queue_interface(pending)

        InterfaceVlanModel.create(
            adapter=adapter,
            ids={"device_name": self.device.name, "interface_name": "eth9"},
            attrs={"mode": InterfaceModeChoices.MODE_ACCESS, "untagged_vid": 10, "tagged_vids": []},
        )
        pending.flush()

        interface = Interface.objects.get(device=self.device, name="eth9")
        self.assertEqual(interface.mode, InterfaceModeChoices.MODE_ACCESS)
        self.assertEqual(interface.untagged_vlan, self.vlans[10])

    def test_a_queued_interface_gets_its_tagged_vlans_too(self):
        """The tagged VLANs are join rows, so they are queued behind the Interface itself."""
        adapter = self.bulk_adapter()
        pending = adapter.pending
        self.queue_interface(pending)

        InterfaceVlanModel.create(
            adapter=adapter,
            ids={"device_name": self.device.name, "interface_name": "eth9"},
            attrs={"mode": InterfaceModeChoices.MODE_TAGGED, "untagged_vid": 10, "tagged_vids": [20]},
        )
        pending.flush()

        interface = Interface.objects.get(device=self.device, name="eth9")
        self.assertEqual(interface.mode, InterfaceModeChoices.MODE_TAGGED)
        self.assertEqual(list(interface.tagged_vlans.all()), [self.vlans[20]])

    def queue_vlan(self, pending, vid, name):
        """Queue a VLAN new to Nautobot, as a first bulk sync of a site does."""
        vlan = create_vlan(
            vlan_name=name,
            vlan_id=vid,
            vlan_status="Active",
            location_obj=self.location,
            description="",
            pending=pending,
        )
        self.assertFalse(VLAN.objects.filter(vid=vid).exists(), "The VLAN is meant to be queued, not written.")
        return vlan

    def test_a_vlan_queued_this_run_is_found_rather_than_dropped(self):
        """A first bulk sync of a site creates the VLANs and the switchports in the same run.

        The VLAN is only in the queue at that point, so looking for it in the database alone writes
        the mode and silently drops every VLAN, with a warning that reads as a configuration fault.
        """
        adapter = self.bulk_adapter()
        pending = adapter.pending
        self.queue_vlan(pending, 30, "queued-untagged")
        self.queue_vlan(pending, 40, "queued-tagged")
        self.queue_interface(pending, "eth7")

        InterfaceVlanModel.create(
            adapter=adapter,
            ids={"device_name": self.device.name, "interface_name": "eth7"},
            attrs={"mode": InterfaceModeChoices.MODE_TAGGED, "untagged_vid": 30, "tagged_vids": [40]},
        )
        pending.flush()

        interface = Interface.objects.get(device=self.device, name="eth7")
        self.assertIsNotNone(interface.untagged_vlan, "The untagged VLAN was dropped.")
        self.assertEqual(interface.untagged_vlan.vid, 30)
        self.assertEqual([vlan.vid for vlan in interface.tagged_vlans.all()], [40])

    def test_a_tagged_vlan_the_run_stops_reporting_is_removed_in_bulk_mode(self):
        """`update` carries the whole set, so bulk mode has to replace it rather than add to it."""
        adapter = self.bulk_adapter()
        self.interface.mode = InterfaceModeChoices.MODE_TAGGED
        self.interface.validated_save()
        self.interface.tagged_vlans.set([self.vlans[10], self.vlans[20]])

        set_interface_vlans(
            device_name=self.device.name,
            interface_name=self.interface.name,
            mode=InterfaceModeChoices.MODE_TAGGED,
            untagged_vid=None,
            tagged_vids=[10],
            tagged_only=False,
            pending=adapter.pending,
        )
        adapter.pending.flush()

        self.interface.refresh_from_db()
        self.assertEqual(
            [vlan.vid for vlan in self.interface.tagged_vlans.all()],
            [10],
            "VLAN 20 is no longer reported, so it has to come off the Interface.",
        )

    def test_a_tagged_vlan_the_run_still_reports_is_not_queued_twice(self):
        """The join table makes (interface, vlan) unique, so a second row would refuse the batch."""
        adapter = self.bulk_adapter()
        self.interface.mode = InterfaceModeChoices.MODE_TAGGED
        self.interface.validated_save()
        self.interface.tagged_vlans.set([self.vlans[10]])

        set_interface_vlans(
            device_name=self.device.name,
            interface_name=self.interface.name,
            mode=InterfaceModeChoices.MODE_TAGGED,
            untagged_vid=None,
            tagged_vids=[10, 20],
            tagged_only=False,
            pending=adapter.pending,
        )
        adapter.pending.flush()

        self.interface.refresh_from_db()
        self.assertEqual(sorted(vlan.vid for vlan in self.interface.tagged_vlans.all()), [10, 20])

    def test_the_helper_reports_failure_when_the_queue_is_withheld(self):
        """What the defect looked like: the Interface exists only in the queue, so nothing is written."""
        pending = PendingWrites()
        self.queue_interface(pending)

        written = set_interface_vlans(
            device_name=self.device.name,
            interface_name="eth9",
            mode=InterfaceModeChoices.MODE_ACCESS,
            untagged_vid=10,
            tagged_vids=[],
            tagged_only=False,
            pending=None,
        )

        self.assertFalse(written, "Without the queue there is no Interface to find, which is the bug.")
