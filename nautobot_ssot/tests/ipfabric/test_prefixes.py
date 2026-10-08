# pylint: disable=too-many-lines
"""Unit tests for syncing Prefixes from IP Fabric."""

from unittest.mock import MagicMock, patch

from diffsync.enum import DiffSyncFlags, DiffSyncModelFlags
from django.apps import apps as global_apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import JobResult, Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix, PrefixLocationAssignment, get_default_namespace

from nautobot_ssot.integrations.ipfabric.bulk_writes import THROUGH_LEVELS
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import (
    IPV6_MANAGED_IP_SUMMARY,
    IPFabricDiffSync,
    prefixes_overlapping_other_sites,
    sites_by_prefix,
)
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import DELETE_ORDER, NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.jobs import IpFabricDataSource
from nautobot_ssot.integrations.ipfabric.signals import nautobot_database_ready_callback
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache
from nautobot_ssot.tests.ipfabric.job_log import job_log_text


def summary_row(net, site="site1"):
    """Return a row of IP Fabric's managed IP summary table."""
    return {"net": net, "siteName": site}


def full_scope(**overrides):
    """Return a scope with every object type selected, less whatever the caller turns off."""
    selected = {syncable.key: True for syncable in SYNCABLE_OBJECTS}
    selected.update(overrides)
    return SyncScope(key for key, enabled in selected.items() if enabled)


def nautobot_adapter(**overrides):
    """Return a Nautobot adapter, with every object type in scope unless overridden."""
    kwargs = {
        "job": MagicMock(),
        "sync": MagicMock(),
        "sync_ipfabric_tagged_only": False,
        "location_filter": None,
        "scope": full_scope(),
        "safe_delete_mode": False,
    }
    kwargs.update(overrides)
    return NautobotDiffSync(**kwargs)


class SitesByPrefixTestCase(SimpleTestCase):
    """Grouping the summary table's rows, one per network per site, by network."""

    def test_a_network_seen_at_several_sites_is_one_entry(self):
        rows = [summary_row("10.0.0.0/24", "a"), summary_row("10.0.0.0/24", "b")]
        self.assertEqual(sites_by_prefix(rows, MagicMock()), {"10.0.0.0/24": {"a", "b"}})

    def test_a_network_reported_with_host_bits_is_the_network_it_names(self):
        """Both adapters must key a Prefix the same way, and Nautobot holds the network address."""
        self.assertEqual(sites_by_prefix([summary_row("10.0.0.1/24")], MagicMock()), {"10.0.0.0/24": {"site1"}})

    def test_ipv6_is_keyed_in_its_compressed_form(self):
        rows = [summary_row("FD00:0000:0000:0000::/64")]
        self.assertEqual(sites_by_prefix(rows, MagicMock()), {"fd00::/64": {"site1"}})

    def test_a_row_naming_no_network_is_skipped(self):
        logger = MagicMock()
        self.assertEqual(sites_by_prefix([{"net": None, "siteName": "a"}], logger), {})
        logger.warning.assert_not_called()

    def test_a_network_that_is_not_one_is_reported_and_skipped(self):
        logger = MagicMock()
        self.assertEqual(sites_by_prefix([summary_row("not-a-network")], logger), {})
        self.assertIn("not-a-network", job_log_text(logger, "warning"))

    def test_a_row_naming_no_site_still_reports_the_network(self):
        """The Prefix is synced. It is only the Location that is unknown."""
        self.assertEqual(
            sites_by_prefix([{"net": "10.0.0.0/24", "siteName": None}], MagicMock()), {"10.0.0.0/24": set()}
        )


