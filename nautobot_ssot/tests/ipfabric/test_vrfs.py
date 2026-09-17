# pylint: disable=too-many-lines
"""Unit tests for syncing VRFs and their Route Targets from IP Fabric."""

from unittest import mock

from diffsync.enum import DiffSyncFlags, DiffSyncModelFlags
from django.apps import apps as global_apps
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import JobResult, Role, Status
from nautobot.ipam.models import VRF, Namespace, RouteTarget, VRFDeviceAssignment, get_default_namespace

from nautobot_ssot.integrations.ipfabric.bulk_writes import LEVELS, THROUGH_LEVELS
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import (
    IPFabricDiffSync,
    agreed_targets,
    reconcile_vrfs,
)
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import DELETE_ORDER, NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import RouteTarget as DiffSyncRouteTarget
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Vrf
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import (
    VrfDeviceAssignment as DiffSyncVrfDeviceAssignment,
)
from nautobot_ssot.integrations.ipfabric.jobs import IpFabricDataSource
from nautobot_ssot.integrations.ipfabric.signals import nautobot_database_ready_callback
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import VRF_CONFLICT_CF_NAME
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

RD_CONFLICT = "IP Fabric's devices disagree about this VRF's route distinguisher"
RT_CONFLICT = "IP Fabric's devices disagree about this VRF's route targets"
BOTH_CONFLICT = "IP Fabric's devices disagree about this VRF's route distinguisher and route targets"


def detail_row(vrf, serial="a", rd=None):
    """Return a row of IP Fabric's VRF detail table."""
    return {"sn": serial, "hostname": f"host-{serial}", "vrf": vrf, "rd": rd}


def target_row(vrf, serial="a", rd=None, af="ipv4", import_rt=(), export_rt=()):  # pylint: disable=too-many-arguments
    """Return a row of IP Fabric's L3 VPN VRF route targets table."""
    return {
        "sn": serial,
        "hostname": f"host-{serial}",
        "vrf": vrf,
        "rd": rd,
        "af": af,
        "importRT": list(import_rt),
        "exportRT": list(export_rt),
    }


def full_scope(**overrides):
    """Return a scope with every object type selected, less whatever the caller turns off."""
    selected = {syncable.key: True for syncable in SYNCABLE_OBJECTS}
    selected.update(overrides)
    return SyncScope(key for key, enabled in selected.items() if enabled)


def nautobot_adapter(**overrides):
    """Return a Nautobot adapter, with every object type in scope unless overridden."""
    kwargs = {
        "job": mock.MagicMock(),
        "sync": mock.MagicMock(),
        "sync_ipfabric_tagged_only": False,
        "location_filter": None,
        "scope": full_scope(),
    }
    kwargs.update(overrides)
    return NautobotDiffSync(**kwargs)


def ipfabric_adapter(client=None, **overrides):
    """Return an IP Fabric adapter, with every object type in scope unless overridden."""
    kwargs = {
        "job": mock.MagicMock(),
        "sync": mock.MagicMock(),
        "client": client if client is not None else mock.MagicMock(),
        "location_filter": None,
        "scope": full_scope(),
    }
    kwargs.update(overrides)
    return IPFabricDiffSync(**kwargs)


def vrf_attrs(**overrides):
    """Return the attributes a DiffSync Vrf carries, with the unset ones at their empty values."""
    attrs = {"rd": None, "status": "Active", "import_targets": [], "export_targets": [], "conflict": ""}
    attrs.update(overrides)
    return attrs


class VrfTestCase(TestCase):
    """Base for the cases that write to the database.

    The signal callback makes the custom fields the sync stamps, which a test database built with
    the integration disabled does not have. The cache holds ORM objects, so it must not outlive a
    test's transaction; see test_cables.py.
    """

    # Set by each subclass, which decides what its adapter needs.
    adapter = None

    def setUp(self):
        populate_status_choices()
        nautobot_database_ready_callback(sender=None, apps=global_apps)
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        self.namespace = get_default_namespace()

    def create_vrf(self, name="BLUE", **attrs):
        """Create a VRF through the DiffSync model, as a sync would."""
        return self.adapter.vrf.create(self.adapter, {"name": name}, vrf_attrs(**attrs))


class AgreedTargetsTestCase(SimpleTestCase):
    """Reducing what each device reported to the one set they agree on."""

    def test_no_device_reported_any_targets(self):
        self.assertEqual(agreed_targets({}), ([], False))

    def test_one_device_reporting_is_agreement(self):
        self.assertEqual(agreed_targets({"a": {"65000:2", "65000:1"}}), (["65000:1", "65000:2"], False))

    def test_devices_reporting_the_same_set_agree(self):
        by_device = {"a": {"65000:1"}, "b": {"65000:1"}}
        self.assertEqual(agreed_targets(by_device), (["65000:1"], False))

    def test_devices_reporting_different_sets_disagree(self):
        by_device = {"a": {"65000:1"}, "b": {"65000:2"}}
        self.assertEqual(agreed_targets(by_device), ([], True))

    def test_a_device_reporting_none_disagrees_with_one_reporting_some(self):
        """An absent report is a report of nothing, not an abstention.

        A VRF configured with a route target on one device and not on another is misconfigured, and
        saying so is more use than silently taking the device that happens to have it.
        """
        by_device = {"a": {"65000:1"}, "b": set()}
        self.assertEqual(agreed_targets(by_device), ([], True))


