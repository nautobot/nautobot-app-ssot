"""Tests for the port channel an Interface belongs to.

IP Fabric reports a port channel's members as one string, each name followed by its state in
brackets. Nautobot holds the relation as a foreign key from each member to the port channel, and
refuses one on a virtual Interface.
"""

import copy
from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache, lag_member_names
from nautobot_ssot.tests.ipfabric.job_log import job_log_text, job_logger
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    INTERFACE_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)

LAG_SERIAL = "a000a02"
LAG_HOST = "jcy-rtr-02"


class TestReadingTheMemberColumn(TestCase):
    """What IP Fabric's single members column says."""

    def test_each_member_is_named_without_its_state(self):
        self.assertEqual(["Et35", "Et36"], lag_member_names("Et35(DOWN), Et36(DOWN)"))

    def test_only_the_last_brackets_are_the_state(self):
        """A member's own name may carry brackets, so the state comes off the end."""
        self.assertEqual(["Et35(TEST)"], lag_member_names("Et35(TEST)(DOWN)"))

    def test_a_member_with_no_state_is_still_named(self):
        self.assertEqual(["Et35"], lag_member_names("Et35"))

    def test_nothing_reported_names_nobody(self):
        for reported in (None, "", "   ", ","):
            with self.subTest(reported=reported):
                self.assertEqual([], lag_member_names(reported))


def client_with_lag(
    members="Ethernet1(UP), Ethernet2(UP)",
    lag_name="Port-channel12",
    interface_names=("Port-channel12", "Ethernet1", "Ethernet2"),
):
    """Return a client reporting the given Interfaces and one port channel over them.

    Names already in their canonical form, because this environment canonicalises them and the
    member column is matched against what the inventory reported, not against what is written.
    """
    client = mock_ipfabric_client()
    template = next(row for row in INTERFACE_FIXTURE if row.get("sn") == LAG_SERIAL)
    client.inventory.interfaces.all.return_value = [
        dict(copy.deepcopy(template), intName=name, hostname=LAG_HOST, sn=LAG_SERIAL, media="1000BaseT")
        for name in interface_names
    ]
    client.technology.port_channels.member_status_table.all.return_value = [
        {"sn": LAG_SERIAL, "hostname": LAG_HOST, "intName": lag_name, "members": members}
    ]
    return client