class PrefixesOverlappingOtherSitesTestCase(SimpleTestCase):
    """Telling an address plan's own nesting from a range reused at unrelated sites."""

    def test_nesting_within_one_site_is_not_reported(self):
        self.assertEqual(prefixes_overlapping_other_sites({"10.0.0.0/24": {"a"}, "10.0.0.0/25": {"a"}}), [])

    def test_nesting_between_sites_sharing_one_is_not_reported(self):
        """A link network seen at both ends sits inside a summary seen at one of them."""
        by_prefix = {"10.0.0.0/16": {"a"}, "10.0.1.0/30": {"a", "b"}}
        self.assertEqual(prefixes_overlapping_other_sites(by_prefix), [])

    def test_nesting_between_unrelated_sites_reports_both_networks(self):
        by_prefix = {"10.0.0.0/24": {"azure"}, "10.0.0.0/25": {"aws"}, "192.168.0.0/24": {"aws"}}
        self.assertEqual(prefixes_overlapping_other_sites(by_prefix), ["10.0.0.0/24", "10.0.0.0/25"])

    def test_a_network_inside_several_others_is_counted_once(self):
        by_prefix = {"10.0.0.0/8": {"a"}, "10.0.0.0/16": {"b"}, "10.0.0.0/24": {"c"}}
        self.assertEqual(prefixes_overlapping_other_sites(by_prefix), ["10.0.0.0/8", "10.0.0.0/16", "10.0.0.0/24"])

    def test_ipv6_is_compared_within_its_own_version(self):
        by_prefix = {"fd00::/48": {"a"}, "fd00::/64": {"b"}, "10.0.0.0/8": {"a"}}
        self.assertEqual(prefixes_overlapping_other_sites(by_prefix), ["fd00::/48", "fd00::/64"])