class ReconcileVrfsTestCase(SimpleTestCase):
    """Turning per device, per address family reports into one record per VRF."""

    def test_a_vrf_every_device_agrees_on(self):
        reconciled = reconcile_vrfs(
            [detail_row("BLUE", "a", "65000:1"), detail_row("BLUE", "b", "65000:1")],
            [
                target_row("BLUE", "a", import_rt=["65000:1"], export_rt=["65000:1"]),
                target_row("BLUE", "b", import_rt=["65000:1"], export_rt=["65000:1"]),
            ],
        )
        self.assertEqual(
            reconciled["BLUE"],
            {"rd": "65000:1", "import_targets": ["65000:1"], "export_targets": ["65000:1"], "conflict": ""},
        )

    def test_a_vrf_with_neither_a_distinguisher_nor_targets_is_recorded_as_is(self):
        """The VRF detail table names VRFs that the route target table never mentions."""
        reconciled = reconcile_vrfs([detail_row("PLAIN")], [])
        self.assertEqual(
            reconciled["PLAIN"],
            {"rd": None, "import_targets": [], "export_targets": [], "conflict": ""},
        )

    def test_address_families_are_combined_rather_than_reconciled(self):
        """Nautobot holds one set of targets per VRF, so a device's families are one report."""
        reconciled = reconcile_vrfs(
            [detail_row("BLUE", "a", "65000:1")],
            [
                target_row("BLUE", "a", af="ipv4", import_rt=["65000:1"]),
                target_row("BLUE", "a", af="ipv6", import_rt=["65000:2"]),
            ],
        )
        self.assertEqual(reconciled["BLUE"]["import_targets"], ["65000:1", "65000:2"])
        self.assertEqual(reconciled["BLUE"]["conflict"], "")

    def test_a_disputed_distinguisher_is_dropped_and_recorded(self):
        reconciled = reconcile_vrfs(
            [detail_row("SPLIT", "a", "65000:1"), detail_row("SPLIT", "b", "65000:2")],
            [],
        )
        self.assertIsNone(reconciled["SPLIT"]["rd"])
        self.assertEqual(reconciled["SPLIT"]["conflict"], RD_CONFLICT)

    def test_disputed_targets_are_dropped_and_recorded(self):
        reconciled = reconcile_vrfs(
            [detail_row("SPLIT", "a", "65000:1"), detail_row("SPLIT", "b", "65000:1")],
            [
                target_row("SPLIT", "a", import_rt=["65000:1"]),
                target_row("SPLIT", "b", import_rt=["65000:9"]),
            ],
        )
        self.assertEqual(reconciled["SPLIT"]["import_targets"], [])
        self.assertEqual(reconciled["SPLIT"]["conflict"], RT_CONFLICT)

    def test_an_agreed_distinguisher_survives_disputed_targets(self):
        """The two are reconciled independently, so one dispute does not discard the other value."""
        reconciled = reconcile_vrfs(
            [detail_row("MIXED", "a", "65000:1"), detail_row("MIXED", "b", "65000:1")],
            [
                target_row("MIXED", "a", import_rt=["65000:1"]),
                target_row("MIXED", "b", import_rt=["65000:9"]),
            ],
        )
        self.assertEqual(reconciled["MIXED"]["rd"], "65000:1")
        self.assertEqual(reconciled["MIXED"]["import_targets"], [])

    def test_both_disputes_are_recorded_together(self):
        reconciled = reconcile_vrfs(
            [detail_row("BAD", "a", "65000:1"), detail_row("BAD", "b", "65000:2")],
            [
                target_row("BAD", "a", import_rt=["65000:1"]),
                target_row("BAD", "b", import_rt=["65000:9"]),
            ],
        )
        self.assertEqual(reconciled["BAD"]["conflict"], BOTH_CONFLICT)

    def test_no_target_rows_reports_no_targets_and_no_dispute(self):
        """The target table is not read when targets are out of scope, which reports none of them."""
        reconciled = reconcile_vrfs([detail_row("BLUE", "a", "65000:1")], [])
        self.assertEqual(reconciled["BLUE"]["import_targets"], [])
        self.assertEqual(reconciled["BLUE"]["export_targets"], [])
        self.assertEqual(reconciled["BLUE"]["rd"], "65000:1")
        self.assertEqual(reconciled["BLUE"]["conflict"], "")

    def test_a_distinguisher_only_the_target_table_reports_is_still_found(self):
        reconciled = reconcile_vrfs([detail_row("BLUE")], [target_row("BLUE", rd="65000:1")])
        self.assertEqual(reconciled["BLUE"]["rd"], "65000:1")

    def test_rows_naming_no_vrf_are_skipped(self):
        self.assertEqual(reconcile_vrfs([detail_row(None), {"sn": "a"}], []), {})


class IPFabricVrfLoadTestCase(SimpleTestCase):
    """Loading VRFs from IP Fabric's tables into DiffSync models."""

    def build_adapter(self, detail_rows, target_rows, scope=None, location_filter=None):
        """Return an IP Fabric adapter whose VRF tables serve the given rows."""
        client = mock.MagicMock()
        client.technology.routing.vrf_detail.all.return_value = detail_rows
        client.technology.mpls.l3vpn_vrf_targets.all.return_value = target_rows
        adapter = IPFabricDiffSync(
            job=mock.MagicMock(),
            sync=mock.MagicMock(),
            client=client,
            location_filter=location_filter,
            scope=scope if scope is not None else full_scope(),
        )
        return adapter

    def test_each_reconciled_vrf_is_loaded(self):
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1"), detail_row("RED", "a", "65000:2")],
            [target_row("BLUE", "a", import_rt=["65000:1"])],
        )
        adapter.load_vrfs()
        loaded = {vrf.name: vrf for vrf in adapter.get_all("vrf")}
        self.assertEqual(set(loaded), {"BLUE", "RED"})
        self.assertEqual(loaded["BLUE"].rd, "65000:1")
        self.assertEqual(loaded["BLUE"].import_targets, ["65000:1"])
        self.assertEqual(loaded["RED"].import_targets, [])

    def test_the_route_target_table_is_not_read_when_targets_are_out_of_scope(self):
        """It is the only table read solely for targets, so a narrowed run should not fetch it."""
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1")],
            [target_row("BLUE", "a", import_rt=["65000:1"])],
            scope=full_scope(route_targets=False),
        )
        adapter.load_vrfs()
        adapter.client.technology.mpls.l3vpn_vrf_targets.all.assert_not_called()
        self.assertEqual(adapter.get("vrf", "BLUE").import_targets, [])

    def test_the_vrf_summary_table_is_not_read(self):
        """It names the same VRFs as the detail table but carries no route distinguisher."""
        adapter = self.build_adapter([detail_row("BLUE")], [])
        adapter.load_vrfs()
        adapter.client.technology.routing.vrf_summary.all.assert_not_called()

    def test_an_unfiltered_run_may_delete_a_vrf_it_no_longer_reports(self):
        adapter = self.build_adapter([detail_row("BLUE")], [])
        adapter.load_vrfs()
        self.assertNotIn(DiffSyncModelFlags.SKIP_UNMATCHED_DST, adapter.get("vrf", "BLUE").model_flags)

    def test_a_location_filtered_run_may_not_delete_a_vrf(self):
        """A filtered run sees one site's VRFs, so every other VRF would look absent from IP Fabric."""
        adapter = self.build_adapter([detail_row("BLUE")], [], location_filter="site1")
        adapter.load_vrfs()
        self.assertIn(DiffSyncModelFlags.SKIP_UNMATCHED_DST, adapter.get("vrf", "BLUE").model_flags)

    def test_a_location_filtered_run_may_not_delete_a_route_target(self):
        """The Nautobot side loads every tagged Route Target, so a filtered run must delete none."""
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1")],
            [target_row("BLUE", "a", import_rt=["65000:1"])],
            location_filter="site1",
        )
        adapter.load_vrfs()
        self.assertIn(
            DiffSyncModelFlags.SKIP_UNMATCHED_DST,
            adapter.get("route_target", "65000:1").model_flags,
        )

    def test_vrfs_out_of_scope_loads_none(self):
        adapter = self.build_adapter([detail_row("BLUE")], [], scope=full_scope(vrfs=False, route_targets=False))
        adapter.client.inventory.sites.all.return_value = []
        adapter.client.devices.by_site = {}
        with mock.patch.object(IPFabricDiffSync, "load_data", return_value=({}, {}, {})):
            adapter.load()
        self.assertEqual(adapter.get_all("vrf"), [])
        adapter.client.technology.routing.vrf_detail.all.assert_not_called()


