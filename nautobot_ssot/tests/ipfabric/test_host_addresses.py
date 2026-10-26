"""Unit tests for syncing the IP Addresses of the hosts IP Fabric discovers."""

from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer
from nautobot.extras.models import Role
from nautobot.ipam.models import IPAddress, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.constants import SAFE_DELETE_IPADDRESS_STATUS
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import (
    IPFabricDiffSync,
    covering_lengths,
    reported_hosts,
)
from nautobot_ssot.integrations.ipfabric.strict_mode import StrictObjects
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.tests.ipfabric.job_log import job_log_text
from nautobot_ssot.tests.ipfabric.test_prefixes import PrefixTestCase, full_scope, nautobot_adapter, summary_row


def host_row(ip, mac="aac1.ab6f.dbe2", dns_name=None):
    """Return a row of IP Fabric's IPv4 host table, reduced to the columns read."""
    return {"ip": ip, "dnsName": dns_name, "mac": mac}


class ReportedHostsTestCase(SimpleTestCase):
    """Reading each host's DNS name and MAC address from the host tables' rows."""

    def test_a_host_keeps_its_dns_name_and_a_normalised_mac(self):
        self.assertEqual(
            reported_hosts([host_row("10.0.0.5", dns_name=" web01.example.com ")]),
            {"10.0.0.5": ("web01.example.com", "AA:C1:AB:6F:DB:E2")},
        )

    def test_a_host_reported_twice_keeps_neither(self):
        rows = [host_row("10.0.0.5", dns_name="a"), host_row("10.0.0.5", mac="0011.2233.4455", dns_name="b")]
        self.assertEqual(reported_hosts(rows), {"10.0.0.5": ("", "")})

    def test_an_unusable_address_or_mac_is_dropped(self):
        rows = [host_row("not-an-address"), host_row(None), host_row("FD00::0005", mac="bogus")]
        self.assertEqual(reported_hosts(rows), {"fd00::5": ("", "")})


class CoveringLengthsTestCase(SimpleTestCase):
    """Choosing the mask a host takes from the networks loaded."""

    def test_the_most_specific_covering_network_wins(self):
        lengths = covering_lengths(["10.0.0.5", "10.0.0.200"], ["10.0.0.0/16", "10.0.0.0/25"])
        self.assertEqual(lengths, {"10.0.0.5": 25, "10.0.0.200": 16})

    def test_a_host_no_network_covers_is_left_out(self):
        self.assertEqual(covering_lengths(["192.0.2.1", "fd00::5"], ["10.0.0.0/8", "fd00::/64"]), {"fd00::5": 64})


class HostAddressScopeTestCase(SimpleTestCase):
    """The job form toggle."""

    def test_it_is_off_by_default_and_needs_prefixes_and_addresses(self):
        syncable = next(syncable for syncable in SYNCABLE_OBJECTS if syncable.key == "host_addresses")
        self.assertFalse(syncable.default)
        self.assertIn(
            "Skipped unless 'prefixes' and 'ip_addresses' are also selected",
            syncable.form_field().field_attrs["help_text"],
        )
        self.assertFalse(full_scope(prefixes=False).host_addresses)


class IPFabricHostAddressLoadTestCase(SimpleTestCase):
    """Loading the hosts IP Fabric discovers."""

    def load(self, hosts, scope=None, on_interfaces=()):
        """Return an IP Fabric adapter that has loaded 10.0.0.0/24 and 10.0.0.0/25 and the given hosts."""
        client = MagicMock()
        client.technology.addressing.managed_ipv4_summary.all.return_value = [
            summary_row("10.0.0.0/24"),
            summary_row("10.0.0.0/25"),
        ]
        client.fetch_all.return_value = []
        client.inventory.hosts.all.return_value = list(hosts)
        client.inventory.hosts_ipv6.all.return_value = [{"ipv6": "fd00::5", "mac": None}]
        adapter = IPFabricDiffSync(
            job=MagicMock(), sync=MagicMock(), client=client, location_filter=None, scope=scope or full_scope()
        )
        for address in on_interfaces:
            adapter.index_by_interface({"sn": "a", "intName": "e0", "ip": address})
        adapter.load_prefixes()
        return adapter

    def loaded(self, adapter):
        """Return the HostAddress models an adapter loaded, as tuples."""
        return sorted(
            (model.host, model.mask_length, model.dns_name, model.mac_address)
            for model in adapter.get_all("host_address")
        )

    def test_each_covered_host_is_loaded_with_the_most_specific_mask(self):
        adapter = self.load([host_row("10.0.0.5", dns_name="web01"), host_row("10.0.0.200")])
        self.assertEqual(
            self.loaded(adapter),
            [("10.0.0.200", 24, "", "AA:C1:AB:6F:DB:E2"), ("10.0.0.5", 25, "web01", "AA:C1:AB:6F:DB:E2")],
        )

    def test_a_host_on_an_interface_is_left_to_the_interface(self):
        adapter = self.load([host_row("10.0.0.5")], on_interfaces=["10.0.0.5"])
        self.assertEqual(self.loaded(adapter), [])

    def test_hosts_no_network_covers_are_reported_once(self):
        adapter = self.load([host_row("192.0.2.1")])
        self.assertEqual(self.loaded(adapter), [])
        self.assertIn(
            "Not syncing 2 hosts IP Fabric discovers, as no network it reports covers them, for example 192.0.2.1, "
            "fd00::5.",
            job_log_text(adapter.job.logger, "warning"),
        )

    def test_nothing_is_read_unless_selected(self):
        adapter = self.load([host_row("10.0.0.5")], scope=full_scope(host_addresses=False))
        adapter.client.inventory.hosts.all.assert_not_called()
        self.assertEqual(self.loaded(adapter), [])


