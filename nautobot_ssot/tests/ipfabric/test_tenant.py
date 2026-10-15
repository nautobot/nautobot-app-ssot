"""Tests for running the IP Fabric sync on behalf of one Tenant."""

from types import SimpleNamespace
from unittest import mock

from django.apps import apps as global_apps
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from nautobot.dcim.models import Device, Interface, Location
from nautobot.ipam.models import VLAN, VRF, IPAddress, Prefix, RouteTarget, get_default_namespace
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.diffsync import diffsync_models
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.signals import nautobot_database_ready_callback
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.tests.ipfabric.job_log import job_log_text
from nautobot_ssot.tests.ipfabric.supporting_objects import SupportingObjectTestCase


def prepare(adapter):
    """Make the custom fields the sync stamps and two Tenants, and run the adapter for the first."""
    nautobot_database_ready_callback(sender=None, apps=global_apps)
    tenant = Tenant.objects.create(name="customer-a")
    adapter.tenant = tenant
    adapter.sync_ipfabric_tagged_only = False
    return tenant, Tenant.objects.create(name="customer-b")


class TestClaimingAnObjectForTheTenant(SimpleTestCase):
    """The one rule every adoption follows."""

    TENANT = SimpleNamespace(pk=1)

    def test_an_object_with_no_tenant_is_given_the_runs(self):
        obj = SimpleNamespace(tenant_id=None, tenant=None)
        self.assertTrue(nbutils.claim_for_tenant(obj, self.TENANT))
        self.assertIs(obj.tenant, self.TENANT)

    def test_an_object_already_the_tenants_is_unchanged(self):
        obj = SimpleNamespace(tenant_id=1, tenant=self.TENANT)
        self.assertFalse(nbutils.claim_for_tenant(obj, self.TENANT))

    def test_an_object_of_another_tenant_is_refused(self):
        obj = SimpleNamespace(tenant_id=2, tenant="other")
        with self.assertRaises(nbutils.BelongsToAnotherTenant) as raised:
            nbutils.claim_for_tenant(obj, self.TENANT)
        self.assertIs(raised.exception.nautobot_object, obj)

    def test_a_run_with_no_tenant_changes_nothing(self):
        obj = SimpleNamespace(tenant_id=2, tenant="other")
        self.assertFalse(nbutils.claim_for_tenant(obj, None))
        self.assertEqual(obj.tenant_id, 2)

    def test_the_location_lookup_stays_cached_for_the_run(self):
        """Every Device at a site asks for its Location, so the lookup must not lose its cache."""
        self.assertTrue(hasattr(nbutils.get_or_create_location_object, "cache_info"))


class TestWritingDevices(SupportingObjectTestCase):
    """A Device the sync creates or adopts is the Tenant's, and another Tenant's is left alone."""

    def setUp(self):
        super().setUp()
        self.tenant, self.other_tenant = prepare(self.adapter)

    def test_a_new_device_is_given_the_tenant(self):
        self.create_device(name="new")
        self.assertEqual(Device.objects.get(name="new").tenant, self.tenant)

    def test_an_existing_device_with_no_tenant_is_adopted(self):
        self.adapter.tenant = None
        self.create_device(name="existing")
        self.adapter.tenant = self.tenant
        self.create_device(name="existing")
        self.assertEqual(Device.objects.get(name="existing").tenant, self.tenant)

    def test_an_existing_device_of_another_tenant_is_skipped_and_recorded(self):
        self.adapter.tenant = self.other_tenant
        self.create_device(name="theirs")
        self.adapter.tenant = self.tenant
        self.assertIsNone(self.create_device(name="theirs"))
        self.assertEqual(Device.objects.get(name="theirs").tenant, self.other_tenant)
        self.assertEqual(dict(self.adapter.objects_of_another_tenant), {"devices": ["theirs"]})

    def test_a_location_the_sync_creates_is_given_the_tenant(self):
        self.create_device(name="new", location_name="new-site")
        self.assertEqual(Location.objects.get(name="new-site").tenant, self.tenant)

    def test_an_existing_location_keeps_its_tenant(self):
        """A site may be shared, so Locations are neither narrowed nor claimed."""
        self.create_device(name="new")
        self.location.refresh_from_db()
        self.assertIsNone(self.location.tenant)

    def test_the_device_gate_matches_only_the_tenants_devices(self):
        self.create_device(name="ours")
        self.adapter.tenant = self.other_tenant
        self.create_device(name="theirs")
        self.assertIsNotNone(nbutils.get_syncable_device("ours", tagged_only=False, tenant=self.tenant))
        self.assertIsNone(nbutils.get_syncable_device("theirs", tagged_only=False, tenant=self.tenant))
        self.assertIsNotNone(nbutils.get_syncable_device("theirs", tagged_only=False, tenant=None))