class NautobotVrfLoadTestCase(VrfTestCase):
    """Loading VRFs Nautobot already holds."""

    def build_adapter(self, scope=None, location_filter=None):
        """Return a loaded Nautobot adapter."""
        adapter = nautobot_adapter(
            location_filter=location_filter,
            scope=scope if scope is not None else full_scope(),
        )
        adapter.load_vrfs()
        return adapter

    def test_a_vrf_is_loaded_with_its_distinguisher_and_targets(self):
        vrf = VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        vrf.import_targets.add(RouteTarget.objects.create(name="65000:1"))
        vrf.export_targets.add(RouteTarget.objects.create(name="65000:2"))

        loaded = self.build_adapter().get("vrf", "BLUE")
        self.assertEqual(loaded.rd, "65000:1")
        self.assertEqual(loaded.import_targets, ["65000:1"])
        self.assertEqual(loaded.export_targets, ["65000:2"])

    def test_targets_out_of_scope_are_reported_as_none(self):
        """Matching what the IP Fabric adapter reports, so that neither side writes the lists."""
        vrf = VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        vrf.import_targets.add(RouteTarget.objects.create(name="65000:1"))

        loaded = self.build_adapter(scope=full_scope(route_targets=False)).get("vrf", "BLUE")
        self.assertEqual(loaded.import_targets, [])

    def test_a_recorded_conflict_is_loaded_back(self):
        """So that a VRF whose conflict persists is not rewritten on every run."""
        VRF.objects.create(
            name="SPLIT",
            namespace=self.namespace,
            status=self.active,
            _custom_field_data={VRF_CONFLICT_CF_NAME: RD_CONFLICT},
        )
        self.assertEqual(self.build_adapter().get("vrf", "SPLIT").conflict, RD_CONFLICT)

    def test_a_vrf_in_another_namespace_is_not_loaded(self):
        other = Namespace.objects.create(name="other")
        VRF.objects.create(name="ELSEWHERE", rd="65000:3", namespace=other, status=self.active)
        self.assertEqual(self.build_adapter().get_all("vrf"), [])

    def test_a_duplicated_name_loads_neither_vrf(self):
        """Nautobot allows two VRFs of one name, and IP Fabric reports nothing telling them apart."""
        VRF.objects.create(name="TWICE", rd="65000:1", namespace=self.namespace, status=self.active)
        VRF.objects.create(name="TWICE", rd="65000:2", namespace=self.namespace, status=self.active)
        self.assertEqual(self.build_adapter().get_all("vrf"), [])

    def test_a_vrf_with_no_status_is_loaded(self):
        """`VRF.status` is optional in Nautobot, so a VRF another process made may carry none."""
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace)
        self.assertEqual(self.build_adapter().get("vrf", "BLUE").status, "Active")

    def test_a_location_filtered_run_may_not_delete_a_vrf(self):
        site_lt, _ = LocationType.objects.get_or_create(name="site")
        site = Location.objects.create(name="site1", location_type=site_lt, status=self.active)
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)

        loaded = self.build_adapter(location_filter=site).get("vrf", "BLUE")
        self.assertIn(DiffSyncModelFlags.SKIP_UNMATCHED_DST, loaded.model_flags)


