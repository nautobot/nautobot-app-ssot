"""Tests for the port a subinterface hangs off.

IP Fabric's interface inventory reports no relation between a subinterface and the port it is
configured on, so the name is the only evidence: a dot separates the port from the logical interface
on every platform this sync has met. Nautobot accepts a parent only on a virtual Interface, so the
type and the parent are decided together.
"""

import copy
from collections import Counter
from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import Cable, Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache, parent_interface_name
from nautobot_ssot.tests.ipfabric.job_log import job_log_text, job_logger
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    INTERFACE_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)

PORTED_SERIAL = "a000a02"
PORTED_HOST = "jcy-rtr-02"


class TestReadingAParentFromAName(TestCase):
    """What a name says about the port its Interface is configured on."""

    def test_a_dot_separates_the_port_from_the_unit(self):
        self.assertEqual("GigabitEthernet0/1", parent_interface_name("GigabitEthernet0/1.100"))
        self.assertEqual("ge-0/0/0", parent_interface_name("ge-0/0/0.0"))

    def test_a_name_with_no_dot_names_no_parent(self):
        self.assertIsNone(parent_interface_name("GigabitEthernet0/1"))

    def test_the_last_dot_is_the_separator(self):
        """A port whose own name carries a dot still keeps all of it."""
        self.assertEqual("Ethernet1.2", parent_interface_name("Ethernet1.2.3"))

    def test_a_name_that_is_all_separator_names_no_parent(self):
        """Refused rather than returning an empty name nothing could match."""
        for name in (".", "Gi0.", ".100", ""):
            with self.subTest(name=name):
                self.assertIsNone(parent_interface_name(name))


def client_with(*interface_names, serial=PORTED_SERIAL, host=PORTED_HOST, media="1000BaseT"):
    """Return a client whose interface inventory carries the given Interfaces on one Device.

    A physical media type by default, so that an Interface coming out virtual is attributable to
    the parent logic rather than to what the fixture reported. The stock `Gi4` row reports
    `Virtual`, which would make every assertion here pass for the wrong reason.
    """
    client = mock_ipfabric_client()
    template = next(row for row in INTERFACE_FIXTURE if row.get("sn") == serial)
    client.inventory.interfaces.all.return_value = [
        dict(copy.deepcopy(template), intName=name, hostname=host, sn=serial, media=media) for name in interface_names
    ]
    return client


class TestPuttingASubinterfaceUnderItsPort(TestCase):
    """What the adapter reports for a subinterface whose port it can see."""

    def loaded(self, *interface_names):
        """Return `(interfaces keyed by name, the adapter, the job's logger)`."""
        logger = job_logger()
        adapter = build_adapter(client=client_with(*interface_names), logger=logger)
        interfaces = {model.name: model for model in adapter.get_all("interface") if model.device_name == PORTED_HOST}
        return interfaces, adapter, logger

    def test_a_subinterface_is_put_under_the_port_it_names(self):
        interfaces, _, _ = self.loaded("Ethernet1", "Ethernet1.100")

        self.assertEqual("Ethernet1", interfaces["Ethernet1.100"].parent_interface)

    def test_it_is_virtual_because_nautobot_accepts_a_parent_on_nothing_else(self):
        """`Interface.clean()` refuses a parent on anything but a virtual Interface."""
        interfaces, _, _ = self.loaded("Ethernet1", "Ethernet1.100")

        self.assertEqual(InterfaceTypeChoices.TYPE_VIRTUAL, interfaces["Ethernet1.100"].type)

    def test_the_port_itself_is_left_as_it_was(self):
        """Only what hangs off a port becomes virtual, never the port."""
        interfaces, _, _ = self.loaded("Ethernet1", "Ethernet1.100")

        self.assertIsNone(interfaces["Ethernet1"].parent_interface)
        self.assertNotEqual(InterfaceTypeChoices.TYPE_VIRTUAL, interfaces["Ethernet1"].type)

    def test_a_subinterface_whose_port_is_absent_is_left_alone(self):
        """A dot in a name is not proof of a port, so nothing is claimed without one."""
        interfaces, adapter, logger = self.loaded("Ethernet1.100")

        self.assertIsNone(interfaces["Ethernet1.100"].parent_interface)
        self.assertNotEqual(
            InterfaceTypeChoices.TYPE_VIRTUAL,
            interfaces["Ethernet1.100"].type,
            "Without a parent there is no reason to call it virtual.",
        )
        self.assertEqual({"Ethernet": 1}, dict(adapter.subinterfaces_without_their_port))
        self.assertIn("Ethernet1.100", str(interfaces))
        self.assertIsNotNone(job_log_text(logger, "warning"))

    def test_a_port_is_loaded_before_anything_configured_on_it(self):
        """DiffSync creates children in order, so the port has to be added first."""
        _, adapter, _ = self.loaded("Ethernet1.100", "Ethernet1")

        names = [model.name for model in adapter.get_all("interface") if model.device_name == PORTED_HOST]
        self.assertLess(
            names.index("Ethernet1"),
            names.index("Ethernet1.100"),
            "The port must come first however IP Fabric ordered them.",
        )

    def test_several_units_on_one_port_all_find_it(self):
        interfaces, adapter, _ = self.loaded("ge-0/0/0", "ge-0/0/0.0", "ge-0/0/0.100")

        self.assertEqual("ge-0/0/0", interfaces["ge-0/0/0.0"].parent_interface)
        self.assertEqual("ge-0/0/0", interfaces["ge-0/0/0.100"].parent_interface)
        self.assertEqual(2, adapter.subinterfaces)

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def test_the_parent_is_matched_on_the_name_the_sync_writes(self):
        """Both names are canonicalised, so the port is found under the name Nautobot will hold."""
        interfaces, _, _ = self.loaded("Gi4", "Gi4.100")

        self.assertIn("GigabitEthernet4.100", interfaces)
        self.assertEqual("GigabitEthernet4", interfaces["GigabitEthernet4.100"].parent_interface)


