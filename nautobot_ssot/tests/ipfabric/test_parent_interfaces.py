"""Tests for the port a subinterface hangs off.

IP Fabric's interface inventory reports no relation between a subinterface and the port it is
configured on, so the name is the only evidence: a dot separates the port from the logical interface
on every platform this sync has met. Nautobot accepts a parent only on a virtual Interface, so the
type and the parent are decided together.
"""

import copy
from unittest.mock import MagicMock, patch

from nautobot.apps.testing import TestCase
from nautobot.dcim.choices import InterfaceTypeChoices

from nautobot_ssot.integrations.ipfabric.utilities.utils import parent_interface_name
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