class VrfWriteTestCase(VrfTestCase):
    """Creating, updating and deleting a VRF in Nautobot."""

    def setUp(self):
        super().setUp()
        self.adapter = nautobot_adapter()
        # `safe_delete_mode` is read from the model rather than from the adapter, so both are set:
        # the model decides whether a delete removes or marks, the adapter whether the queue drains.
        self.adapter.safe_delete_mode = False
        patched = mock.patch.object(Vrf, "safe_delete_mode", False)
        patched.start()
        self.addCleanup(patched.stop)

    def test_create_makes_the_vrf_in_the_global_namespace(self):
        self.create_vrf(rd="65000:1")
        vrf = VRF.objects.get(name="BLUE")
        self.assertEqual(vrf.rd, "65000:1")
        self.assertEqual(vrf.namespace, self.namespace)
        self.assertEqual(vrf.status, self.active)

    def test_create_records_the_route_targets_nautobot_holds(self):
        """Route Targets are synced as their own object type and written before the VRFs naming them."""
        RouteTarget.objects.create(name="65000:1")
        RouteTarget.objects.create(name="65000:2")
        self.create_vrf(import_targets=["65000:1"], export_targets=["65000:1", "65000:2"])
        vrf = VRF.objects.get(name="BLUE")
        self.assertEqual([target.name for target in vrf.import_targets.all()], ["65000:1"])
        self.assertEqual(
            sorted(target.name for target in vrf.export_targets.all()),
            ["65000:1", "65000:2"],
        )

    def test_create_reports_a_route_target_nautobot_does_not_hold(self):
        """One missing here is one whose own creation was refused, so the rest are still recorded."""
        RouteTarget.objects.create(name="65000:1")
        self.create_vrf(import_targets=["65000:1", "65000:9"])
        self.assertEqual([target.name for target in VRF.objects.get(name="BLUE").import_targets.all()], ["65000:1"])
        self.adapter.job.logger.warning.assert_called()

    def test_create_points_at_the_route_target_nautobot_already_holds(self):
        existing = RouteTarget.objects.create(name="65000:1")
        self.create_vrf(import_targets=["65000:1"])
        self.assertEqual(RouteTarget.objects.count(), 1)
        self.assertEqual(VRF.objects.get(name="BLUE").import_targets.first(), existing)

    def test_create_records_a_conflict(self):
        self.create_vrf(conflict=RD_CONFLICT)
        self.assertEqual(VRF.objects.get(name="BLUE").cf[VRF_CONFLICT_CF_NAME], RD_CONFLICT)

    def test_create_marks_the_vrf_as_synced(self):
        self.create_vrf()
        vrf = VRF.objects.get(name="BLUE")
        self.assertEqual(vrf.cf["system_of_record"], "IPFabric")
        self.assertTrue(vrf.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_create_declines_a_distinguisher_another_vrf_already_holds(self):
        """A route distinguisher is unique within a Namespace, so the second VRF cannot take it."""
        VRF.objects.create(name="FIRST", rd="65000:1", namespace=self.namespace, status=self.active)
        self.assertIsNone(self.create_vrf(name="SECOND", rd="65000:1"))
        self.assertFalse(VRF.objects.filter(name="SECOND").exists())
        self.adapter.job.logger.error.assert_called()

    def test_create_declines_a_name_the_loader_found_ambiguous(self):
        VRF.objects.create(name="TWICE", rd="65000:1", namespace=self.namespace, status=self.active)
        VRF.objects.create(name="TWICE", rd="65000:2", namespace=self.namespace, status=self.active)
        self.adapter.load_vrfs()

        self.assertIsNone(self.create_vrf(name="TWICE", rd="65000:3"))
        self.assertEqual(VRF.objects.filter(name="TWICE").count(), 2)

    def loaded_model(self, name="BLUE"):
        """Return the DiffSync model for a VRF Nautobot holds."""
        self.adapter.load_vrfs()
        return self.adapter.get("vrf", name)

    def test_update_sets_a_new_distinguisher(self):
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        self.loaded_model().update({"rd": "65000:2"})
        self.assertEqual(VRF.objects.get(name="BLUE").rd, "65000:2")

    def test_update_clears_a_distinguisher_ip_fabric_no_longer_reports(self):
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        self.loaded_model().update({"rd": None})
        self.assertIsNone(VRF.objects.get(name="BLUE").rd)

    def test_update_replaces_the_route_targets(self):
        vrf = VRF.objects.create(name="BLUE", namespace=self.namespace, status=self.active)
        vrf.import_targets.add(RouteTarget.objects.create(name="65000:1"))
        RouteTarget.objects.create(name="65000:2")
        self.loaded_model().update({"import_targets": ["65000:2"]})
        self.assertEqual([target.name for target in vrf.import_targets.all()], ["65000:2"])

    def test_update_leaves_the_other_target_list_alone(self):
        """Both are written together, so the list that did not change is read from the model."""
        vrf = VRF.objects.create(name="BLUE", namespace=self.namespace, status=self.active)
        vrf.export_targets.add(RouteTarget.objects.create(name="65000:9"))
        self.loaded_model().update({"import_targets": ["65000:2"]})
        self.assertEqual([target.name for target in vrf.export_targets.all()], ["65000:9"])

    def test_update_records_a_conflict(self):
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        self.loaded_model().update({"conflict": RT_CONFLICT})
        self.assertEqual(VRF.objects.get(name="BLUE").cf[VRF_CONFLICT_CF_NAME], RT_CONFLICT)

    def test_update_reports_a_vrf_that_is_no_longer_there(self):
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        model = self.loaded_model()
        VRF.objects.filter(name="BLUE").delete()
        self.assertIsNone(model.update({"rd": "65000:2"}))
        self.adapter.job.logger.error.assert_called()

    def test_delete_queues_the_vrf_when_safe_delete_is_off(self):
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        self.loaded_model().delete()
        self.assertEqual(
            [vrf.name for vrf in self.adapter.objects_to_delete["_vrf"]],
            ["BLUE"],
        )

    def test_a_queued_vrf_is_deleted_on_completion(self):
        """The deletion order has to name the grouping, or the queue is built and never drained."""
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        self.loaded_model().delete()
        self.adapter.sync_complete(mock.MagicMock(), mock.MagicMock())
        self.assertFalse(VRF.objects.filter(name="BLUE").exists())

    def test_safe_delete_marks_the_vrf_rather_than_removing_it(self):
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        model = self.loaded_model()
        with mock.patch.object(Vrf, "safe_delete_mode", True):
            model.delete()
        vrf = VRF.objects.get(name="BLUE")
        self.assertEqual(vrf.status.name, "Deprecated")
        self.assertTrue(vrf.tags.filter(name="SSoT Safe Delete").exists())

    def test_update_to_active_clears_the_safe_delete_tag(self):
        """A VRF IP Fabric reports again is brought back, rather than left marked for deletion."""
        VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        model = self.loaded_model()
        with mock.patch.object(Vrf, "safe_delete_mode", True):
            model.delete()

        model.update({"status": "Active"})
        vrf = VRF.objects.get(name="BLUE")
        self.assertEqual(vrf.status.name, "Active")
        self.assertFalse(vrf.tags.filter(name="SSoT Safe Delete").exists())


class VrfConvergenceTestCase(VrfTestCase):
    """A second sync of unchanged VRFs must report nothing to do.

    A sync that reports the same change on every run is as much a defect as one that fails, and it
    comes from the two adapters describing one object differently — an empty route distinguisher as
    `""` on one side and `None` on the other, or target lists in different orders.
    """

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()
        self.detail_rows = [
            detail_row("BLUE", "a", "65000:1"),
            detail_row("BLUE", "b", "65000:1"),
            detail_row("PLAIN", "a"),
            detail_row("SPLIT", "a", "65000:8"),
            detail_row("SPLIT", "b", "65000:9"),
        ]
        self.target_rows = [
            target_row("BLUE", "a", af="ipv4", import_rt=["65000:1"], export_rt=["65000:1"]),
            target_row("BLUE", "a", af="ipv6", import_rt=["65000:2"], export_rt=["65000:1"]),
            target_row("BLUE", "b", import_rt=["65000:2", "65000:1"], export_rt=["65000:1"]),
        ]

    def ipf_client(self):
        """Return a mock IPFClient serving only the VRF tables."""
        client = mock.MagicMock()
        client.inventory.sites.all.return_value = []
        client.devices.by_site = {}
        client.inventory.interfaces.all.return_value = []
        client.technology.platforms.stacks_members.all.return_value = []
        client.fetch_all = mock.MagicMock(return_value=[])
        client.technology.routing.vrf_detail.all.return_value = self.detail_rows
        client.technology.mpls.l3vpn_vrf_targets.all.return_value = self.target_rows
        return client

    def job(self):
        """Return a job with a real JobResult, since the adapters log through it."""
        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="vrf convergence", worker="default")
        job.logger = mock.MagicMock()
        job.debug = False
        return job

    def adapters(self, bulk_write_mode=False):
        """Return a loaded source and destination scoped to VRFs and their Route Targets."""
        job = self.job()
        scope = full_scope()
        source = ipfabric_adapter(client=self.ipf_client(), job=job, sync=None, scope=scope)
        source.load()
        destination = nautobot_adapter(job=job, bulk_write_mode=bulk_write_mode, scope=scope)
        destination.load()
        return source, destination

    def test_a_second_sync_of_unchanged_vrfs_reports_nothing(self):
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)

        self.assertEqual(
            sorted(VRF.objects.values_list("name", flat=True)),
            ["BLUE", "PLAIN", "SPLIT"],
        )

        source, destination = self.adapters()
        diff = destination.diff_from(source)
        self.assertEqual(diff.summary()["update"], 0, f"Second sync still reports changes: {diff.str()}")
        self.assertEqual(diff.summary()["create"], 0, f"Second sync still reports creates: {diff.str()}")
        self.assertEqual(diff.summary()["delete"], 0, f"Second sync still reports deletes: {diff.str()}")

    def test_the_first_sync_writes_what_was_reconciled(self):
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)

        blue = VRF.objects.get(name="BLUE")
        self.assertEqual(blue.rd, "65000:1")
        self.assertEqual(
            sorted(target.name for target in blue.import_targets.all()),
            ["65000:1", "65000:2"],
        )
        self.assertEqual(blue.cf[VRF_CONFLICT_CF_NAME], "")

        split = VRF.objects.get(name="SPLIT")
        self.assertIsNone(split.rd)
        self.assertEqual(split.cf[VRF_CONFLICT_CF_NAME], RD_CONFLICT)

    def test_a_vrf_ip_fabric_stops_reporting_is_removed(self):
        source, destination = self.adapters()
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)

        self.detail_rows = [row for row in self.detail_rows if row["vrf"] != "PLAIN"]
        source, destination = self.adapters()
        # Set on the model and on the adapter, as the Job does: the model decides whether a delete
        # removes or marks, and the adapter whether the queue it builds is drained.
        with (
            mock.patch.object(Vrf, "safe_delete_mode", False),
            mock.patch.object(destination, "safe_delete_mode", False),
        ):
            destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)

        self.assertFalse(VRF.objects.filter(name="PLAIN").exists())
        self.assertTrue(VRF.objects.filter(name="BLUE").exists())

    def test_a_bulk_mode_sync_converges_the_same_way(self):
        """A run's output must not depend on the write mode it ran in."""
        source, destination = self.adapters(bulk_write_mode=True)
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        destination.flush_pending_writes()

        self.assertEqual(
            sorted(VRF.objects.values_list("name", flat=True)),
            ["BLUE", "PLAIN", "SPLIT"],
        )
        blue = VRF.objects.get(name="BLUE")
        self.assertEqual(blue.rd, "65000:1")
        self.assertEqual(sorted(target.name for target in blue.import_targets.all()), ["65000:1", "65000:2"])

        source, destination = self.adapters()
        diff = destination.diff_from(source)
        self.assertEqual(diff.summary()["update"], 0, f"Second sync still reports changes: {diff.str()}")
        self.assertEqual(diff.summary()["create"], 0, f"Second sync still reports creates: {diff.str()}")
        self.assertEqual(diff.summary()["delete"], 0, f"Second sync still reports deletes: {diff.str()}")