class TestTheFixtureHasNoSubinterfaces(TestCase):
    """A guard: the stock fixtures must not themselves exercise this path."""

    def test_no_stock_interface_name_carries_a_dot(self):
        """If this stops holding, the tests above stop meaning what they say."""
        adapter = build_adapter(logger=MagicMock())

        self.assertEqual(0, adapter.subinterfaces)
        self.assertEqual({}, dict(adapter.subinterfaces_without_their_port))


class TestATunnelUnitThatWasCabledUnderTheDefaultType(TestCase):
    """A unit synced as `1000base-t` in an earlier release, cabled, and now typed as virtual.

    Nautobot refuses a Cable on a virtual Interface, so a manual run re-typing Junos `st0.0` units
    failed every one of them with "Virtual and wireless interfaces cannot be connected".
    """

    def setUp(self):
        super().setUp()
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="tunnel-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="tunnel-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="tunnel-site1", location_type=location_type, status=active)
        manufacturer = Manufacturer.objects.create(name="tunnel-vendor")
        self.device = Device.objects.create(
            name="d1xfw01",
            status=active,
            role=role,
            location=location,
            device_type=DeviceType.objects.create(model="tunnel-model", manufacturer=manufacturer),
        )
        self.port = Interface.objects.create(device=self.device, name="st0", status=active, type="1000base-t")
        self.unit = Interface.objects.create(device=self.device, name="st0.0", status=active, type="1000base-t")
        self.far = Interface.objects.create(device=self.device, name="ge-0/0/1", status=active, type="1000base-t")
        Cable.objects.create(
            termination_a=self.unit, termination_b=self.far, status=Status.objects.get_for_model(Cable).first()
        )

    def update(self, safe_delete_mode):
        """Drive the update a re-sync makes to the unit, and return the adapter it reported to."""
        adapter = MagicMock()
        adapter.sync_ipfabric_tagged_only = False
        adapter.safe_delete_tally = Counter()
        # Held per run on the adapter, so two syncs in one worker cannot share it.
        adapter.safe_delete_mode = safe_delete_mode
        model = InterfaceModel(name=self.unit.name, device_name=self.device.name, status="Active")
        model.adapter = adapter
        model.update({"type": InterfaceTypeChoices.TYPE_VIRTUAL, "parent_interface": "st0"})
        self.unit.refresh_from_db()
        self.far.refresh_from_db()
        return adapter

    def test_the_cable_is_removed_so_the_unit_can_be_virtual(self):
        adapter = self.update(safe_delete_mode=False)

        self.assertIsNone(self.unit.cable)
        self.assertEqual(InterfaceTypeChoices.TYPE_VIRTUAL, self.unit.type)
        self.assertEqual(self.port, self.unit.parent_interface)
        self.assertFalse(adapter.job.logger.error.called, "Nothing should be refused once the Cable is gone.")

    def test_the_far_end_is_freed_with_it(self):
        """A Cable has two ends, and the other one must not be left claiming it."""
        self.update(safe_delete_mode=False)

        self.assertIsNone(self.far.cable)
        self.assertEqual(0, Cable.objects.count())

    def test_the_removal_is_counted_rather_than_named(self):
        adapter = self.update(safe_delete_mode=False)

        self.assertEqual(
            {("Cable", "deleted, the Interface they ended on being virtual"): 1}, dict(adapter.safe_delete_tally)
        )

    def test_safe_delete_mode_keeps_the_cable_and_holds_the_change_back(self):
        """Safe Delete Mode never removes anything, so the unit is left exactly as it was."""
        adapter = self.update(safe_delete_mode=True)

        self.assertIsNotNone(self.unit.cable)
        self.assertEqual("1000base-t", self.unit.type)
        self.assertIsNone(self.unit.parent_interface)
        self.assertFalse(adapter.job.logger.error.called, "Held back, not refused.")
        self.assertEqual(1, sum(adapter.safe_delete_tally.values()))

    def test_a_unit_holding_no_cable_is_made_virtual_as_before(self):
        self.unit.cable.delete()
        self.unit.refresh_from_db()

        adapter = self.update(safe_delete_mode=True)

        self.assertEqual(InterfaceTypeChoices.TYPE_VIRTUAL, self.unit.type)
        self.assertEqual(self.port, self.unit.parent_interface)
        self.assertEqual({}, dict(adapter.safe_delete_tally), "Nothing to remove, so nothing to count.")