class IPFabricPrefixLoadTestCase(SimpleTestCase):
    """Loading the networks IP Fabric reports into DiffSync models."""

    def build_adapter(self, ipv4_rows, ipv6_rows=(), sites=("site1",), scope=None, location_filter=None):  # pylint: disable=too-many-arguments
        """Return an IP Fabric adapter whose summary tables serve the given rows."""
        client = MagicMock()
        client.technology.addressing.managed_ipv4_summary.all.return_value = list(ipv4_rows)
        client.fetch_all.return_value = list(ipv6_rows)
        adapter = IPFabricDiffSync(
            job=MagicMock(),
            sync=MagicMock(),
            client=client,
            location_filter=location_filter,
            scope=scope if scope is not None else full_scope(),
        )
        for site in sites:
            adapter.add(adapter.location(adapter=adapter, name=site, site_id=site, status="Active"))
        return adapter

    def test_each_network_is_loaded_as_an_active_prefix(self):
        adapter = self.build_adapter([summary_row("10.0.0.0/24"), summary_row("10.0.1.0/24")])
        adapter.load_prefixes()
        self.assertEqual(
            {(prefix.prefix, prefix.status) for prefix in adapter.get_all("prefix")},
            {("10.0.0.0/24", "Active"), ("10.0.1.0/24", "Active")},
        )

    def test_ipv6_networks_are_read_from_their_own_table(self):
        adapter = self.build_adapter([], [summary_row("fd00::/64")])
        adapter.load_prefixes()
        adapter.client.fetch_all.assert_called_once_with(IPV6_MANAGED_IP_SUMMARY, columns=["net", "siteName"])
        self.assertEqual([prefix.prefix for prefix in adapter.get_all("prefix")], ["fd00::/64"])

    def test_each_site_a_network_is_seen_at_is_recorded(self):
        adapter = self.build_adapter(
            [summary_row("10.0.0.0/24", "site1"), summary_row("10.0.0.0/24", "site2")],
            sites=("site1", "site2"),
        )
        adapter.load_prefixes()
        self.assertEqual(
            sorted((pair.prefix, pair.location_name) for pair in adapter.get_all("prefix_location")),
            [("10.0.0.0/24", "site1"), ("10.0.0.0/24", "site2")],
        )

    def test_a_site_this_run_did_not_load_is_not_recorded(self):
        """A pair for a site the Location tree does not hold could only ever fail to be written."""
        adapter = self.build_adapter([summary_row("10.0.0.0/24", "elsewhere")])
        adapter.load_prefixes()
        self.assertEqual(len(adapter.get_all("prefix")), 1)
        self.assertEqual(adapter.get_all("prefix_location"), [])

    def test_an_unfiltered_run_may_delete_what_it_no_longer_reports(self):
        adapter = self.build_adapter([summary_row("10.0.0.0/24")])
        adapter.load_prefixes()
        self.assertNotIn(DiffSyncModelFlags.SKIP_UNMATCHED_DST, adapter.get("prefix", "10.0.0.0/24").model_flags)

    def test_a_location_filtered_run_may_delete_neither_a_prefix_nor_its_locations(self):
        """A filtered run sees one site's networks, so every other one would look absent."""
        adapter = self.build_adapter([summary_row("10.0.0.0/24")], location_filter="site1")
        adapter.load_prefixes()
        self.assertIn(DiffSyncModelFlags.SKIP_UNMATCHED_DST, adapter.get("prefix", "10.0.0.0/24").model_flags)
        self.assertIn(
            DiffSyncModelFlags.SKIP_UNMATCHED_DST,
            adapter.get("prefix_location", {"prefix": "10.0.0.0/24", "location_name": "site1"}).model_flags,
        )

    def test_networks_reused_at_unrelated_sites_are_reported_once(self):
        adapter = self.build_adapter(
            [summary_row("10.0.0.0/24", "azure"), summary_row("10.0.0.0/25", "aws")],
            sites=("azure", "aws"),
        )
        adapter.load_prefixes()
        warning = job_log_text(adapter.job.logger, "warning")
        self.assertIn("2 networks IP Fabric reports overlap a network it reports only at other sites", warning)
        self.assertIn("10.0.0.0/24, 10.0.0.0/25", warning)
        self.assertEqual(adapter.job.logger.warning.call_count, 1)

    def test_an_ordinary_address_plan_is_not_reported(self):
        adapter = self.build_adapter([summary_row("10.0.0.0/16"), summary_row("10.0.1.0/24")])
        adapter.load_prefixes()
        adapter.job.logger.warning.assert_not_called()

    def test_prefixes_out_of_scope_reads_neither_table(self):
        adapter = self.build_adapter([summary_row("10.0.0.0/24")], scope=full_scope(prefixes=False))
        adapter.client.inventory.sites.all.return_value = []
        adapter.client.devices.by_site = {}
        with patch.object(IPFabricDiffSync, "load_data", return_value=({}, {}, {})):
            adapter.load()
        self.assertEqual(adapter.get_all("prefix"), [])
        adapter.client.technology.addressing.managed_ipv4_summary.all.assert_not_called()

    def test_prefixes_in_scope_are_read_by_a_full_load(self):
        adapter = self.build_adapter([summary_row("10.0.0.0/24")], scope=full_scope(vrfs=False))
        adapter.client.inventory.sites.all.return_value = [{"siteName": "site1", "id": "site1"}]
        adapter.client.devices.by_site = {}
        with patch.object(IPFabricDiffSync, "load_data", return_value=({}, {}, {})):
            adapter.load()
        self.assertEqual([prefix.prefix for prefix in adapter.get_all("prefix")], ["10.0.0.0/24"])


class PrefixSyncOrderTestCase(SimpleTestCase):
    """Where Prefixes sit in the order DiffSync writes and Nautobot deletes."""

    def test_prefixes_are_written_before_the_addresses_under_the_location_tree(self):
        self.assertEqual(DiffSyncModelAdapters.top_level[0], "prefix")

    def test_a_prefix_is_put_at_its_locations_once_they_are_written(self):
        order = DiffSyncModelAdapters.top_level
        self.assertGreater(order.index("prefix_location"), order.index("location"))

    def test_prefixes_are_deleted_after_the_addresses_they_hold(self):
        self.assertGreater(DELETE_ORDER.index("_prefix"), DELETE_ORDER.index("_ipaddress"))

    def test_a_queued_location_assignment_is_a_row_bulk_mode_writes(self):
        self.assertIn(PrefixLocationAssignment, THROUGH_LEVELS)

    def test_prefixes_are_off_unless_selected(self):
        """Prefixes are what another IPAM system governs, so a sync must not start writing them."""
        self.assertFalse(SyncScope.from_job_kwargs({}).prefixes)


