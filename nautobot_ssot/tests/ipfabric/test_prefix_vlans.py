"""Unit tests for syncing the VLAN a Prefix is in."""

from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from nautobot.dcim.models import Location
from nautobot.ipam.models import VLAN, Prefix

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import (
    IPFabricDiffSync,
    agreed_prefix_vlan,
    vlans_by_prefix,
)
from nautobot_ssot.integrations.ipfabric.strict_mode import StrictObjects
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.tests.ipfabric.job_log import job_log_text
from nautobot_ssot.tests.ipfabric.test_prefixes import PrefixTestCase, full_scope, nautobot_adapter, summary_row


def vlan_row(net, vlan_id, site="site1"):
    """Return a row of IP Fabric's managed IP table, reduced to the columns read for a Prefix's VLAN."""
    return {"net": net, "siteName": site, "vlanId": vlan_id}


class VlansByPrefixTestCase(SimpleTestCase):
    """Grouping the site and VLAN pairs each network's addresses are reported in."""

    def test_the_addresses_of_a_network_are_one_entry(self):
        rows = [vlan_row("10.0.0.1/24", 10), vlan_row("10.0.0.2/24", 10), vlan_row("10.0.0.3/24", 20, "b")]
        self.assertEqual(vlans_by_prefix(rows), {"10.0.0.0/24": {("site1", 10), ("b", 20)}})

    def test_a_row_without_a_usable_vlan_site_or_network_is_skipped(self):
        rows = [
            vlan_row("10.0.0.0/24", None),
            vlan_row("10.0.0.0/24", 5000),
            vlan_row("10.0.0.0/24", 10, site=None),
            vlan_row(None, 10),
            vlan_row("not-a-network", 10),
        ]
        self.assertEqual(vlans_by_prefix(rows), {})


class AgreedPrefixVlanTestCase(SimpleTestCase):
    """Settling on the one VLAN Nautobot can hold for a Prefix."""

    def test_one_pair_is_the_prefixs_vlan(self):
        self.assertEqual(agreed_prefix_vlan({("site1", 10)}), {"vid": 10, "location_name": "site1", "conflict": ""})

    def test_several_pairs_record_none_and_name_them(self):
        self.assertEqual(
            agreed_prefix_vlan({("b", 20), ("a", 10)}),
            {
                "vid": None,
                "location_name": None,
                "conflict": "IP Fabric reports this network in VLAN 10 at a, VLAN 20 at b",
            },
        )


class PrefixVlanTestCase(PrefixTestCase):
    """Base for the cases with a Prefix at site1 and a VLAN 10 there."""

    def setUp(self):
        super().setUp()
        self.location = self.make_location()
        nbutils.allow_vlans_at_location_type(self.location.location_type_id)
        self.vlan = VLAN.objects.create(vid=10, name="v10", status=self.active)
        self.vlan.locations.add(self.location)
        self.prefix_obj = self.make_prefix()
        self.prefix_obj.locations.add(self.location)

    def create(self, **attrs):
        """Record the Prefix's VLAN through the DiffSync model, as a sync would."""
        attrs = {"vid": 10, "location_name": "site1", "conflict": "", **attrs}
        return self.adapter.prefix_vlan.create(self.adapter, {"prefix": "10.0.0.0/24"}, attrs)

    def model(self, **attrs):
        """Return a DiffSync PrefixVlan for the Prefix as the Nautobot side holds it."""
        attrs = {"vid": 10, "location_name": "site1", "conflict": "", **attrs}
        return self.adapter.prefix_vlan(adapter=self.adapter, prefix="10.0.0.0/24", **attrs)

    def conflict(self):
        """Return what the Prefix's conflict custom field holds."""
        self.prefix_obj.refresh_from_db()
        return self.prefix_obj.cf.get(nbutils.PREFIX_VLAN_CONFLICT_CF_NAME)