class TestPuttingAnInterfaceInItsPortChannel(TestCase):
    """What the adapter reports for a member and for the channel itself."""

    def loaded(self, **kwargs):
        """Return `(interfaces keyed by name, the adapter, the job's logger)`."""
        logger = job_logger()
        adapter = build_adapter(client=client_with_lag(**kwargs), logger=logger)
        interfaces = {model.name: model for model in adapter.get_all("interface") if model.device_name == LAG_HOST}
        return interfaces, adapter, logger

    def test_each_member_names_the_channel_it_is_in(self):
        interfaces, adapter, _ = self.loaded()

        self.assertEqual("Port-channel12", interfaces["Ethernet1"].lag)
        self.assertEqual("Port-channel12", interfaces["Ethernet2"].lag)
        self.assertEqual(2, adapter.lag_members)

    def test_the_channel_itself_is_in_no_channel(self):
        interfaces, _, _ = self.loaded()

        self.assertIsNone(interfaces["Port-channel12"].lag)

    def test_an_interface_in_no_channel_is_left_alone(self):
        interfaces, _, _ = self.loaded(interface_names=("Port-channel12", "Ethernet1", "Ethernet2", "Ethernet9"))

        self.assertIsNone(interfaces["Ethernet9"].lag)

    def test_the_channel_is_loaded_before_its_members(self):
        """DiffSync creates children in order, so the channel has to exist first."""
        _, adapter, _ = self.loaded(interface_names=("Ethernet1", "Ethernet2", "Port-channel12"))

        names = [model.name for model in adapter.get_all("interface") if model.device_name == LAG_HOST]
        self.assertLess(names.index("Port-channel12"), names.index("Ethernet1"), "The channel must come first.")
        self.assertLess(names.index("Port-channel12"), names.index("Ethernet2"))

    def test_a_channel_with_no_members_records_no_membership(self):
        _, adapter, _ = self.loaded(members="")

        self.assertEqual({}, adapter.lag_by_member)
        self.assertEqual(0, adapter.lag_members)

    def test_a_subinterface_is_kept_out_of_a_channel_and_reported(self):
        """Nautobot refuses a port channel on a virtual Interface, which a subinterface is."""
        interfaces, _, logger = self.loaded(
            members="Ethernet1.100(UP)", interface_names=("Port-channel12", "Ethernet1", "Ethernet1.100")
        )

        self.assertIsNone(interfaces["Ethernet1.100"].lag, "Virtual Interfaces cannot be in a port channel.")
        self.assertEqual("Ethernet1", interfaces["Ethernet1.100"].parent_interface, "It is still under its port.")
        self.assertIn("Nautobot does not allow in a port channel", job_log_text(logger, "warning"))

    @patch("nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True)
    def test_the_channel_is_named_as_the_sync_writes_it(self):
        """Both names are canonicalised, so the member points at the name Nautobot will hold."""
        interfaces, _, _ = self.loaded(members="Gi4(UP)", lag_name="Po12", interface_names=("Po12", "Gi4"))

        self.assertEqual("Port-channel12", interfaces["GigabitEthernet4"].lag)


class TestTheFixtureHasNoPortChannels(TestCase):
    """A guard: the stock fixtures must not themselves exercise this path."""

    def test_no_membership_is_recorded_from_the_stock_fixtures(self):
        """If this stops holding, the tests above stop meaning what they say."""
        adapter = build_adapter(logger=MagicMock())

        self.assertEqual({}, adapter.lag_by_member)
        self.assertEqual(0, adapter.lag_members)


class TestUpdatingTheRelationsOnAnInterfaceNautobotHolds(TestCase):
    """A re-sync drives `update`, which resolves a name into the Interface it points at.

    `create` and `update` take different routes to the same field, and only `create` was covered
    until a manual run raised `Cannot assign "'Port-channel3'": "Interface.lag" must be a
    "Interface" instance.` from this path.
    """

    def setUp(self):
        super().setUp()
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="lag-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="lag-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="lag-site1", location_type=location_type, status=active)
        manufacturer = Manufacturer.objects.create(name="lag-vendor")
        self.device = Device.objects.create(
            name="lag-dev1",
            status=active,
            role=role,
            location=location,
            device_type=DeviceType.objects.create(model="lag-model", manufacturer=manufacturer),
        )
        self.channel = Interface.objects.create(
            device=self.device, name="Port-channel3", status=active, type=InterfaceTypeChoices.TYPE_LAG
        )
        self.member = Interface.objects.create(device=self.device, name="Ethernet1", status=active, type="1000base-t")
        self.port = Interface.objects.create(device=self.device, name="Ethernet2", status=active, type="1000base-t")
        self.unit = Interface.objects.create(
            device=self.device, name="Ethernet2.100", status=active, type=InterfaceTypeChoices.TYPE_VIRTUAL
        )

    def diff_model(self, interface):
        """Return an Interface model bound to a stub adapter, as the Nautobot side loads one."""
        adapter = MagicMock()
        adapter.sync_ipfabric_tagged_only = False
        model = InterfaceModel(name=interface.name, device_name=self.device.name, status="Active")
        model.adapter = adapter
        return model

    def test_a_port_channel_named_in_an_update_is_resolved_to_the_interface(self):
        """The name has to become an Interface; assigning the string raises from Django."""
        self.diff_model(self.member).update({"lag": "Port-channel3"})

        self.member.refresh_from_db()
        self.assertEqual(self.channel, self.member.lag)

    def test_an_interface_taken_out_of_its_channel_stops_claiming_membership(self):
        self.member.lag = self.channel
        self.member.validated_save()

        self.diff_model(self.member).update({"lag": None})

        self.member.refresh_from_db()
        self.assertIsNone(self.member.lag)

    def test_a_port_named_in_an_update_is_resolved_to_the_interface(self):
        self.diff_model(self.unit).update({"parent_interface": "Ethernet2"})

        self.unit.refresh_from_db()
        self.assertEqual(self.port, self.unit.parent_interface)

    def test_a_subinterface_taken_out_from_under_its_port_stops_pointing_at_it(self):
        self.unit.parent_interface = self.port
        self.unit.validated_save()

        self.diff_model(self.unit).update({"parent_interface": None})

        self.unit.refresh_from_db()
        self.assertIsNone(self.unit.parent_interface)

    def test_a_channel_that_is_not_there_is_reported_rather_than_assigned(self):
        model = self.diff_model(self.member)

        model.update({"lag": "Port-channel99"})

        self.member.refresh_from_db()
        self.assertIsNone(self.member.lag, "Nothing to point at, and nothing raised.")
