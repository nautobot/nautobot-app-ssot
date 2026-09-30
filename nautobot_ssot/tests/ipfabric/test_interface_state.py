"""Tests for the interface state IP Fabric observed, and the admin state derived from it.

Nautobot's `enabled` is whether an Interface is meant to be up; IP Fabric's L1 state is what the last
discovery found. The mapping between them, and what happens when it cannot be read, is the subject.
"""

import copy
import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.ipfabric.constants import (
    INTERFACE_L1_CF_NAME,
    INTERFACE_L2_CF_NAME,
    INTERFACE_REASON_CF_NAME,
    PSEUDO_MANAGEMENT_INTERFACE_NAME,
)
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import admin_state_of
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import create_interface
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    INTERFACE_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)


class TestAdminStateMapping(TestCase):
    """What a reported physical state says about whether the Interface is meant to be up."""

    def test_a_shut_port_is_disabled_however_the_platform_spells_it(self):
        for reported in (
            "adminDown",
            "admin-down",
            "admin down",
            "ADMIN_DOWN",
            "administratively down",
            "shutdown",
            "disabled",
        ):
            with self.subTest(reported=reported):
                self.assertIs(admin_state_of(reported), False)

    def test_err_disabled_is_not_read_as_disabled(self):
        """The switch took the port down for a fault; the configuration still asks for it to be up."""
        for reported in ("errDisabled", "err-disabled", "error-disabled"):
            with self.subTest(reported=reported):
                self.assertIsNone(admin_state_of(reported), "Matching by substring would catch this.")

    def test_an_interface_that_is_merely_down_is_still_enabled(self):
        """Down is an operational state: the Interface is meant to be running and is not."""
        self.assertIs(admin_state_of("down"), True)
        self.assertIs(admin_state_of("up"), True)
        self.assertIs(admin_state_of("down", "err-disabled"), True, "A reason that is not the administrator.")

    def test_a_port_that_is_down_because_somebody_shut_it_is_disabled(self):
        """Most platforms report a shut port as plain `down` and say why in the reason."""
        for reason in ("admin", "Admin", "admin-down", "administratively down"):
            with self.subTest(reason=reason):
                self.assertIs(admin_state_of("down", reason), False)

    def test_a_port_that_is_up_is_enabled_whatever_the_reason_says(self):
        """Reachable at layer one, so it is not a shut port however the reason reads."""
        self.assertIs(admin_state_of("up", "admin"), True)

    def test_a_state_that_names_neither_is_refused(self):
        """Refused rather than guessed at, so the caller can leave Nautobot's value alone."""
        for reported in (None, "", "   ", "notPresent", "dormant", "lowerLayerDown"):
            with self.subTest(reported=reported):
                self.assertIsNone(admin_state_of(reported))


class InterfaceFixture(TestCase):
    """A Device to hang Interfaces off, and the sync's own helper for creating them."""

    def setUp(self):
        super().setUp()
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="state-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="state-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="state-site1", location_type=location_type, status=self.active)
        manufacturer = Manufacturer.objects.create(name="state-vendor")
        device_type = DeviceType.objects.create(model="state-model", manufacturer=manufacturer)
        self.logger = unittest.mock.MagicMock()
        self.device = Device.objects.create(
            name="state-dev1",
            status=self.active,
            role=role,
            location=location,
            device_type=device_type,
        )

    def create(self, name, **details):
        """Create an Interface through the sync's own helper."""
        return create_interface(
            device_obj=self.device,
            interface_details={"name": name, "type": "1000base-t", **details},
            logger=self.logger,
        )


class TestWritingInterfaceState(InterfaceFixture):
    """What reaches the Nautobot Interface when the sync creates one."""

    def test_the_observed_state_is_recorded_beside_the_interface(self):
        interface = self.create("eth0", state_l1="up", state_l2="down", state_reason="err-disabled")

        self.assertEqual(interface.cf[INTERFACE_L1_CF_NAME], "up")
        self.assertEqual(interface.cf[INTERFACE_L2_CF_NAME], "down")
        self.assertEqual(interface.cf[INTERFACE_REASON_CF_NAME], "err-disabled")

    def test_an_interface_reported_shut_is_created_disabled(self):
        """The defaults filter drops a falsy value as an absence, so `False` needs the guard beside it."""
        interface = self.create("eth1", enabled=False)

        self.assertFalse(interface.enabled)
        interface.refresh_from_db()
        self.assertFalse(interface.enabled, "The disabled state has to reach the database, not just the instance.")

    def test_an_interface_reported_up_is_created_enabled(self):
        self.assertTrue(self.create("eth2", enabled=True).enabled)

    def test_no_admin_state_never_reaches_the_database_as_null(self):
        """`Interface.enabled` is not nullable, so an unreadable state must not be written at all."""
        interface = self.create("eth3", enabled=None)

        self.assertIsNotNone(interface, "The Interface must still be created.")
        interface.refresh_from_db()
        self.assertTrue(interface.enabled, "Nautobot's own default stands where the sync says nothing.")