class PrefixTestCase(TestCase):
    """Base for the cases that write to the database.

    The signal callback makes the custom fields the sync stamps, which a test database built with the
    integration disabled does not have. The cache holds ORM objects, so it must not outlive a test's
    transaction; see test_cables.py.
    """

    def setUp(self):
        populate_status_choices()
        nautobot_database_ready_callback(sender=None, apps=global_apps)
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        self.namespace = get_default_namespace()
        self.adapter = nautobot_adapter()

    def make_prefix(self, prefix="10.0.0.0/24", tagged=True, **fields):
        """Create a Prefix in the Global Namespace, carrying the sync's Tag unless told otherwise."""
        fields.setdefault("status", self.active)
        prefix_obj = Prefix.objects.create(prefix=prefix, namespace=self.namespace, **fields)
        if tagged:
            prefix_obj.tags.add(self.adapter.ssot_tag)
        return prefix_obj

    def make_location(self, name="site1", location_type=None):
        """Create a Location, of a type permitting Prefixes unless one is given."""
        if location_type is None:
            location_type, _ = LocationType.objects.get_or_create(name="Site")
        return Location.objects.create(name=name, location_type=location_type, status=self.active)

    def prefix_model(self, prefix="10.0.0.0/24", status="Active"):
        """Return a DiffSync Prefix bound to this test's adapter."""
        return self.adapter.prefix(adapter=self.adapter, prefix=prefix, status=status)

    def pair_model(self, prefix="10.0.0.0/24", location_name="site1"):
        """Return a DiffSync PrefixLocation bound to this test's adapter."""
        return self.adapter.prefix_location(adapter=self.adapter, prefix=prefix, location_name=location_name)


class NautobotPrefixLoadTestCase(PrefixTestCase):
    """Loading the Prefixes Nautobot already holds."""

    def load(self, **overrides):
        """Return a Nautobot adapter that has loaded its Prefixes."""
        adapter = nautobot_adapter(**overrides)
        adapter.load_prefixes()
        return adapter

    def test_a_tagged_prefix_is_loaded_with_its_locations(self):
        self.make_prefix().locations.add(self.make_location())
        adapter = self.load()
        self.assertEqual([prefix.prefix for prefix in adapter.get_all("prefix")], ["10.0.0.0/24"])
        self.assertEqual(
            [(pair.prefix, pair.location_name) for pair in adapter.get_all("prefix_location")],
            [("10.0.0.0/24", "site1")],
        )

    def test_a_prefix_this_sync_has_not_marked_is_not_loaded(self):
        """Loaded, every Prefix another IPAM owns would be deleted the moment Prefixes were selected."""
        self.make_prefix(tagged=False)
        self.assertEqual(self.load().get_all("prefix"), [])

    def test_a_prefix_in_another_namespace_is_not_loaded(self):
        other = Namespace.objects.create(name="other")
        prefix_obj = Prefix.objects.create(prefix="10.0.0.0/24", namespace=other, status=self.active)
        prefix_obj.tags.add(self.adapter.ssot_tag)
        self.assertEqual(self.load().get_all("prefix"), [])

    def test_ipv6_is_keyed_as_the_ip_fabric_side_keys_it(self):
        self.make_prefix("fd00:0:0:0::/64")
        self.assertEqual([prefix.prefix for prefix in self.load().get_all("prefix")], ["fd00::/64"])

    def test_a_status_of_its_own_is_reported_as_active(self):
        """IP Fabric reports no status, so a Prefix held as Reserved is left so."""
        self.make_prefix(status=Status.objects.get(name="Reserved"))
        self.assertEqual(self.load().get("prefix", "10.0.0.0/24").status, "Active")

    def test_the_safe_delete_status_is_reported_so_it_can_be_restored(self):
        self.make_prefix(status=Status.objects.get(name="Deprecated"))
        self.assertEqual(self.load().get("prefix", "10.0.0.0/24").status, "Deprecated")

    def test_a_location_filtered_run_may_not_delete_a_prefix_or_its_locations(self):
        location = self.make_location()
        self.make_prefix().locations.add(location)
        adapter = self.load(location_filter=location)
        self.assertIn(DiffSyncModelFlags.SKIP_UNMATCHED_DST, adapter.get("prefix", "10.0.0.0/24").model_flags)
        self.assertIn(DiffSyncModelFlags.SKIP_UNMATCHED_DST, adapter.get_all("prefix_location")[0].model_flags)

    def test_prefixes_out_of_scope_loads_none(self):
        self.make_prefix()
        adapter = nautobot_adapter(scope=full_scope(prefixes=False))
        adapter.load()
        self.assertEqual(adapter.get_all("prefix"), [])

    def test_prefixes_in_scope_are_loaded_by_a_full_load(self):
        self.make_prefix()
        adapter = nautobot_adapter(scope=full_scope(vrfs=False))
        adapter.load()
        self.assertEqual([prefix.prefix for prefix in adapter.get_all("prefix")], ["10.0.0.0/24"])