class TestTheOtherObjectsTheSyncCreates(SupportingObjectTestCase):
    """VLANs, Route Targets, VRFs and addresses follow the same rule as Devices."""

    def setUp(self):
        super().setUp()
        self.tenant, self.other_tenant = prepare(self.adapter)

    def vlan(self, vid=10):
        """Create a VLAN through the helper the sync uses."""
        return nbutils.create_vlan(f"vlan{vid}", vid, "Active", self.location, "", tenant=self.tenant)

    def test_a_new_vlan_is_given_the_tenant(self):
        self.assertEqual(self.vlan().tenant, self.tenant)

    def test_an_existing_vlan_with_no_tenant_is_adopted(self):
        nbutils.create_vlan("vlan10", 10, "Active", self.location, "")
        self.vlan()
        self.assertEqual(VLAN.objects.get(vid=10).tenant, self.tenant)

    def test_an_existing_vlan_of_another_tenant_is_refused(self):
        nbutils.create_vlan("vlan10", 10, "Active", self.location, "", tenant=self.other_tenant)
        with self.assertRaises(nbutils.BelongsToAnotherTenant):
            self.vlan()

    def test_a_route_target_is_given_or_adopted_for_the_tenant(self):
        self.assertEqual(nbutils.create_route_target("65000:1", tenant=self.tenant).tenant, self.tenant)
        RouteTarget.objects.create(name="65000:2")
        nbutils.create_route_target("65000:2", tenant=self.tenant)
        self.assertEqual(RouteTarget.objects.get(name="65000:2").tenant, self.tenant)
        RouteTarget.objects.create(name="65000:3", tenant=self.other_tenant)
        with self.assertRaises(nbutils.BelongsToAnotherTenant):
            nbutils.create_route_target("65000:3", tenant=self.tenant)

    def test_a_new_vrf_is_given_the_tenant(self):
        vrf = nbutils.create_vrf("BLUE", "65000:1", "Active", "", tenant=self.tenant)
        self.assertEqual(vrf.tenant, self.tenant)

    def test_an_existing_vrf_with_no_tenant_is_adopted_rather_than_duplicated(self):
        """The run reads only its Tenant's VRFs, so it never loaded this one to match it by name."""
        VRF.objects.create(name="BLUE", namespace=get_default_namespace(), status=self.active_status)
        vrf = nbutils.create_vrf("BLUE", "65000:1", "Active", "", tenant=self.tenant)
        self.assertEqual(VRF.objects.filter(name="BLUE").count(), 1)
        vrf.refresh_from_db()
        self.assertEqual((vrf.tenant, vrf.rd), (self.tenant, "65000:1"))

    def test_an_adoption_nautobot_refuses_is_reported(self):
        VRF.objects.create(name="BLUE", namespace=get_default_namespace(), status=self.active_status)
        logger = mock.MagicMock()
        with mock.patch.object(nbutils, "tag_object", side_effect=ValidationError("refused")):
            self.assertIsNone(nbutils.create_vrf("BLUE", None, "Active", "", logger=logger, tenant=self.tenant))
        self.assertIn("Unable to adopt the VRF named BLUE", job_log_text(logger, "error"))

    def test_an_existing_vrf_of_another_tenant_is_refused(self):
        VRF.objects.create(
            name="BLUE", namespace=get_default_namespace(), status=self.active_status, tenant=self.other_tenant
        )
        with self.assertRaises(nbutils.BelongsToAnotherTenant):
            nbutils.create_vrf("BLUE", None, "Active", "", tenant=self.tenant)

    def test_a_vrf_name_held_twice_is_refused(self):
        for rd in ("65000:1", "65000:2"):
            VRF.objects.create(name="BLUE", rd=rd, namespace=get_default_namespace(), status=self.active_status)
        logger = mock.MagicMock()
        self.assertIsNone(nbutils.create_vrf("BLUE", None, "Active", "", logger=logger, tenant=self.tenant))
        self.assertIn("more than one", job_log_text(logger, "error"))

    def test_without_a_tenant_a_vrf_is_created_as_before(self):
        VRF.objects.create(name="BLUE", namespace=get_default_namespace(), status=self.active_status)
        nbutils.create_vrf("BLUE", "65000:9", "Active", "")
        self.assertEqual(VRF.objects.filter(name="BLUE").count(), 2)

    def address_setup(self):
        """Create the Prefix an address needs."""
        Prefix.objects.create(prefix="10.0.0.0/24", namespace=get_default_namespace(), status=self.active_status)

    def test_a_new_address_is_given_the_tenant(self):
        self.address_setup()
        self.assertEqual(nbutils.create_ip("10.0.0.1", 24, tenant=self.tenant).tenant, self.tenant)

    def test_an_existing_address_with_no_tenant_is_adopted(self):
        self.address_setup()
        nbutils.create_ip("10.0.0.1", 24)
        nbutils.create_ip("10.0.0.1", 24, tenant=self.tenant)
        self.assertEqual(IPAddress.objects.get(host="10.0.0.1").tenant, self.tenant)

    def test_an_existing_address_of_another_tenant_is_refused(self):
        self.address_setup()
        nbutils.create_ip("10.0.0.1", 24, tenant=self.other_tenant)
        with self.assertRaises(nbutils.BelongsToAnotherTenant):
            nbutils.create_ip("10.0.0.1", 24, tenant=self.tenant)

    def test_a_queued_address_is_given_the_tenant_and_an_existing_one_adopted(self):
        self.address_setup()
        nbutils.create_ip("10.0.0.2", 24)
        pending = PendingWrites(mock.MagicMock())
        nbutils.create_ip("10.0.0.1", 24, pending=pending, tenant=self.tenant)
        nbutils.create_ip("10.0.0.2", 24, pending=pending, tenant=self.tenant)
        pending.flush()
        self.assertEqual(
            {str(host): tenant for host, tenant in IPAddress.objects.values_list("host", "tenant")},
            {"10.0.0.1": self.tenant.pk, "10.0.0.2": self.tenant.pk},
        )