DEVICE_A = ("jcy-rtr-02", "a000a02")
DEVICE_B = ("nyc-rtr-01", "VM60D5EE2211")


def client_with_links(links, interfaces_a=(), interfaces_b=()):
    """Return a client whose two Devices report the given Interfaces and connectivity matrix rows."""
    client = mock_ipfabric_client()
    template = next(row for row in INTERFACE_FIXTURE if row.get("sn") == DEVICE_A[1])
    client.inventory.interfaces.all.return_value = [
        dict(copy.deepcopy(template), intName=name, hostname=host, sn=serial, media="1000BaseT")
        for (host, serial), names in ((DEVICE_A, interfaces_a), (DEVICE_B, interfaces_b))
        for name in names
    ]
    client.technology.interfaces.connectivity_matrix.all.return_value = [
        {"localHost": DEVICE_A[0], "localInt": local, "remoteHost": DEVICE_B[0], "remoteInt": remote}
        for local, remote in links
    ]
    return client


class TestALinkSeenOnSubinterfaces(TestCase):
    """IP Fabric reports a link where the adjacency was seen, which for a subinterface is its unit."""

    def cables(self, links, interfaces_a, interfaces_b):
        """Return the Cables loaded, as `{(device, interface), (device, interface)}` pairs, and the adapter."""
        logger = job_logger()
        adapter = build_adapter(
            client=client_with_links(links, interfaces_a, interfaces_b), logger=logger, sync_cables=True
        )
        cables = {
            frozenset(
                {
                    (model.termination_a_device, model.termination_a_name),
                    (model.termination_b_device, model.termination_b_name),
                }
            )
            for model in adapter.get_all("cable")
        }
        return cables, adapter, logger

    def test_a_link_between_units_is_cabled_between_their_ports(self):
        """`c0xr01:ge-0/0/0.0 <-> c0xr02:ge-0/0/0.0` from the manual run, as the Cable it rides on."""
        cables, _, _ = self.cables(
            [("ge-0/0/0.0", "ge-0/0/0.0")], ("ge-0/0/0", "ge-0/0/0.0"), ("ge-0/0/0", "ge-0/0/0.0")
        )

        self.assertEqual({frozenset({(DEVICE_A[0], "ge-0/0/0"), (DEVICE_B[0], "ge-0/0/0")})}, cables)

    def test_a_tunnel_peering_is_not_turned_into_a_cable(self):
        """`st0.0 <-> st0.0` is reached over IP, so there is no Cable between the two `st0`."""
        cables, _, _ = self.cables([("st0.0", "st0.0")], ("st0", "st0.0"), ("st0", "st0.0"))

        self.assertEqual(set(), cables)

    def test_several_units_on_one_pair_of_ports_make_one_cable(self):
        """Each VLAN on a trunk is reported as its own link, and they share the one Cable."""
        cables, adapter, _ = self.cables(
            [("ge-0/0/0.100", "ge-0/0/0.100"), ("ge-0/0/0.200", "ge-0/0/0.200")],
            ("ge-0/0/0", "ge-0/0/0.100", "ge-0/0/0.200"),
            ("ge-0/0/0", "ge-0/0/0.100", "ge-0/0/0.200"),
        )

        self.assertEqual({frozenset({(DEVICE_A[0], "ge-0/0/0"), (DEVICE_B[0], "ge-0/0/0")})}, cables)
        self.assertEqual(2, len(adapter.links_moved_to_their_ports), "Each reported link is counted once.")

    def test_a_unit_linked_to_a_port_moves_only_the_unit(self):
        """A router on a stick: the unit's end moves to its port, the switch end stays put."""
        cables, _, _ = self.cables([("ge-0/0/0.100", "Ethernet1")], ("ge-0/0/0", "ge-0/0/0.100"), ("Ethernet1",))

        self.assertEqual({frozenset({(DEVICE_A[0], "ge-0/0/0"), (DEVICE_B[0], "Ethernet1")})}, cables)

    def test_a_unit_whose_port_was_not_reported_is_not_moved(self):
        """Moving it would cable a port nothing reported, so the link goes uncabled instead."""
        cables, adapter, _ = self.cables([("ge-0/0/0.0", "ge-0/0/0.0")], ("ge-0/0/0.0",), ("ge-0/0/0.0",))

        self.assertNotIn(frozenset({(DEVICE_A[0], "ge-0/0/0"), (DEVICE_B[0], "ge-0/0/0")}), cables)
        self.assertEqual(set(), adapter.links_moved_to_their_ports)

    def test_moving_links_is_reported_once_for_the_run(self):
        _, _, logger = self.cables(
            [("ge-0/0/0.0", "ge-0/0/0.0")], ("ge-0/0/0", "ge-0/0/0.0"), ("ge-0/0/0", "ge-0/0/0.0")
        )

        self.assertIn("Recording 1 links IP Fabric reports between subinterfaces", job_log_text(logger, "info"))
