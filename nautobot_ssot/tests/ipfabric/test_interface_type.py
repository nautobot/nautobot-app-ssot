"""Tests for the Interface type the sync resolves, and for what it does when nothing resolves one.

An Interface type that stood for "not resolved" would be indistinguishable from one genuinely
resolved to that value, so an unresolved type is reported by neither adapter and the value Nautobot
holds is left alone. The exception is a new Interface, which has no value to keep and which Nautobot
will not accept without a type.
"""

import copy
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_INTERFACE_TYPE,
    PSEUDO_MANAGEMENT_INTERFACE_NAME,
)
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import create_interface
from nautobot_ssot.integrations.ipfabric.utilities.utils import interface_name_kind, job_scoped_cache
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    INTERFACE_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)


def inventory_with_an_unresolvable_name():
    """Return the interface inventory with one name no pattern matches and no media type reported.

    `fxp0`, the Junos management port, is physical but named for no pattern, so neither the media
    type nor the name resolves a type for it.
    """
    inventory = copy.deepcopy(INTERFACE_FIXTURE)
    for interface in inventory:
        if interface["intName"] == "ipip":
            interface["intName"] = "fxp0"
    return inventory


class TestTheKindAnInterfaceNameNames(TestCase):
    """Grouping unresolved Interfaces by name, which is what says the mapping is missing a pattern."""

    def test_the_leading_letters_are_the_kind(self):
        self.assertEqual("Ethernet", interface_name_kind("Ethernet1/1"))
        self.assertEqual("Ethernet", interface_name_kind("Ethernet49"))

    def test_a_name_with_no_leading_letters_has_no_kind(self):
        """Reported rather than crashed on: IP Fabric names an Interface whatever the platform does."""
        self.assertEqual("", interface_name_kind("1/1/1"))


class TestLoadingInterfaceType(TestCase):
    """What the IP Fabric adapter does with each kind of reported media type."""

    def loaded(self):
        """Return `(interfaces keyed by (device, interface), the adapter, the job's logger)`."""
        job_logger = MagicMock()
        client = mock_ipfabric_client()
        client.inventory.interfaces.all.return_value = inventory_with_an_unresolvable_name()
        adapter = build_adapter(client=client, logger=job_logger)
        interfaces = {(interface.device_name, interface.name): interface for interface in adapter.get_all("interface")}
        return interfaces, adapter, job_logger

    def test_a_media_type_that_maps_loads_as_that_type(self):
        self.assertEqual("virtual", self.loaded()[0][("jcy-rtr-02", "GigabitEthernet4")].type)

    def test_an_interface_nothing_resolves_a_type_for_leaves_type_unsaid(self):
        """Said on neither side, or the difference is diffed on every run and never settles."""
        interfaces, adapter, _ = self.loaded()

        self.assertIsNone(interfaces[("nyc-rtr-01", "fxp0")].type)
        self.assertIn(("nyc-rtr-01", "fxp0"), adapter.interfaces_without_a_type)

    def test_an_unresolved_type_reaches_the_job_result_log(self):
        """Not just the worker's stdout, or an operator cannot see what went unresolved."""
        _, _, job_logger = self.loaded()

        reported = " ".join(str(call) for call in job_logger.warning.call_args_list)
        self.assertIn("no Nautobot Interface type either", reported)

    def test_interfaces_with_no_media_are_counted_by_name_once_per_kind(self):
        """An estate of one unmapped naming scheme is a line, not one warning per port."""
        _, _, job_logger = self.loaded()

        counted = [
            (call.args[2], call.args[1])
            for call in job_logger.warning.call_args_list
            if "no media type" in call.args[0]
        ]
        self.assertEqual([("Ethernet...", 2), ("fxp...", 1)], sorted(counted))

    def test_each_unmappable_media_type_is_reported_once_however_many_interfaces_carry_it(self):
        """Per distinct value, so what is missing from the mapping is legible rather than buried."""
        inventory = inventory_with_an_unresolvable_name()
        # `Gi4` keeps a media type that maps: the other three are named for no pattern either, so
        # the name fallback cannot rescue them and the count is of the media values alone.
        for interface, media in zip(inventory, ("Coax", "Coax", "Virtual", "SomeNewOptic")):
            interface["media"] = media
        client = mock_ipfabric_client()
        client.inventory.interfaces.all.return_value = inventory
        job_logger = MagicMock()

        build_adapter(client=client, logger=job_logger)

        counted = [
            (call.args[1], call.args[2])
            for call in job_logger.warning.call_args_list
            if "media type of" in call.args[0]
        ]
        self.assertEqual([("Coax", 2), ("SomeNewOptic", 1)], sorted(counted))

    def test_the_fabricated_management_interface_is_registered_rather_than_given_a_type(self):
        """It is this adapter's own invention, so IP Fabric reports no media type for it at all."""
        _, adapter, _ = self.loaded()

        fabricated = [key for key in adapter.interfaces_without_a_type if key[1] == PSEUDO_MANAGEMENT_INTERFACE_NAME]
        self.assertTrue(fabricated, "It still has to be registered, or its type is diffed every run.")


class TestWritingAnInterfaceWithNoResolvedType(TestCase):
    """Nautobot requires a type, so the configured default survives for a new Interface alone."""

    def setUp(self):
        super().setUp()
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="type-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="type-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="type-site1", location_type=location_type, status=active)
        manufacturer = Manufacturer.objects.create(name="type-vendor")
        self.logger = MagicMock()
        self.device = Device.objects.create(
            name="type-dev1",
            status=active,
            role=role,
            location=location,
            device_type=DeviceType.objects.create(model="type-model", manufacturer=manufacturer),
        )

    def create(self, name, **details):
        """Create an Interface through the sync's own helper."""
        return create_interface(
            device_obj=self.device,
            interface_details={"name": name, **details},
            logger=self.logger,
        )

    def test_a_new_interface_with_no_type_takes_the_configured_default(self):
        """`Interface.type` is not nullable, and a new Interface has no earlier value to keep."""
        interface = self.create("eth0", type=None)

        self.assertIsNotNone(interface, "The Interface must still be created.")
        interface.refresh_from_db()
        self.assertEqual(DEFAULT_INTERFACE_TYPE, interface.type)

    def test_a_new_interface_with_a_resolved_type_keeps_it(self):
        self.assertEqual("virtual", self.create("eth1", type="virtual").type)