class TestPrefixes(SupportingObjectTestCase):
    """Prefixes follow the same rule, whether synced as networks or created as an address's parent."""

    def setUp(self):
        super().setUp()
        self.tenant, self.other_tenant = prepare(self.adapter)

    def existing(self, tenant=None):
        """Create the Prefix 10.0.0.0/24 as Nautobot might already hold it."""
        return Prefix.objects.create(
            prefix="10.0.0.0/24", namespace=get_default_namespace(), status=self.active_status, tenant=tenant
        )

    def sync_prefix(self):
        """Create the Prefix 10.0.0.0/24 through the DiffSync model, as a sync would."""
        return diffsync_models.Prefix.create(self.adapter, {"prefix": "10.0.0.0/24"}, {"status": "Active"})

    def test_a_new_prefix_is_given_the_tenant(self):
        self.assertIsNotNone(self.sync_prefix())
        self.assertEqual(Prefix.objects.get(prefix="10.0.0.0/24").tenant, self.tenant)

    def test_an_existing_prefix_with_no_tenant_is_adopted(self):
        existing = self.existing()
        self.assertIsNotNone(self.sync_prefix())
        existing.refresh_from_db()
        self.assertEqual(existing.tenant, self.tenant)

    def test_an_existing_prefix_of_another_tenant_is_skipped_with_its_locations(self):
        existing = self.existing(tenant=self.other_tenant)
        self.assertIsNone(self.sync_prefix())
        self.assertEqual(dict(self.adapter.objects_of_another_tenant), {"prefixes": ["10.0.0.0/24"]})
        self.assertIsNone(
            diffsync_models.PrefixLocation.create(
                self.adapter, {"prefix": "10.0.0.0/24", "location_name": self.location.name}, {}
            )
        )
        self.assertFalse(existing.locations.exists())
        self.assertFalse(existing.tags.exists())

    def test_the_parent_prefix_made_for_an_address_is_given_the_tenant(self):
        nbutils.create_ip("10.0.0.1", 24, tenant=self.tenant)
        self.assertEqual(Prefix.objects.get(prefix="10.0.0.0/24").tenant, self.tenant)

    def test_a_queued_addresss_parent_prefix_is_given_the_tenant(self):
        pending = PendingWrites(mock.MagicMock())
        nbutils.create_ip("10.0.0.1", 24, pending=pending, tenant=self.tenant)
        pending.flush()
        self.assertEqual(Prefix.objects.get(prefix="10.0.0.0/24").tenant, self.tenant)

    def test_an_existing_parent_prefix_keeps_its_tenant(self):
        """An address only needs its parent to exist; it does not claim the network for the Tenant."""
        self.existing(tenant=self.other_tenant)
        nbutils.create_ip("10.0.0.1", 24, tenant=self.tenant)
        self.assertEqual(Prefix.objects.get(prefix="10.0.0.0/24").tenant, self.other_tenant)


