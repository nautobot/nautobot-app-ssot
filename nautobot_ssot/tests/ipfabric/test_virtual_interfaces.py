"""Tests for the Interfaces IP Fabric's inventory does not return but another table attests.

`tables/inventory/interfaces` is the only table this sync reads Interfaces from, and it does not
always carry the virtual ones. An address configured on an SVI, a loopback or a tunnel is reported
by the managed address table whether or not the inventory named the port, so the port exists and
only the inventory is silent.
"""

from unittest.mock import MagicMock

from nautobot.apps.testing import TestCase

from nautobot_ssot.tests.ipfabric.job_log import job_log_text, job_logger
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    NETWORKS_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)

# `a000a02` is jcy-rtr-02, whose only inventory Interface is `Gi4`.
ADDRESSED_SERIAL = "a000a02"
ADDRESSED_HOST = "jcy-rtr-02"


def client_addressing(*interface_names, host=ADDRESSED_HOST, serial=ADDRESSED_SERIAL):
    """Return a client whose managed address table names an address on each given Interface."""
    client = mock_ipfabric_client()
    client.technology.addressing.managed_ip_ipv4.all.return_value = [
        {
            "net": "10.10.0.0/24",
            "sn": serial,
            "hostname": host,
            "ip": f"10.10.0.{index + 20}",
            "intName": name,
        }
        for index, name in enumerate(interface_names)
    ]
    return client


class TestInterfacesTheInventoryLeftOut(TestCase):
    """What the adapter does with an Interface only the address table names."""

    def loaded(self, *interface_names, **kwargs):
        """Return `(interfaces keyed by (device, name), the adapter, the job's logger)`."""
        logger = job_logger()
        adapter = build_adapter(client=client_addressing(*interface_names, **kwargs), logger=logger)
        interfaces = {(model.device_name, model.name): model for model in adapter.get_all("interface")}
        return interfaces, adapter, logger

    def test_an_interface_only_an_address_names_is_still_synced(self):
        """Nothing could attach the address before, and the port was missing with nothing said."""
        interfaces, _, _ = self.loaded("Vlan100")

        self.assertIn((ADDRESSED_HOST, "Vlan100"), interfaces)

    def test_its_type_is_read_from_its_name(self):
        """The table that reports a media type is the one that left the Interface out."""
        interfaces, _, _ = self.loaded("Vlan100")

        self.assertEqual("virtual", interfaces[(ADDRESSED_HOST, "Vlan100")].type)

    def test_the_address_that_named_it_is_attached_to_it(self):
        """Attaching the address is the point: it had nowhere to go before."""
        _, adapter, _ = self.loaded("Vlan100")

        addressed = [
            model
            for model in adapter.get_all("interface_address")
            if model.interface_name == "Vlan100" and model.device_name == ADDRESSED_HOST
        ]
        self.assertEqual(1, len(addressed), "The address must sit on the Interface that named it.")

    def test_an_interface_the_inventory_did_return_is_not_added_twice(self):
        """`Gi4` is in the inventory, so naming an address on it must change nothing."""
        interfaces, adapter, _ = self.loaded("Gi4")

        matching = [key for key in interfaces if key == (ADDRESSED_HOST, "GigabitEthernet4") or key[1] == "Gi4"]
        self.assertEqual(1, len(matching), f"Expected one Interface, got {matching}")
        self.assertEqual(adapter.interfaces_the_inventory_left_out, {})

    def test_what_the_inventory_omitted_is_reported_once_per_kind(self):
        """Which kinds the appliance omits is the thing worth knowing, not which ports."""
        _, adapter, logger = self.loaded("Vlan100", "Vlan200", "Loopback0")

        self.assertEqual({"Vlan": 2, "Loopback": 1}, dict(adapter.interfaces_the_inventory_left_out))
        reported = job_log_text(logger, "warning")
        self.assertIn("interface inventory did not", reported)
        self.assertIn("Vlan...", reported)

    def test_nothing_is_invented_where_the_inventory_covers_everything(self):
        """The ordinary case: no extra Interfaces and no report."""
        _, adapter, logger = self.loaded()

        self.assertEqual(adapter.interfaces_the_inventory_left_out, {})
        self.assertNotIn("interface inventory did not", job_log_text(logger, "warning"))

    def test_an_address_on_a_device_this_run_did_not_load_invents_nothing(self):
        """The serial has to match a Device the run holds, or there is nothing to hang it off."""
        _, adapter, _ = self.loaded("Vlan100", serial="no-such-serial", host="no-such-device")

        self.assertEqual(adapter.interfaces_the_inventory_left_out, {})


class TestTheFixtureStillCoversTheOrdinaryCase(TestCase):
    """A guard: the stock fixtures must not themselves exercise the new path."""

    def test_the_stock_address_fixture_names_an_interface_the_inventory_returns(self):
        """If this ever stops holding, the other tests here stop meaning what they say."""
        adapter = build_adapter(logger=MagicMock())

        self.assertEqual(adapter.interfaces_the_inventory_left_out, {})
        self.assertEqual("Gi4", NETWORKS_FIXTURE[0]["intName"])