class PrefixVlanWriteTestCase(PrefixVlanTestCase):  # pylint: disable=too-many-ancestors
    """Writing the VLAN a Prefix is in."""

    def test_create_puts_the_prefix_in_the_vlan(self):
        self.assertIsNotNone(self.create())
        self.prefix_obj.refresh_from_db()
        self.assertEqual(self.prefix_obj.vlan, self.vlan)

    def test_a_conflict_leaves_no_vlan_and_names_the_pairs(self):
        self.assertIsNotNone(self.create(vid=None, location_name=None, conflict="IP Fabric reports two"))
        self.assertEqual(self.conflict(), "IP Fabric reports two")
        self.assertIsNone(self.prefix_obj.vlan)

    def test_a_vlan_nautobot_does_not_hold_is_counted_and_reported_once(self):
        self.assertIsNone(self.create(vid=20))
        self.assertIsNone(self.create(vid=20))
        self.adapter.sync_complete(MagicMock(), MagicMock())
        self.assertIn(
            "Not recording VLAN 20 at site1 on 2 Prefixes, as Nautobot holds no such VLAN.",
            job_log_text(self.adapter.job.logger, "warning"),
        )

    def test_a_vlan_queued_earlier_in_a_bulk_run_is_written_first(self):
        self.adapter = nautobot_adapter(bulk_write_mode=True)
        with patch.object(self.adapter, "flush_pending_writes") as flush:
            self.create()
        flush.assert_called_once()

    def test_a_prefix_this_run_did_not_write_is_skipped(self):
        self.adapter = nautobot_adapter(strict=StrictObjects(["prefixes"]))
        self.adapter.prefixes_not_created.add("10.0.0.0/24")
        self.assertIsNone(self.create())
        self.prefix_obj.refresh_from_db()
        self.assertIsNone(self.prefix_obj.vlan)

    def test_another_tenants_prefix_is_skipped(self):
        self.adapter.objects_of_another_tenant["prefixes"].append("10.0.0.0/24")
        self.assertIsNone(self.create())
        self.prefix_obj.refresh_from_db()
        self.assertIsNone(self.prefix_obj.vlan)

    def test_a_vlan_at_several_locations_is_found_by_its_first(self):
        self.vlan.locations.add(self.make_location("aaa"))
        self.assertIsNotNone(self.create(location_name="aaa"))
        self.prefix_obj.refresh_from_db()
        self.assertEqual(self.prefix_obj.vlan, self.vlan)

    def test_update_moves_the_prefix_to_a_conflict(self):
        self.create()
        self.model().update({"vid": None, "location_name": None, "conflict": "IP Fabric reports two"})
        self.assertEqual(self.conflict(), "IP Fabric reports two")
        self.assertIsNone(self.prefix_obj.vlan)

    def test_update_from_a_conflict_to_one_vlan_clears_it(self):
        self.create(vid=None, location_name=None, conflict="IP Fabric reports two")
        self.model(vid=None, location_name=None, conflict="IP Fabric reports two").update(
            {"vid": 10, "location_name": "site1", "conflict": ""}
        )
        self.assertEqual(self.conflict(), "")
        self.assertEqual(self.prefix_obj.vlan, self.vlan)

    def test_an_update_nautobot_refuses_is_not_recorded(self):
        with patch.object(nbutils, "tag_object", side_effect=ValidationError("refused")):
            self.assertIsNone(self.model().update({"conflict": "x"}))
        self.assertIn("Unable to record the VLAN", job_log_text(self.adapter.job.logger, "error"))

    def test_delete_takes_the_prefix_out_of_its_vlan_and_deletes_nothing(self):
        self.create()
        self.assertIsNotNone(self.model().delete())
        self.prefix_obj.refresh_from_db()
        self.assertIsNone(self.prefix_obj.vlan)
        self.assertTrue(VLAN.objects.filter(pk=self.vlan.pk).exists())

    def test_a_missing_prefix_is_reported(self):
        self.prefix_obj.delete()
        self.assertIsNone(self.model().delete())
        self.assertIn("Unable to find a Prefix of 10.0.0.0/24", job_log_text(self.adapter.job.logger, "error"))


class NautobotPrefixVlanLoadTestCase(PrefixVlanTestCase):  # pylint: disable=too-many-ancestors
    """Loading the VLAN, or the conflict, each synced Prefix holds."""

    def loaded(self):
        """Return the PrefixVlan models a fresh Nautobot adapter loads."""
        adapter = nautobot_adapter()
        adapter.load_prefixes()
        return [
            (model.prefix, model.vid, model.location_name, model.conflict) for model in adapter.get_all("prefix_vlan")
        ]

    def test_a_prefix_without_a_vlan_or_conflict_loads_none(self):
        self.assertEqual(self.loaded(), [])

    def test_a_prefixs_vlan_is_loaded_at_its_first_location(self):
        self.vlan.locations.add(self.make_location("aaa"))
        Prefix.objects.filter(pk=self.prefix_obj.pk).update(vlan=self.vlan)
        self.assertEqual(self.loaded(), [("10.0.0.0/24", 10, "aaa", "")])

    def test_a_conflict_is_loaded_without_a_vlan(self):
        self.create(vid=None, location_name=None, conflict="IP Fabric reports two")
        self.assertEqual(self.loaded(), [("10.0.0.0/24", None, None, "IP Fabric reports two")])