class TestLoadingInterfaceState(TestCase):
    """What the IP Fabric adapter does with each kind of reported state."""

    def loaded(self):
        """Return `(interfaces keyed by (device, interface), the adapter, the job's logger)`."""
        job_logger = unittest.mock.MagicMock()
        adapter = build_adapter(logger=job_logger)
        interfaces = {(interface.device_name, interface.name): interface for interface in adapter.get_all("interface")}
        return interfaces, adapter, job_logger

    def test_a_shut_interface_loads_disabled_and_carries_what_was_observed(self):
        interface = self.loaded()[0][("nyc-leaf-01", "Ethernet15")]

        self.assertIs(interface.enabled, False)
        self.assertEqual(interface.state_l1, "down")
        self.assertEqual(interface.state_l2, "down")
        self.assertEqual(interface.state_reason, "admin")

    def test_a_running_interface_loads_enabled(self):
        self.assertIs(self.loaded()[0][("jcy-rtr-02", "GigabitEthernet4")].enabled, True)

    def test_a_state_that_names_no_admin_state_leaves_enabled_unsaid(self):
        """Said on neither side, or the difference is diffed on every run and never settles."""
        interfaces, adapter, job_logger = self.loaded()

        self.assertIsNone(interfaces[("nyc-rtr-01", "Ethernet1")].enabled)
        self.assertIn(("nyc-rtr-01", "Ethernet1"), adapter.interfaces_without_admin_state)
        reported = " ".join(str(call) for call in job_logger.warning.call_args_list)
        self.assertIn("unreadable-state", reported, "The state has to reach the Job Result log, not just stdout.")

    def test_each_unreadable_state_is_reported_once_however_many_interfaces_carry_it(self):
        """Per distinct value, so an estate full of one odd state is a line rather than thousands."""
        inventory = copy.deepcopy(INTERFACE_FIXTURE)
        for interface, state in zip(inventory, ("dormant", "dormant", "notPresent", "dormant")):
            interface["l1"] = state
            interface["reason"] = None
        client = mock_ipfabric_client()
        client.inventory.interfaces.all.return_value = inventory
        job_logger = unittest.mock.MagicMock()

        build_adapter(client=client, logger=job_logger)

        counted = [
            (call.args[1], call.args[2])
            for call in job_logger.warning.call_args_list
            if "physical state" in call.args[0]
        ]
        self.assertEqual([("dormant", 3), ("notPresent", 1)], counted)

    def test_an_interface_no_state_was_reported_for_is_not_reported_against_ip_fabric(self):
        """The pseudo management Interface is this adapter's own invention, not a discovery reading."""
        _, adapter, job_logger = self.loaded()

        fabricated = [
            key for key in adapter.interfaces_without_admin_state if key[1] == PSEUDO_MANAGEMENT_INTERFACE_NAME
        ]
        self.assertTrue(fabricated, "It still has to be registered, or its Enabled is diffed every run.")
        named = [call.args[1] for call in job_logger.warning.call_args_list if "physical state" in call.args[0]]
        self.assertEqual(["unreadable-state"], named, "Only a state IP Fabric actually reported is named.")


class TestUpdatingInterfaceState(InterfaceFixture):
    """Changing an Interface Nautobot already holds, which is what a re-sync does."""

    def diff_model(self, interface, **attrs):
        """Return an Interface DiffSync model bound to a stub adapter, as the Nautobot side loads it."""
        adapter = unittest.mock.MagicMock()
        adapter.sync_ipfabric_tagged_only = False
        model = InterfaceModel(
            name=interface.name, device_name=self.device.name, status="Active", enabled=True, **attrs
        )
        model.adapter = adapter
        return model

    def test_an_interface_that_becomes_shut_is_disabled(self):
        interface = self.create("eth9", enabled=True)
        self.assertTrue(interface.enabled)

        self.diff_model(interface).update({"enabled": False})

        interface.refresh_from_db()
        self.assertFalse(interface.enabled, "A re-sync reporting the port shut has to clear Enabled.")

    def test_no_admin_state_leaves_the_stored_value_alone(self):
        """Saying nothing is not the same as saying enabled, and `enabled` will not take null."""
        interface = self.create("eth11", enabled=False)

        self.diff_model(interface).update({"enabled": None, "state_l1": "notPresent"})

        interface.refresh_from_db()
        self.assertFalse(interface.enabled, "An unreadable state must not re-enable a disabled Interface.")
        self.assertEqual(interface.cf[INTERFACE_L1_CF_NAME], "notPresent")

    def test_a_changed_reported_state_is_written(self):
        interface = self.create("eth10", state_l1="up", state_l2="up")

        self.diff_model(interface).update({"state_l1": "down", "state_l2": "down", "state_reason": "err-disabled"})

        interface.refresh_from_db()
        self.assertEqual(interface.cf[INTERFACE_L1_CF_NAME], "down")
        self.assertEqual(interface.cf[INTERFACE_REASON_CF_NAME], "err-disabled")