class PrefixWriteTestCase(PrefixTestCase):
    """Creating, restoring and deleting a Prefix in Nautobot."""

    def create(self, prefix="10.0.0.0/24"):
        """Create a Prefix through the DiffSync model, as a sync would."""
        return self.adapter.prefix.create(self.adapter, {"prefix": prefix}, {"status": "Active"})

    def test_create_makes_an_active_network_in_the_global_namespace(self):
        self.assertIsNotNone(self.create())
        prefix_obj = Prefix.objects.get(network="10.0.0.0", prefix_length=24)
        self.assertEqual(prefix_obj.namespace, self.namespace)
        self.assertEqual(prefix_obj.type, "network")
        self.assertEqual(prefix_obj.status, self.active)

    def test_create_marks_the_prefix_as_synced(self):
        self.create()
        prefix_obj = Prefix.objects.get(network="10.0.0.0", prefix_length=24)
        self.assertTrue(prefix_obj.tags.filter(name="SSoT Synced from IPFabric").exists())
        self.assertEqual(prefix_obj.cf["system_of_record"], "IPFabric")

    def test_create_makes_an_ipv6_prefix(self):
        self.create("fd00::/64")
        self.assertTrue(Prefix.objects.filter(network="fd00::", prefix_length=64).exists())

    def test_create_adopts_the_prefix_nautobot_already_holds(self):
        """Unique on its network, so one already there is the Prefix this sync would have made."""
        existing = self.make_prefix(tagged=False, type="container", status=Status.objects.get(name="Reserved"))
        self.assertIsNotNone(self.create())
        self.assertEqual(Prefix.objects.filter(network="10.0.0.0", prefix_length=24).count(), 1)
        existing.refresh_from_db()
        self.assertTrue(existing.tags.filter(name="SSoT Synced from IPFabric").exists())
        self.assertEqual(existing.type, "container")
        self.assertEqual(existing.status.name, "Reserved")

    def test_create_does_not_adopt_a_prefix_of_another_length(self):
        self.make_prefix("10.0.0.0/16", tagged=False)
        self.create()
        self.assertTrue(Prefix.objects.filter(network="10.0.0.0", prefix_length=24).exists())

    def test_create_reports_a_prefix_nautobot_refuses(self):
        with patch.object(Prefix, "validated_save", side_effect=ValidationError("refused")):
            self.assertIsNone(self.create())
        self.assertIn("Unable to create a Prefix of 10.0.0.0/24", job_log_text(self.adapter.job.logger, "error"))

    def test_create_reports_an_adoption_nautobot_refuses_and_carries_on(self):
        """The Prefix exists either way, so the addresses under it can still be written."""
        self.make_prefix(tagged=False)
        with patch.object(nbutils, "tag_object", side_effect=ValidationError("refused")):
            self.assertIsNotNone(self.create())
        self.assertIn("Unable to mark the Prefix 10.0.0.0/24", job_log_text(self.adapter.job.logger, "error"))

    def test_update_restores_a_prefix_safe_delete_marked(self):
        self.make_prefix(status=Status.objects.get(name="Deprecated")).tags.add(self.adapter.safe_delete_tag)
        self.assertIsNotNone(self.prefix_model(status="Deprecated").update({"status": "Active"}))
        prefix_obj = Prefix.objects.get(network="10.0.0.0", prefix_length=24)
        self.assertEqual(prefix_obj.status, self.active)
        self.assertFalse(prefix_obj.tags.filter(name="SSoT Safe Delete").exists())

    def test_update_reports_a_prefix_that_is_no_longer_there(self):
        self.assertIsNone(self.prefix_model().update({"status": "Active"}))
        self.assertIn(
            "Unable to find a Prefix of 10.0.0.0/24 to update", job_log_text(self.adapter.job.logger, "error")
        )

    def test_update_reports_a_restore_nautobot_refuses(self):
        self.make_prefix(status=Status.objects.get(name="Deprecated"))
        with patch.object(nbutils, "tag_object", side_effect=ValidationError("refused")):
            self.assertIsNone(self.prefix_model(status="Deprecated").update({"status": "Active"}))
        self.assertIn("Unable to update the Prefix 10.0.0.0/24", job_log_text(self.adapter.job.logger, "error"))

    def test_a_prefix_ip_fabric_stops_reporting_is_deleted_on_completion(self):
        self.make_prefix()
        self.prefix_model().delete()
        self.adapter.sync_complete(MagicMock(), MagicMock())
        self.assertFalse(Prefix.objects.filter(network="10.0.0.0", prefix_length=24).exists())

    def test_a_prefix_still_holding_addresses_is_kept(self):
        """Nautobot refuses the delete, and the addresses under the Prefix are not this sync's to lose."""
        prefix_obj = self.make_prefix()
        IPAddress.objects.create(address="10.0.0.1/24", namespace=self.namespace, status=self.active)
        self.prefix_model().delete()
        self.adapter.sync_complete(MagicMock(), MagicMock())
        self.assertTrue(Prefix.objects.filter(pk=prefix_obj.pk).exists())
        self.assertIn("Deletion failed protected object", job_log_text(self.adapter.job.logger, "warning"))

    def test_safe_delete_marks_the_prefix_rather_than_removing_it(self):
        self.make_prefix()
        with patch.object(self.adapter, "safe_delete_mode", True):
            self.prefix_model().delete()
        prefix_obj = Prefix.objects.get(network="10.0.0.0", prefix_length=24)
        self.assertEqual(prefix_obj.status.name, "Deprecated")
        self.assertTrue(prefix_obj.tags.filter(name="SSoT Safe Delete").exists())

    def test_delete_reports_a_prefix_that_is_no_longer_there(self):
        self.assertIsNone(self.prefix_model().delete())
        self.assertIn(
            "Unable to find a Prefix of 10.0.0.0/24 to delete", job_log_text(self.adapter.job.logger, "error")
        )