class HostAddressTestCase(PrefixTestCase):
    """Base for the cases with a synced Prefix 10.0.0.0/24 for hosts to sit under."""

    def setUp(self):
        super().setUp()
        self.make_prefix()

    def create(self, host="10.0.0.5", **attrs):
        """Create a host's IP Address through the DiffSync model, as a sync would."""
        attrs = {
            "mask_length": 24,
            "dns_name": "web01",
            "mac_address": "AA:C1:AB:6F:DB:E2",
            "status": "Active",
            **attrs,
        }
        return self.adapter.host_address.create(self.adapter, {"host": host}, attrs)

    def model(self, **attrs):
        """Return a DiffSync HostAddress for 10.0.0.5 as the Nautobot side holds it."""
        attrs = {"mask_length": 24, "dns_name": "web01", "mac_address": "AA:C1:AB:6F:DB:E2", **attrs}
        return self.adapter.host_address(adapter=self.adapter, host="10.0.0.5", **attrs)

    def address(self):
        """Return the IP Address of 10.0.0.5."""
        return IPAddress.objects.get(host="10.0.0.5")

    def make_interface(self):
        """Return an Interface on a Device, for an address to be held by."""
        manufacturer = Manufacturer.objects.create(name="vendor")
        device = Device.objects.create(
            name="router",
            location=self.make_location(),
            device_type=DeviceType.objects.create(model="model", manufacturer=manufacturer),
            role=Role.objects.get_or_create(name="role")[0],
            status=self.active,
        )
        device.role.content_types.add(ContentType.objects.get_for_model(Device))
        return Interface.objects.create(device=device, name="eth0", type="1000base-t", status=self.active)