class IPFabricPrefixVlanLoadTestCase(PrefixVlanTestCase):  # pylint: disable=too-many-ancestors
    """Loading the VLAN IP Fabric reports each network in."""

    def ipfabric_adapter(self, vlan_rows=(), scope=None):
        """Return an IP Fabric adapter whose managed IP tables serve the given rows."""
        client = MagicMock()
        client.technology.addressing.managed_ipv4_summary.all.return_value = [summary_row("10.0.0.0/24")]
        client.fetch_all.return_value = []
        client.technology.addressing.managed_ip_ipv4.all.return_value = list(vlan_rows)
        client.technology.addressing.managed_ip_ipv6.all.return_value = []
        adapter = IPFabricDiffSync(
            job=MagicMock(), sync=MagicMock(), client=client, location_filter=None, scope=scope or full_scope()
        )
        adapter.add(adapter.location(adapter=adapter, name="site1", site_id="site1", status="Active"))
        return adapter

    def load(self, vlan_rows):
        """Return an IP Fabric adapter that has loaded the network 10.0.0.0/24 and the given VLAN rows."""
        adapter = self.ipfabric_adapter(vlan_rows)
        adapter.load_prefixes()
        return adapter

    def loaded(self, adapter):
        """Return the PrefixVlan models an adapter loaded, as tuples."""
        return [
            (model.prefix, model.vid, model.location_name, model.conflict) for model in adapter.get_all("prefix_vlan")
        ]

    def test_only_the_rows_naming_a_vlan_are_requested_from_both_tables(self):
        addressing = self.load([]).client.technology.addressing
        for table in (addressing.managed_ip_ipv4, addressing.managed_ip_ipv6):
            self.assertEqual(table.all.call_args.kwargs["filters"], {"vlanId": ["empty", False]})

    def test_a_loaded_networks_vlan_is_loaded(self):
        adapter = self.load([vlan_row("10.0.0.5/24", 10), vlan_row("10.9.0.5/24", 99)])
        self.assertEqual(self.loaded(adapter), [("10.0.0.0/24", 10, "site1", "")])

    def test_a_vlan_nautobot_does_not_hold_is_named_by_the_reported_site(self):
        adapter = self.load([vlan_row("10.0.0.5/24", 30, "elsewhere")])
        self.assertEqual(self.loaded(adapter), [("10.0.0.0/24", 30, "elsewhere", "")])

    def test_a_network_in_different_vlans_is_reported_once(self):
        adapter = self.load([vlan_row("10.0.0.5/24", 10), vlan_row("10.0.0.6/24", 20)])
        self.assertIsNone(adapter.get("prefix_vlan", "10.0.0.0/24").vid)
        self.assertIn("Not recording a VLAN for 1 Prefixes", job_log_text(adapter.job.logger, "warning"))

    def test_a_vlan_at_several_locations_reads_the_same_on_both_sides(self):
        self.vlan.locations.add(self.make_location("aaa"))
        self.prefix_obj.locations.add(*Location.objects.all())
        Prefix.objects.filter(pk=self.prefix_obj.pk).update(vlan=self.vlan)
        source = self.load([vlan_row("10.0.0.5/24", 10, "site1")])
        destination = nautobot_adapter()
        destination.load_prefixes()
        self.assertEqual(self.loaded(source), self.loaded(destination))
        self.assertEqual(self.loaded(source), [("10.0.0.0/24", 10, "aaa", "")])

    def test_the_rows_kept_from_the_address_read_are_not_requested_again(self):
        adapter = self.ipfabric_adapter()
        adapter.rows_naming_a_vlan = [vlan_row("10.0.0.5/24", 10)]
        adapter.load_prefixes()
        adapter.client.technology.addressing.managed_ip_ipv4.all.assert_not_called()
        self.assertEqual(self.loaded(adapter), [("10.0.0.0/24", 10, "site1", "")])

    def test_the_address_read_keeps_the_rows_naming_a_vlan_when_prefixes_are_in_scope(self):
        rows = [
            vlan_row("10.0.0.5/24", 10) | {"sn": "a", "intName": "e0", "ip": "10.0.0.5"},
            vlan_row("10.0.0.6/24", None),
        ]
        adapter = self.ipfabric_adapter(rows)
        adapter.load_data()
        columns = adapter.client.technology.addressing.managed_ip_ipv4.all.call_args.kwargs["columns"]
        self.assertIn("siteName", columns)
        self.assertEqual(adapter.rows_naming_a_vlan, rows[:1])

    def test_the_address_read_keeps_nothing_without_prefixes(self):
        adapter = self.ipfabric_adapter(scope=full_scope(prefixes=False))
        adapter.load_data()
        self.assertIsNone(adapter.rows_naming_a_vlan)