class PrefixLocationWriteTestCase(PrefixTestCase):
    """Recording a Prefix at a Location, and taking it out of one."""

    def create(self, prefix="10.0.0.0/24", location_name="site1"):
        """Record a Prefix at a Location through the DiffSync model, as a sync would."""
        return self.adapter.prefix_location.create(self.adapter, {"prefix": prefix, "location_name": location_name}, {})

    def test_create_records_the_prefix_at_the_location(self):
        prefix_obj = self.make_prefix()
        location = self.make_location()
        self.assertIsNotNone(self.create())
        self.assertEqual(list(prefix_obj.locations.all()), [location])

    def test_create_lets_a_location_type_hold_prefixes_where_it_did_not(self):
        """Nautobot does not check this on the way in, so the sync grants it, as it does for VLANs."""
        location_type = LocationType.objects.create(name="no-prefixes")
        self.make_location(location_type=location_type)
        self.make_prefix()
        self.create()
        self.assertIn(ContentType.objects.get_for_model(Prefix), location_type.content_types.all())

    def test_a_location_nautobot_does_not_hold_is_counted_and_reported_once(self):
        self.make_prefix()
        self.make_prefix("10.0.1.0/24")
        self.assertIsNone(self.create(location_name="nowhere"))
        self.assertIsNone(self.create("10.0.1.0/24", location_name="nowhere"))
        self.assertEqual(self.adapter.prefix_locations_not_found, {"nowhere": 2})
        self.adapter.sync_complete(MagicMock(), MagicMock())
        self.assertIn(
            "Not recording 2 Prefixes at the Location named nowhere, as Nautobot holds no Location of that name.",
            job_log_text(self.adapter.job.logger, "warning"),
        )
        self.assertEqual(self.adapter.prefix_locations_not_found, {})

    def test_create_reports_a_prefix_that_is_not_there(self):
        self.make_location()
        self.assertIsNone(self.create())
        self.assertIn(
            "Unable to find a Prefix of 10.0.0.0/24 to record at the Location named site1",
            job_log_text(self.adapter.job.logger, "error"),
        )

    def test_create_reports_an_assignment_nautobot_refuses(self):
        self.make_location()
        with patch.object(nbutils, "get_prefix") as get_prefix:
            get_prefix.return_value.locations.add.side_effect = ValidationError("refused")
            self.assertIsNone(self.create())
        self.assertIn(
            "Unable to record the Prefix 10.0.0.0/24 at the Location named site1",
            job_log_text(self.adapter.job.logger, "error"),
        )

    def test_delete_takes_the_prefix_out_of_the_location_and_removes_neither(self):
        prefix_obj = self.make_prefix()
        location = self.make_location()
        prefix_obj.locations.add(location)
        self.assertIsNotNone(self.pair_model().delete())
        self.assertEqual(list(prefix_obj.locations.all()), [])
        self.assertTrue(Location.objects.filter(pk=location.pk).exists())

    def test_delete_reports_a_pair_that_is_no_longer_there(self):
        self.make_prefix()
        self.assertIsNone(self.pair_model().delete())
        self.assertIn(
            "Unable to find the Prefix 10.0.0.0/24 at the Location named site1",
            job_log_text(self.adapter.job.logger, "error"),
        )