class TestEachModelReportsAnotherTenantsObject(SupportingObjectTestCase):
    """Each model skips an object of another Tenant and records it, rather than failing the sync."""

    def setUp(self):
        super().setUp()
        self.tenant, self.other_tenant = prepare(self.adapter)

    def assert_recorded(self, model_name, name):
        """Assert the object was recorded for the end of run report."""
        self.assertEqual(dict(self.adapter.objects_of_another_tenant), {model_name: [name]})

    def test_a_vlan(self):
        nbutils.create_vlan("vlan10", 10, "Active", self.location, "", tenant=self.other_tenant)
        created = diffsync_models.Vlan.create(
            self.adapter,
            {"vid": 10, "location": self.location.name},
            {"name": "vlan10", "status": "Active", "description": "", "in_vlan_group": False},
        )
        self.assertIsNone(created)
        self.assert_recorded("VLANs", "vlan10 (10)")

    def test_a_route_target(self):
        RouteTarget.objects.create(name="65000:3", tenant=self.other_tenant)
        self.assertIsNone(diffsync_models.RouteTarget.create(self.adapter, {"name": "65000:3"}, {}))
        self.assert_recorded("route targets", "65000:3")

    def test_a_vrf(self):
        VRF.objects.create(
            name="BLUE", namespace=get_default_namespace(), status=self.active_status, tenant=self.other_tenant
        )
        attrs = {"rd": None, "status": "Active", "import_targets": [], "export_targets": [], "conflict": ""}
        self.assertIsNone(diffsync_models.Vrf.create(self.adapter, {"name": "BLUE"}, attrs))
        self.assertEqual(list(self.adapter.objects_of_another_tenant), ["VRFs"])

    def test_an_address(self):
        Prefix.objects.create(prefix="10.0.0.0/24", namespace=get_default_namespace(), status=self.active_status)
        nbutils.create_ip("10.0.0.1", 24, tenant=self.other_tenant)
        self.create_device(name="ours")
        Interface.objects.create(
            device=Device.objects.get(name="ours"), name="eth0", type="1000base-t", status=self.active_status
        )
        created = diffsync_models.InterfaceAddress.create(
            self.adapter,
            {"device_name": "ours", "interface_name": "eth0", "host": "10.0.0.1"},
            {"mask_length": 24, "is_primary": False, "status": "Active"},
        )
        self.assertIsNone(created)
        self.assertEqual(list(self.adapter.objects_of_another_tenant), ["IP addresses"])