class VrfBulkWriteTestCase(VrfTestCase):
    """Writing VRFs and their Route Target join rows in Bulk Write Mode."""

    def setUp(self):
        super().setUp()
        self.adapter = nautobot_adapter(bulk_write_mode=True)

    def test_vrfs_are_written_after_the_models_that_do_not_reference_them(self):
        """A reordering here would insert a VRF before something it needs."""
        self.assertIn(VRF, LEVELS)
        self.assertIn(VRF.import_targets.through, THROUGH_LEVELS)
        self.assertIn(VRF.export_targets.through, THROUGH_LEVELS)

    def test_nothing_is_written_before_the_flush(self):
        self.create_vrf(rd="65000:1")
        self.assertFalse(VRF.objects.filter(name="BLUE").exists())

    def test_a_queued_vrf_lands_with_its_stamp_and_tag(self):
        self.create_vrf(rd="65000:1", conflict=RD_CONFLICT)
        self.adapter.flush_pending_writes()

        vrf = VRF.objects.get(name="BLUE")
        self.assertEqual(vrf.rd, "65000:1")
        self.assertEqual(vrf.namespace, self.namespace)
        self.assertEqual(vrf.cf["system_of_record"], "IPFabric")
        self.assertEqual(vrf.cf[VRF_CONFLICT_CF_NAME], RD_CONFLICT)
        self.assertTrue(vrf.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_a_queued_vrf_gets_its_route_target_join_rows(self):
        """`set()` needs a saved VRF, so a queued one gets the join rows directly instead."""
        RouteTarget.objects.create(name="65000:1")
        RouteTarget.objects.create(name="65000:2")
        self.create_vrf(import_targets=["65000:1", "65000:2"], export_targets=["65000:1"])
        self.adapter.flush_pending_writes()

        vrf = VRF.objects.get(name="BLUE")
        self.assertEqual(sorted(target.name for target in vrf.import_targets.all()), ["65000:1", "65000:2"])
        self.assertEqual([target.name for target in vrf.export_targets.all()], ["65000:1"])

    def test_a_route_target_is_written_immediately_rather_than_queued(self):
        """A VRF's join rows need the target's row to exist already, in either mode."""
        self.adapter.route_target.create(self.adapter, {"name": "65000:1"}, {})
        self.assertTrue(RouteTarget.objects.filter(name="65000:1").exists())

    def test_a_queued_vrf_points_at_a_route_target_nautobot_already_holds(self):
        existing = RouteTarget.objects.create(name="65000:1")
        self.create_vrf(import_targets=["65000:1"])
        self.adapter.flush_pending_writes()

        self.assertEqual(RouteTarget.objects.filter(name="65000:1").count(), 1)
        self.assertEqual(VRF.objects.get(name="BLUE").import_targets.first(), existing)

    def test_join_rows_are_dropped_when_their_vrf_is_refused(self):
        """A refused VRF leaves nothing for its join rows to point at, which would fail the flush."""
        VRF.objects.create(name="FIRST", rd="65000:1", namespace=self.namespace, status=self.active)
        RouteTarget.objects.create(name="65000:9")
        self.create_vrf(name="SECOND", rd="65000:1", import_targets=["65000:9"])
        self.adapter.flush_pending_writes()

        self.assertFalse(VRF.objects.filter(name="SECOND").exists())
        self.assertEqual(VRF.import_targets.through.objects.count(), 0)

    def test_bulk_mode_lands_the_same_vrf_as_the_per_object_path(self):
        """The two paths must agree, or a sync's output would depend on the mode it ran in."""
        RouteTarget.objects.create(name="65000:1")
        RouteTarget.objects.create(name="65000:2")
        self.create_vrf(name="BULK", rd="65000:1", import_targets=["65000:1"], export_targets=["65000:2"])
        self.adapter.flush_pending_writes()

        per_object = nautobot_adapter()
        per_object.vrf.create(
            per_object,
            {"name": "SINGLE"},
            {
                "rd": "65000:2",
                "status": "Active",
                "import_targets": ["65000:1"],
                "export_targets": ["65000:2"],
                "conflict": "",
            },
        )

        def state(name):
            vrf = VRF.objects.get(name=name)
            return (
                vrf.namespace_id,
                vrf.status_id,
                sorted(target.name for target in vrf.import_targets.all()),
                sorted(target.name for target in vrf.export_targets.all()),
                vrf.cf["system_of_record"],
                sorted(tag.name for tag in vrf.tags.all()),
            )

        self.assertEqual(state("BULK"), state("SINGLE"))


class RouteTargetTestCase(VrfTestCase):
    """Syncing Route Targets as an object type of their own."""

    def setUp(self):
        super().setUp()
        self.adapter = nautobot_adapter()
        patched = mock.patch.object(DiffSyncRouteTarget, "safe_delete_mode", False)
        patched.start()
        self.addCleanup(patched.stop)

    def create(self, name="65000:1"):
        """Create a Route Target through the DiffSync model, as a sync would."""
        return self.adapter.route_target.create(self.adapter, {"name": name}, {})

    def test_route_targets_are_written_before_the_vrfs_that_name_them(self):
        """A reordering here would have a VRF resolve targets that do not exist yet."""
        top_level = DiffSyncModelAdapters.top_level
        self.assertLess(top_level.index("route_target"), top_level.index("vrf"))

    def test_create_makes_the_route_target(self):
        self.create()
        route_target = RouteTarget.objects.get(name="65000:1")
        self.assertEqual(route_target.cf["system_of_record"], "IPFabric")
        self.assertTrue(route_target.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_create_adopts_one_nautobot_already_holds(self):
        """The name is unique across Nautobot, so one another process made is the same object."""
        existing = RouteTarget.objects.create(name="65000:1")
        self.create()
        self.assertEqual(RouteTarget.objects.filter(name="65000:1").count(), 1)
        existing.refresh_from_db()
        self.assertTrue(existing.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_create_reports_a_value_nautobot_refuses(self):
        """A route target longer than the field allows is named rather than ending the sync."""
        self.assertIsNone(self.create(name="6" * 40))
        self.assertFalse(RouteTarget.objects.filter(name__startswith="6666").exists())
        self.adapter.job.logger.error.assert_called()

    def test_delete_queues_the_route_target(self):
        self.create()
        self.adapter.load_route_targets()
        self.adapter.get("route_target", "65000:1").delete()
        self.assertEqual(
            [each.name for each in self.adapter.objects_to_delete["_routetarget"]],
            ["65000:1"],
        )

    def test_a_queued_route_target_is_deleted_on_completion(self):
        """The deletion order has to name the grouping, or the queue is built and never drained."""
        self.create()
        self.adapter.load_route_targets()
        self.adapter.get("route_target", "65000:1").delete()
        self.adapter.safe_delete_mode = False
        self.adapter.sync_complete(mock.MagicMock(), mock.MagicMock())
        self.assertFalse(RouteTarget.objects.filter(name="65000:1").exists())

    def test_route_targets_are_deleted_after_the_vrfs_that_name_them(self):
        order = DELETE_ORDER
        self.assertLess(order.index("_vrf"), order.index("_routetarget"))

    def test_safe_delete_marks_the_route_target_rather_than_removing_it(self):
        """A Route Target has no Status, so the Tag is all a safe delete can leave."""
        self.create()
        self.adapter.load_route_targets()
        with mock.patch.object(DiffSyncRouteTarget, "safe_delete_mode", True):
            self.adapter.get("route_target", "65000:1").delete()
        route_target = RouteTarget.objects.get(name="65000:1")
        self.assertTrue(route_target.tags.filter(name="SSoT Safe Delete").exists())

    def test_only_route_targets_this_sync_made_are_loaded(self):
        """One another system owns must not look absent from IP Fabric and be deleted."""
        RouteTarget.objects.create(name="65000:9")
        self.create(name="65000:1")

        self.adapter.load_route_targets()

        self.assertEqual([each.name for each in self.adapter.get_all("route_target")], ["65000:1"])

    def test_a_location_filtered_run_may_not_delete_a_route_target(self):
        """Every tagged Route Target is loaded whatever the filter, so none may be deleted under one."""
        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site = Location.objects.create(name="rt-site", location_type=site_type, status=self.active)
        self.create()

        adapter = nautobot_adapter(location_filter=site)
        adapter.load_route_targets()

        self.assertIn(
            DiffSyncModelFlags.SKIP_UNMATCHED_DST,
            adapter.get("route_target", "65000:1").model_flags,
        )

    def test_route_targets_out_of_scope_loads_none(self):
        self.create()
        adapter = nautobot_adapter(scope=full_scope(route_targets=False))
        adapter.load_data()
        self.assertEqual(adapter.get_all("route_target"), [])


class VrfDeviceAssignmentTestCase(VrfTestCase):
    """Recording which Devices carry each VRF."""

    def setUp(self):
        super().setUp()

        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(ContentType.objects.get_for_model(Device))
        self.site = Location.objects.create(name="site1", location_type=site_type, status=self.active)
        role = Role.objects.create(name="router")
        role.content_types.add(ContentType.objects.get_for_model(Device))
        manufacturer = Manufacturer.objects.create(name="vendor")
        device_type = DeviceType.objects.create(model="model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="rtr1",
            status=self.active,
            role=role,
            location=self.site,
            device_type=device_type,
        )
        self.vrf = VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)

        self.adapter = nautobot_adapter()
        patched = mock.patch.object(DiffSyncVrfDeviceAssignment, "safe_delete_mode", False)
        patched.start()
        self.addCleanup(patched.stop)

    def create(self, vrf_name="BLUE", device_name="rtr1"):
        """Assign a VRF to a Device through the DiffSync model, as a sync would."""
        return self.adapter.vrf_device_assignment.create(
            self.adapter, {"vrf_name": vrf_name, "device_name": device_name}, {}
        )

    def test_assignments_are_written_after_both_ends(self):
        """A reordering here would assign a VRF or a Device that has not been written yet."""
        top_level = DiffSyncModelAdapters.top_level
        self.assertLess(top_level.index("vrf"), top_level.index("vrf_device_assignment"))
        self.assertLess(top_level.index("location"), top_level.index("vrf_device_assignment"))

    def test_assignments_are_deleted_before_the_ends_they_join(self):
        """Nautobot cascades them away with either end, which would leave the queue pointing at nothing."""
        self.assertLess(DELETE_ORDER.index("_vrfdeviceassignment"), DELETE_ORDER.index("_device"))
        self.assertLess(DELETE_ORDER.index("_vrfdeviceassignment"), DELETE_ORDER.index("_vrf"))

    def test_create_assigns_the_vrf_to_the_device(self):
        self.create()
        self.assertEqual([vrf.name for vrf in self.device.vrfs.all()], ["BLUE"])

    def test_the_assignment_inherits_the_vrfs_distinguisher_and_name(self):
        """Nautobot's `clean()` would do this, and a batched write never runs it."""
        self.create()
        assignment = VRFDeviceAssignment.objects.get(vrf=self.vrf, device=self.device)
        self.assertEqual(assignment.rd, "65000:1")
        self.assertEqual(assignment.name, "BLUE")

    def test_create_reports_a_vrf_that_is_not_there(self):
        self.assertIsNone(self.create(vrf_name="ABSENT"))
        self.adapter.job.logger.error.assert_called()

    def test_create_reports_a_device_that_is_not_there(self):
        self.assertIsNone(self.create(device_name="absent"))
        self.adapter.job.logger.error.assert_called()

    def test_create_will_not_assign_to_a_device_outside_a_tagged_only_run(self):
        """What gates writing a Device has to gate assigning a VRF to it."""
        adapter = nautobot_adapter(sync_ipfabric_tagged_only=True)
        self.assertIsNone(
            adapter.vrf_device_assignment.create(adapter, {"vrf_name": "BLUE", "device_name": "rtr1"}, {})
        )
        self.assertEqual(VRFDeviceAssignment.objects.count(), 0)

    def test_delete_removes_the_assignment(self):
        self.create()
        self.adapter.load_vrfs()
        self.adapter.load_vrf_device_assignments(Device.objects.all())
        self.adapter.get("vrf_device_assignment", "BLUE__rtr1").delete()
        self.adapter.safe_delete_mode = False
        self.adapter.sync_complete(mock.MagicMock(), mock.MagicMock())

        self.assertEqual(VRFDeviceAssignment.objects.count(), 0)
        self.assertTrue(VRF.objects.filter(name="BLUE").exists())
        self.assertTrue(Device.objects.filter(name="rtr1").exists())

    def test_safe_delete_leaves_the_assignment_in_place(self):
        """It has neither a Status nor a Tag, so there is nothing for a safe delete to mark."""
        self.create()
        self.adapter.load_vrfs()
        self.adapter.load_vrf_device_assignments(Device.objects.all())
        with mock.patch.object(DiffSyncVrfDeviceAssignment, "safe_delete_mode", True):
            self.adapter.get("vrf_device_assignment", "BLUE__rtr1").delete()
        self.assertEqual(VRFDeviceAssignment.objects.count(), 1)

    def test_an_assignment_whose_vrf_was_not_loaded_is_not_loaded(self):
        """A VRF the sync holds no opinion about takes its assignments with it."""
        self.create()
        self.adapter.load_vrf_device_assignments(Device.objects.all())
        self.assertEqual(self.adapter.get_all("vrf_device_assignment"), [])

    def test_only_in_scope_devices_are_loaded(self):
        self.create()
        self.adapter.load_vrfs()
        self.adapter.load_vrf_device_assignments(Device.objects.none())
        self.assertEqual(self.adapter.get_all("vrf_device_assignment"), [])

    def test_both_adapters_describe_an_assignment_the_same_way(self):
        """An assignment carries no attributes, so identity is the whole of what has to agree."""
        self.create()
        self.adapter.load_vrfs()
        self.adapter.load_vrf_device_assignments(Device.objects.all())

        client = mock.MagicMock()
        client.technology.routing.vrf_detail.all.return_value = [
            {"sn": "a", "hostname": "rtr1", "vrf": "BLUE", "rd": "65000:1"}
        ]
        client.technology.mpls.l3vpn_vrf_targets.all.return_value = []
        source = IPFabricDiffSync(
            job=mock.MagicMock(),
            sync=None,
            client=client,
            location_filter=None,
            scope=full_scope(),
        )
        source.add(
            source.device(
                name="rtr1",
                location_name="site1",
                model="model",
                vendor="vendor",
                role="router",
                status="Active",
                serial_number="abc",
            )
        )
        source.load_vrfs()

        self.assertEqual(
            sorted(each.get_unique_id() for each in self.adapter.get_all("vrf_device_assignment")),
            sorted(each.get_unique_id() for each in source.get_all("vrf_device_assignment")),
        )

    def test_an_assignment_is_made_to_a_vrf_still_queued_in_bulk_mode(self):
        """In bulk mode the VRF this assignment needs has no row yet, only a place in the queue."""
        adapter = nautobot_adapter(bulk_write_mode=True)
        adapter.vrf.create(adapter, {"name": "GREEN"}, vrf_attrs(rd="65000:7"))
        adapter.vrf_device_assignment.create(adapter, {"vrf_name": "GREEN", "device_name": "rtr1"}, {})

        adapter.flush_pending_writes()

        green = VRF.objects.get(name="GREEN")
        self.assertEqual([vrf.name for vrf in self.device.vrfs.all()], ["GREEN"])
        self.assertEqual(VRFDeviceAssignment.objects.get(vrf=green, device=self.device).rd, "65000:7")

    def test_a_queued_assignment_is_written_in_bulk_mode(self):
        adapter = nautobot_adapter(bulk_write_mode=True)
        adapter.vrf_device_assignment.create(adapter, {"vrf_name": "BLUE", "device_name": "rtr1"}, {})
        self.assertEqual(VRFDeviceAssignment.objects.count(), 0)

        adapter.flush_pending_writes()

        assignment = VRFDeviceAssignment.objects.get(vrf=self.vrf, device=self.device)
        self.assertEqual(assignment.rd, "65000:1")
        self.assertEqual(assignment.name, "BLUE")


class IPFabricVrfDeviceAssignmentLoadTestCase(SimpleTestCase):
    """Reading which Devices carry each VRF from IP Fabric's VRF detail table."""

    def build_adapter(self, detail_rows, device_names, scope=None):
        """Return an IP Fabric adapter holding the named Devices and serving the given rows."""
        client = mock.MagicMock()
        client.technology.routing.vrf_detail.all.return_value = detail_rows
        client.technology.mpls.l3vpn_vrf_targets.all.return_value = []
        adapter = IPFabricDiffSync(
            job=mock.MagicMock(),
            sync=mock.MagicMock(),
            client=client,
            location_filter=None,
            scope=scope if scope is not None else full_scope(),
        )
        for name in device_names:
            adapter.add(
                adapter.device(
                    name=name,
                    location_name="site1",
                    model="model",
                    vendor="vendor",
                    role="router",
                    status="Active",
                    serial_number="abc",
                )
            )
        return adapter

    def test_each_device_the_table_names_is_assigned(self):
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1"), detail_row("BLUE", "b", "65000:1")],
            ["host-a", "host-b"],
        )
        adapter.load_vrfs()
        self.assertEqual(
            sorted(each.get_unique_id() for each in adapter.get_all("vrf_device_assignment")),
            ["BLUE__host-a", "BLUE__host-b"],
        )

    def test_a_device_the_run_did_not_load_is_skipped(self):
        """A Location filter can leave a hostname the VRF table names outside the run."""
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1"), detail_row("BLUE", "b", "65000:1")],
            ["host-a"],
        )
        adapter.load_vrfs()
        self.assertEqual(
            [each.get_unique_id() for each in adapter.get_all("vrf_device_assignment")],
            ["BLUE__host-a"],
        )

    def test_one_device_carrying_several_vrfs_gets_an_assignment_each(self):
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1"), detail_row("RED", "a", "65000:2")],
            ["host-a"],
        )
        adapter.load_vrfs()
        self.assertEqual(
            sorted(each.get_unique_id() for each in adapter.get_all("vrf_device_assignment")),
            ["BLUE__host-a", "RED__host-a"],
        )

    def test_a_device_reported_twice_for_one_vrf_is_assigned_once(self):
        """The detail table reports a row per address family, so a pair can repeat."""
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1"), detail_row("BLUE", "a", "65000:1")],
            ["host-a"],
        )
        adapter.load_vrfs()
        self.assertEqual(len(adapter.get_all("vrf_device_assignment")), 1)

    def test_no_device_matching_at_all_is_reported(self):
        """A narrowed run leaves some out; nothing matching means the two tables disagree on names."""
        adapter = self.build_adapter([detail_row("BLUE", "a", "65000:1")], ["somewhere-else"])
        adapter.load_vrfs()

        self.assertEqual(adapter.get_all("vrf_device_assignment"), [])
        warned = " ".join(str(call) for call in adapter.job.logger.warning.call_args_list)
        self.assertIn("none of which match a Device this run loaded", warned)

    def test_device_vrfs_out_of_scope_loads_none(self):
        adapter = self.build_adapter(
            [detail_row("BLUE", "a", "65000:1")],
            ["host-a"],
            scope=full_scope(device_vrfs=False),
        )
        adapter.load_vrfs()
        self.assertEqual(adapter.get_all("vrf_device_assignment"), [])