class PrefixLocationBulkWriteTestCase(PrefixTestCase):
    """Recording a Prefix at a Location in Bulk Write Mode."""

    def setUp(self):
        super().setUp()
        self.adapter = nautobot_adapter(bulk_write_mode=True)

    def create(self):
        """Record a Prefix at a Location through the DiffSync model, as a sync would."""
        return self.adapter.prefix_location.create(
            self.adapter, {"prefix": "10.0.0.0/24", "location_name": "site1"}, {}
        )

    def test_the_assignment_is_written_with_the_queue(self):
        prefix_obj = self.make_prefix()
        location = self.make_location()
        self.create()
        self.assertEqual(list(prefix_obj.locations.all()), [])
        self.adapter.flush_pending_writes()
        self.assertEqual(list(prefix_obj.locations.all()), [location])

    def test_a_location_this_run_only_queued_is_found(self):
        """Locations are written in bulk too, so on a first sync the site may have no row yet."""
        prefix_obj = self.make_prefix()
        location_type, _ = LocationType.objects.get_or_create(name="Site")
        queued = Location(name="site1", location_type=location_type, status=self.active)
        self.adapter.pending.add(queued, key="site1")
        self.create()
        self.adapter.flush_pending_writes()
        self.assertEqual(list(prefix_obj.locations.all()), [queued])

    def test_a_queue_that_does_not_hold_the_location_falls_back_to_nautobot(self):
        prefix_obj = self.make_prefix()
        location = self.make_location()
        self.adapter.pending.add(
            Location(name="other", location_type=location.location_type, status=self.active), key="other"
        )
        self.create()
        self.adapter.flush_pending_writes()
        self.assertEqual(list(prefix_obj.locations.all()), [location])