class HostAddressWriteTestCase(HostAddressTestCase):  # pylint: disable=too-many-ancestors
    """Writing the IP Address of a host."""

    def test_create_records_the_dns_name_and_mac_and_tags_it(self):
        self.assertIsNotNone(self.create())
        ip_obj = self.address()
        self.assertEqual((ip_obj.dns_name, ip_obj.cf[nbutils.HOST_MAC_CF_NAME]), ("web01", "AA:C1:AB:6F:DB:E2"))
        self.assertTrue(ip_obj.tags.filter(pk=self.adapter.ssot_tag.pk).exists())

    def test_an_address_nautobot_holds_is_adopted(self):
        existing = IPAddress.objects.create(address="10.0.0.5/24", status=self.active)
        self.assertIsNotNone(self.create())
        self.assertEqual(self.address().pk, existing.pk)
        self.assertEqual(self.address().dns_name, "web01")

    def test_an_address_queued_on_an_interface_in_a_bulk_run_is_adopted(self):
        self.adapter.pending = PendingWrites(MagicMock())
        queued = nbutils.create_ip(
            "10.0.0.5", 24, object_pk=self.make_interface(), logger=MagicMock(), writer=self.adapter.writer
        )
        self.assertIsNotNone(self.create())
        self.adapter.pending.flush()
        self.assertEqual(self.address().pk, queued.pk)
        self.assertEqual(self.address().dns_name, "web01")

    def test_a_dns_name_nautobot_refuses_is_reported(self):
        self.assertIsNone(self.create(dns_name="not a name"))
        self.assertIn("Unable to record the host details", job_log_text(self.adapter.job.logger, "error"))

    def test_a_strict_run_reports_a_host_no_prefix_covers(self):
        self.adapter = nautobot_adapter(strict=StrictObjects(["prefixes"]))
        self.assertIsNone(self.create(host="192.0.2.1"))
        self.assertEqual(self.adapter.addresses_outside_every_prefix, ["192.0.2.1/24 (host)"])
        self.assertFalse(IPAddress.objects.filter(host="192.0.2.1").exists())

    def test_another_tenants_address_is_skipped_and_recorded(self):
        IPAddress.objects.create(
            address="10.0.0.5/24", status=self.active, tenant=Tenant.objects.create(name="customer-b")
        )
        self.adapter.tenant = Tenant.objects.create(name="customer-a")
        self.assertIsNone(self.create())
        self.assertEqual(dict(self.adapter.objects_of_another_tenant), {"IP addresses": ["10.0.0.5/24"]})

    def test_update_changes_the_details(self):
        self.create()
        self.assertIsNotNone(self.model().update({"dns_name": "web02", "mac_address": ""}))
        self.assertEqual((self.address().dns_name, self.address().cf[nbutils.HOST_MAC_CF_NAME]), ("web02", ""))

    def test_update_changes_the_mask(self):
        self.make_prefix("10.0.0.0/25")
        self.create()
        self.assertIsNotNone(self.model().update({"mask_length": 25}))
        self.assertEqual(self.address().mask_length, 25)

    def test_an_update_nautobot_refuses_is_not_recorded(self):
        self.create()
        with patch.object(nbutils, "tag_object", side_effect=ValidationError("refused")):
            self.assertIsNone(self.model().update({"dns_name": "web02"}))
        self.assertIn("Unable to record the host details", job_log_text(self.adapter.job.logger, "error"))

    def test_update_restores_a_host_safe_delete_mode_marked(self):
        self.create()
        self.adapter = nautobot_adapter(safe_delete_mode=True)
        self.model().delete()
        self.assertEqual(self.address().status.name, SAFE_DELETE_IPADDRESS_STATUS)
        self.model(status=SAFE_DELETE_IPADDRESS_STATUS).update({"status": "Active"})
        self.assertEqual(self.address().status.name, "Active")
        self.assertFalse(self.address().tags.filter(pk=self.adapter.safe_delete_tag.pk).exists())

    def test_delete_queues_the_address_without_safe_delete_mode(self):
        self.create()
        self.assertIsNotNone(self.model().delete())
        self.assertEqual(self.adapter.objects_to_delete["_ipaddress"], [(IPAddress, self.address().pk)])

    def test_delete_leaves_an_address_an_interface_has_come_to_hold(self):
        self.create()
        self.make_interface().ip_addresses.add(self.address())
        self.model().delete()
        self.assertEqual(self.adapter.objects_to_delete["_ipaddress"], [])

    def test_a_missing_address_is_reported(self):
        self.assertIsNone(self.model().update({"dns_name": "x"}))
        self.assertIsNone(self.model().delete())
        self.assertEqual(job_log_text(self.adapter.job.logger, "error").count("Unable to find an IP Address"), 2)


class NautobotHostAddressLoadTestCase(HostAddressTestCase):  # pylint: disable=too-many-ancestors
    """Loading the hosts this integration synced."""

    def loaded(self, **overrides):
        """Return the HostAddress models a fresh Nautobot adapter loads, as tuples."""
        adapter = nautobot_adapter(**overrides)
        adapter.load_host_addresses()
        return [
            (model.host, model.mask_length, model.dns_name, model.mac_address, model.status)
            for model in adapter.get_all("host_address")
        ]

    def test_a_synced_host_is_loaded(self):
        self.create()
        self.assertEqual(self.loaded(), [("10.0.0.5", 24, "web01", "AA:C1:AB:6F:DB:E2", "Active")])

    def test_an_address_an_interface_holds_or_the_sync_never_tagged_is_not(self):
        self.create()
        self.make_interface().ip_addresses.add(self.address())
        IPAddress.objects.create(address="10.0.0.6/24", status=self.active)
        self.assertEqual(self.loaded(), [])

    def test_a_host_safe_delete_mode_marked_reports_that_status(self):
        self.create()
        IPAddress.objects.filter(host="10.0.0.5").update(
            status=nbutils.get_status_for_model(IPAddress, SAFE_DELETE_IPADDRESS_STATUS)
        )
        self.assertEqual(self.loaded()[0][4], SAFE_DELETE_IPADDRESS_STATUS)

    def test_a_host_two_namespaces_hold_is_loaded_once_and_reported(self):
        self.create()
        elsewhere = Namespace.objects.create(name="customer-a")
        Prefix.objects.create(prefix="10.0.0.0/24", namespace=elsewhere, status=self.active)
        other = IPAddress.objects.create(address="10.0.0.5/24", status=self.active, namespace=elsewhere)
        other.tags.add(self.adapter.ssot_tag)
        adapter = nautobot_adapter()
        adapter.load_host_addresses()
        self.assertEqual(len(adapter.get_all("host_address")), 1)
        self.assertIn("more than one Namespace holds", job_log_text(adapter.job.logger, "warning"))

    def test_only_the_tenants_hosts_are_loaded(self):
        self.create()
        self.assertEqual(self.loaded(tenant=Tenant.objects.create(name="customer-a")), [])