class InterfaceVrfTestCase(VrfTestCase):
    """Putting Interfaces in the VRF IP Fabric reports for them."""

    def setUp(self):
        super().setUp()
        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(ContentType.objects.get_for_model(Device))
        site = Location.objects.create(name="site1", location_type=site_type, status=self.active)
        role = Role.objects.create(name="router")
        role.content_types.add(ContentType.objects.get_for_model(Device))
        manufacturer = Manufacturer.objects.create(name="vendor")
        self.device = Device.objects.create(
            name="rtr1",
            status=self.active,
            role=role,
            location=site,
            device_type=DeviceType.objects.create(model="model", manufacturer=manufacturer),
        )
        self.interface = Interface.objects.create(
            device=self.device, name="Ethernet1", type="1000base-t", status=self.active
        )
        self.vrf = VRF.objects.create(name="BLUE", rd="65000:1", namespace=self.namespace, status=self.active)
        self.other_vrf = VRF.objects.create(name="RED", rd="65000:2", namespace=self.namespace, status=self.active)
        self.adapter = nautobot_adapter()

    def assign_vrf_to_device(self, vrf=None):
        """Carry out what Sync Device VRFs does, which Nautobot requires before an Interface may."""
        VRFDeviceAssignment.objects.create(vrf=vrf or self.vrf, device=self.device)

    def create(self, vrf_name="BLUE", interface_name="Ethernet1"):
        """Put an Interface in a VRF through the DiffSync model, as a sync would."""
        return self.adapter.interface_vrf.create(
            self.adapter,
            {"device_name": "rtr1", "interface_name": interface_name},
            {"vrf_name": vrf_name},
        )

    def loaded_model(self):
        """Return the DiffSync model for the Interface VRF Nautobot holds."""
        self.adapter.load_vrfs()
        self.adapter.load_interface_vrfs(Device.objects.all())
        return self.adapter.get("interface_vrf", "rtr1__Ethernet1")

    def test_interface_vrfs_are_written_after_the_device_assignments(self):
        """Nautobot refuses an Interface a VRF its Device does not carry."""
        top_level = DiffSyncModelAdapters.top_level
        self.assertLess(top_level.index("vrf_device_assignment"), top_level.index("interface_vrf"))

    def test_create_puts_the_interface_in_the_vrf(self):
        self.assign_vrf_to_device()
        self.create()
        self.interface.refresh_from_db()
        self.assertEqual(self.interface.vrf, self.vrf)

    def test_create_is_refused_when_the_device_does_not_carry_the_vrf(self):
        """Without the assignment Nautobot rejects it, which is reported rather than raised."""
        self.assertIsNone(self.create())
        self.interface.refresh_from_db()
        self.assertIsNone(self.interface.vrf)
        self.adapter.job.logger.error.assert_called()

    def test_create_reports_a_vrf_that_is_not_there(self):
        self.assertIsNone(self.create(vrf_name="ABSENT"))
        self.adapter.job.logger.error.assert_called()

    def test_create_reports_an_interface_that_is_not_there(self):
        self.assign_vrf_to_device()
        self.assertIsNone(self.create(interface_name="Ethernet99"))

    def test_update_moves_the_interface_to_another_vrf(self):
        self.assign_vrf_to_device()
        self.assign_vrf_to_device(self.other_vrf)
        self.create()

        self.loaded_model().update({"vrf_name": "RED"})

        self.interface.refresh_from_db()
        self.assertEqual(self.interface.vrf, self.other_vrf)

    def test_delete_takes_the_interface_out_of_its_vrf(self):
        self.assign_vrf_to_device()
        self.create()

        self.loaded_model().delete()

        self.interface.refresh_from_db()
        self.assertIsNone(self.interface.vrf)
        self.assertTrue(VRF.objects.filter(name="BLUE").exists())
        self.assertTrue(Interface.objects.filter(pk=self.interface.pk).exists())

    def test_only_interfaces_in_a_vrf_are_loaded(self):
        self.assign_vrf_to_device()
        self.create()
        Interface.objects.create(device=self.device, name="Ethernet2", type="1000base-t", status=self.active)

        self.adapter.load_vrfs()
        self.adapter.load_interface_vrfs(Device.objects.all())

        self.assertEqual(
            [each.get_unique_id() for each in self.adapter.get_all("interface_vrf")],
            ["rtr1__Ethernet1"],
        )

    def test_an_interface_whose_vrf_was_not_loaded_is_not_loaded(self):
        self.assign_vrf_to_device()
        self.create()
        self.adapter.load_interface_vrfs(Device.objects.all())
        self.assertEqual(self.adapter.get_all("interface_vrf"), [])

    def test_only_in_scope_devices_are_loaded(self):
        self.assign_vrf_to_device()
        self.create()
        self.adapter.load_vrfs()
        self.adapter.load_interface_vrfs(Device.objects.none())
        self.assertEqual(self.adapter.get_all("interface_vrf"), [])

    def test_both_adapters_describe_an_interface_vrf_the_same_way(self):
        """A run that reported it differently on each side would rewrite it forever."""
        self.assign_vrf_to_device()
        self.create()
        self.adapter.load_vrfs()
        self.adapter.load_interface_vrfs(Device.objects.all())

        client = mock.MagicMock()
        client.technology.routing.vrf_detail.all.return_value = []
        client.technology.mpls.l3vpn_vrf_targets.all.return_value = []
        client.technology.routing.vrf_interfaces.all.return_value = [
            {"sn": "a", "hostname": "rtr1", "intName": "Ethernet1", "vrf": "BLUE"}
        ]
        source = ipfabric_adapter(client=client)
        source.add(
            source.interface(
                name="Ethernet1",
                device_name="rtr1",
                description="",
                enabled=True,
                mac_address="00:00:00:00:00:01",
                mtu=1500,
                type="1000base-t",
                mgmt_only=False,
                ip_address=None,
                subnet_mask=None,
                ip_is_primary=False,
                status="Active",
            )
        )
        source.load_interface_vrfs()

        self.assertEqual(
            {each.get_unique_id(): each.vrf_name for each in self.adapter.get_all("interface_vrf")},
            {each.get_unique_id(): each.vrf_name for each in source.get_all("interface_vrf")},
        )

    def test_a_queued_vrf_is_found_in_bulk_mode(self):
        """In bulk mode the VRF and its Device assignment may both be queued rather than written."""
        adapter = nautobot_adapter(bulk_write_mode=True)
        adapter.vrf.create(adapter, {"name": "GREEN"}, vrf_attrs(rd="65000:7"))
        adapter.vrf_device_assignment.create(adapter, {"vrf_name": "GREEN", "device_name": "rtr1"}, {})
        adapter.interface_vrf.create(
            adapter, {"device_name": "rtr1", "interface_name": "Ethernet1"}, {"vrf_name": "GREEN"}
        )

        adapter.flush_pending_writes()

        self.interface.refresh_from_db()
        self.assertEqual(self.interface.vrf, VRF.objects.get(name="GREEN"))