class PrefixConvergenceTestCase(PrefixTestCase):
    """A second sync of unchanged networks must report nothing to do."""

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()
        self.sites = [{"siteName": "site1", "id": "1"}, {"siteName": "site2", "id": "2"}]
        self.ipv4_rows = [
            summary_row("10.0.0.0/24", "site1"),
            summary_row("10.0.0.0/24", "site2"),
            summary_row("10.0.1.0/30", "site1"),
        ]
        self.ipv6_rows = [summary_row("fd00::/64", "site2")]

    def ipf_client(self):
        """Return a mock IPFClient serving the sites and the managed IP summary tables."""
        client = MagicMock()
        client.inventory.sites.all.return_value = self.sites
        client.devices.by_site = {}
        client.technology.addressing.managed_ipv4_summary.all.return_value = self.ipv4_rows
        client.fetch_all = MagicMock(return_value=self.ipv6_rows)
        return client

    def job(self):
        """Return a job with a real JobResult, since the adapters log through it."""
        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="prefix convergence", worker="default")
        job.logger = MagicMock()
        job.debug = False
        return job

    def adapters(self, bulk_write_mode=False):
        """Return a loaded source and destination scoped to Locations and Prefixes."""
        job = self.job()
        scope = SyncScope(["locations", "prefixes"])
        source = IPFabricDiffSync(job=job, sync=None, client=self.ipf_client(), location_filter=None, scope=scope)
        with patch.object(IPFabricDiffSync, "load_data", return_value=({}, {}, {})):
            source.load()
        destination = nautobot_adapter(job=job, bulk_write_mode=bulk_write_mode, scope=scope)
        destination.load()
        return source, destination

    def assert_nothing_left_to_do(self):
        """Assert a fresh pair of adapters finds no difference."""
        source, destination = self.adapters()
        summary = destination.diff_from(source).summary()
        self.assertEqual((summary["create"], summary["update"], summary["delete"]), (0, 0, 0))

    def test_a_first_sync_writes_each_network_at_its_sites(self):
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        shared = Prefix.objects.get(network="10.0.0.0", prefix_length=24)
        self.assertEqual(sorted(shared.locations.values_list("name", flat=True)), ["site1", "site2"])
        self.assertEqual(Prefix.objects.count(), 3)
        self.assert_nothing_left_to_do()

    def test_a_bulk_mode_sync_converges_the_same_way(self):
        """The Locations are queued in bulk mode, which is what the assignments have to find."""
        source, destination = self.adapters(bulk_write_mode=True)
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        destination.flush_pending_writes()
        shared = Prefix.objects.get(network="10.0.0.0", prefix_length=24)
        self.assertEqual(sorted(shared.locations.values_list("name", flat=True)), ["site1", "site2"])
        self.assert_nothing_left_to_do()

    def test_a_network_ip_fabric_stops_reporting_at_one_site_leaves_that_site(self):
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        self.ipv4_rows = [row for row in self.ipv4_rows if row != summary_row("10.0.0.0/24", "site2")]
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        shared = Prefix.objects.get(network="10.0.0.0", prefix_length=24)
        self.assertEqual(list(shared.locations.values_list("name", flat=True)), ["site1"])
        self.assert_nothing_left_to_do()

    def test_a_network_ip_fabric_stops_reporting_is_removed(self):
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        self.ipv4_rows = [row for row in self.ipv4_rows if row["net"] != "10.0.1.0/30"]
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        self.assertFalse(Prefix.objects.filter(network="10.0.1.0", prefix_length=30).exists())
        self.assert_nothing_left_to_do()

    def test_a_prefix_another_system_holds_is_adopted_rather_than_duplicated(self):
        self.make_prefix(tagged=False)
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        self.assertEqual(Prefix.objects.filter(network="10.0.0.0", prefix_length=24).count(), 1)
        self.assert_nothing_left_to_do()

    def test_a_prefix_this_sync_never_marked_is_left_alone(self):
        """However unreported, a Prefix another system owns is not the sync's to delete."""
        self.make_prefix("172.16.0.0/12", tagged=False)
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        self.assertTrue(Prefix.objects.filter(network="172.16.0.0", prefix_length=12).exists())