class TestReadingOnlyTheTenantsObjects(SupportingObjectTestCase):
    """The Nautobot adapter reads the Tenant's Devices, VLANs, VRFs, Route Targets and Prefixes, and no others."""

    def setUp(self):
        super().setUp()
        self.tenant, self.other_tenant = prepare(self.adapter)

    def nautobot_adapter(self):
        """Return a Nautobot adapter for this test's Tenant, with VRFs and Route Targets in scope."""
        return NautobotDiffSync(
            job=mock.MagicMock(),
            sync=None,
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=SyncScope(["locations", "vlans", "vrfs", "route_targets", "prefixes"]),
            tenant=self.tenant,
        )

    def test_only_the_tenants_devices_are_in_scope(self):
        self.create_device(name="ours")
        self.adapter.tenant = self.other_tenant
        self.create_device(name="theirs")
        adapter = self.nautobot_adapter()
        names = set(adapter.get_in_scope_devices(Location.objects.all()).values_list("name", flat=True))
        self.assertEqual(names, {"ours"})

    def test_only_the_tenants_vlans_vrfs_and_route_targets_are_loaded(self):
        nbutils.create_vlan("ours", 10, "Active", self.location, "", tenant=self.tenant)
        nbutils.create_vlan("theirs", 20, "Active", self.location, "", tenant=self.other_tenant)
        for name, tenant in (("OURS", self.tenant), ("THEIRS", self.other_tenant)):
            VRF.objects.create(name=name, namespace=get_default_namespace(), status=self.active_status, tenant=tenant)
        nbutils.create_route_target("65000:1", tenant=self.tenant)
        nbutils.create_route_target("65000:2", tenant=self.other_tenant)

        adapter = self.nautobot_adapter()
        adapter.load()

        self.assertEqual([vlan.vid for vlan in adapter.get_all("vlan")], [10])
        self.assertEqual([vrf.name for vrf in adapter.get_all("vrf")], ["OURS"])
        self.assertEqual([target.name for target in adapter.get_all("route_target")], ["65000:1"])

    def test_only_the_tenants_prefixes_are_loaded(self):
        adapter = self.nautobot_adapter()
        for prefix, tenant in (("10.0.0.0/24", self.tenant), ("10.0.1.0/24", self.other_tenant)):
            Prefix.objects.create(
                prefix=prefix, namespace=get_default_namespace(), status=self.active_status, tenant=tenant
            ).tags.add(adapter.ssot_tag)
        adapter.load_prefixes()
        self.assertEqual([prefix.prefix for prefix in adapter.get_all("prefix")], ["10.0.0.0/24"])

    def test_objects_of_another_tenant_are_reported_once_per_model(self):
        adapter = self.nautobot_adapter()
        adapter.objects_of_another_tenant["devices"].extend(["b", "a"])
        adapter.sync_complete(mock.MagicMock(), mock.MagicMock())
        self.assertEqual(
            job_log_text(adapter.job.logger, "warning"),
            "Not syncing 2 devices IP Fabric reports, as they belong to a Tenant other than customer-a: a, b",
        )
        self.assertEqual(dict(adapter.objects_of_another_tenant), {})