class IPFabricInterfaceVrfLoadTestCase(SimpleTestCase):
    """Reading the VRF each Interface is in from IP Fabric's VRF interfaces table."""

    def build_adapter(self, rows, interfaces, scope=None):
        """Return an IP Fabric adapter holding the named Interfaces and serving the given rows."""
        client = mock.MagicMock()
        client.technology.routing.vrf_detail.all.return_value = []
        client.technology.mpls.l3vpn_vrf_targets.all.return_value = []
        client.technology.routing.vrf_interfaces.all.return_value = rows
        adapter = ipfabric_adapter(client=client, scope=scope if scope is not None else full_scope())
        for device_name, interface_name in interfaces:
            adapter.add(
                adapter.interface(
                    name=interface_name,
                    device_name=device_name,
                    description="",
                    enabled=True,
                    mac_address="00:00:00:00:00:01",
                    mtu=1500,
                    type="1000base-t",
                    mgmt_only=False,
                    ip_address=None,
                    subnet_mask=None,
                    ip_is_primary=False,
                    status="Active",
                )
            )
        return adapter

    @staticmethod
    def row(vrf="BLUE", hostname="rtr1", int_name="Ethernet1"):
        """Return a row of IP Fabric's VRF interfaces table."""
        return {"sn": "a", "hostname": hostname, "intName": int_name, "vrf": vrf}

    def test_each_interface_the_table_names_is_loaded(self):
        adapter = self.build_adapter(
            [self.row(), self.row(vrf="RED", int_name="Ethernet2")],
            [("rtr1", "Ethernet1"), ("rtr1", "Ethernet2")],
        )
        adapter.load_interface_vrfs()
        self.assertEqual(
            {each.get_unique_id(): each.vrf_name for each in adapter.get_all("interface_vrf")},
            {"rtr1__Ethernet1": "BLUE", "rtr1__Ethernet2": "RED"},
        )

    def test_an_interface_the_run_did_not_load_is_skipped(self):
        """An Interface in a VRF that this run never saw would be reported absent on every run."""
        adapter = self.build_adapter([self.row(int_name="Ethernet9")], [("rtr1", "Ethernet1")])
        adapter.load_interface_vrfs()
        self.assertEqual(adapter.get_all("interface_vrf"), [])

    def test_a_row_naming_no_vrf_is_skipped(self):
        adapter = self.build_adapter([self.row(vrf=None)], [("rtr1", "Ethernet1")])
        adapter.load_interface_vrfs()
        self.assertEqual(adapter.get_all("interface_vrf"), [])

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME", True
    )
    def test_the_interface_name_is_canonicalised_to_match_the_loaded_interface(self):
        """The Interfaces were loaded under canonical names, so these have to be matched the same way."""
        adapter = self.build_adapter([self.row(int_name="Eth1")], [("rtr1", "Ethernet1")])
        adapter.load_interface_vrfs()
        self.assertEqual(
            [each.get_unique_id() for each in adapter.get_all("interface_vrf")],
            ["rtr1__Ethernet1"],
        )

    def test_interface_vrfs_out_of_scope_are_not_read(self):
        adapter = self.build_adapter([self.row()], [("rtr1", "Ethernet1")], scope=full_scope(interface_vrfs=False))
        adapter.client.inventory.sites.all.return_value = []
        adapter.client.devices.by_site = {}
        with mock.patch.object(IPFabricDiffSync, "load_data", return_value=({}, {}, {})):
            adapter.load()
        self.assertEqual(adapter.get_all("interface_vrf"), [])
        adapter.client.technology.routing.vrf_interfaces.all.assert_not_called()
