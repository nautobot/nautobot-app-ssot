"""Tests for taking Locations out of an IP Fabric sync's scope.

Locations are the root of the object tree, so they cannot simply be left unloaded: every Device and
VLAN is a child of one. Deselecting them withholds *writing* Locations while still using them to
reach their children, and these tests pin that distinction where it is decided: in the diff for what
gets considered, and in a real sync for what gets written.
"""

import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import CustomField, Role, Status, Tag
from nautobot.ipam.models import VLAN
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache
from nautobot_ssot.tests.ipfabric.job_log import job_log_text

# A site IP Fabric reports that this sync did not load from Nautobot.
UNLOADED_FROM_NAUTOBOT = "site-discovered"
# A site Nautobot holds that IP Fabric does not report.
UNKNOWN_TO_IPFABRIC = "site-unreported"
# A site both sides know, whose IP Fabric site ID differs from the one Nautobot has recorded.
KNOWN_TO_BOTH = "site-shared"


class LocationScopeTestCase(TestCase):
    """Diff and sync a Nautobot estate against a source that disagrees about Locations three ways."""

    def setUp(self):
        # Helpers memoize real ORM objects, which would outlive this test's transaction.
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)

        populate_status_choices()
        self.active_status = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        self.role = Role.objects.create(name="test")
        self.role.content_types.add(device_ct)
        # `get_or_create_device_role_object` matches on this custom field rather than the name, so
        # without it a sync would try to create a second Role called "test".
        role_cf, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="ipfabric_type",
            defaults={"label": "IPFabric Type"},
        )
        role_cf.content_types.add(ContentType.objects.get_for_model(Role))
        self.role.cf["ipfabric_type"] = "test"
        self.role.validated_save()
        # Named "Site" so `get_or_create_location_object` would reuse it if it were ever reached.
        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        vlan_ct = ContentType.objects.get_for_model(VLAN)
        self.site_type.content_types.add(device_ct, vlan_ct)
        manufacturer = Manufacturer.objects.create(name="man1")
        self.device_type = DeviceType.objects.create(model="dev_type1", manufacturer=manufacturer)
        self.ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN},
        )
        self.ssot_tag.content_types.add(device_ct)
        self.ssot_tag.content_types.add(ContentType.objects.get_for_model(Location))
        self.ssot_tag.content_types.add(vlan_ct)

        for site_name in (KNOWN_TO_BOTH, UNKNOWN_TO_IPFABRIC):
            self._location(site_name, tagged=True)
            self._device(f"{site_name}-dev", site_name)

        self.nb_adapter = self._adapter()

    def _adapter(self, tagged_only=True):
        """Return a Nautobot adapter, tagged-only by default as the job form defaults to."""
        return NautobotDiffSync(
            job=unittest.mock.Mock(),
            sync=unittest.mock.Mock(),
            sync_ipfabric_tagged_only=tagged_only,
            location_filter=None,
        )

    def _location(self, name, tagged):
        """Create a Nautobot Location, tagged only if this sync is meant to load it."""
        location = Location.objects.create(name=name, location_type=self.site_type, status=self.active_status)
        if tagged:
            location.tags.add(self.ssot_tag)
        return location

    def _device(self, name, location_name):
        """Create a Nautobot Device, tagged so a tagged-only run loads it."""
        device = Device.objects.create(
            name=name,
            serial=name,
            status=self.active_status,
            role=self.role,
            location=Location.objects.get(name=location_name),
            device_type=self.device_type,
        )
        device.tags.add(self.ssot_tag)
        return device

    def _source(self, locations_in_scope, with_device_at=()):
        """Return a source adapter reporting the shared site and one this sync did not load.

        Built through `location_model` rather than by hand, so the placeholders the test relies on are
        the ones the real adapters use.
        """
        source = DiffSyncModelAdapters(scope=SyncScope.from_job_kwargs({"sync_locations": locations_in_scope}))
        for site_name in (KNOWN_TO_BOTH, UNLOADED_FROM_NAUTOBOT):
            location = source.location_model(site_name, site_id="ipf-id", status="Active")
            source.add(location)
            if site_name in with_device_at:
                device = source.device(
                    name=f"{site_name}-newdev",
                    location_name=site_name,
                    model="dev_type1",
                    vendor="man1",
                    serial_number=f"{site_name}-newdev",
                    role="test",
                    status="Active",
                )
                source.add(device)
                location.add_child(device)
        return source

    def _load(self, locations_in_scope):
        """Load Nautobot with the given Location scope."""
        self.nb_adapter.scope = SyncScope.from_job_kwargs(
            {"sync_locations": locations_in_scope, "sync_interfaces": False, "sync_vlans": False}
        )
        self.nb_adapter.load_data()

    def _diff(self, locations_in_scope, **source_kwargs):
        self._load(locations_in_scope)
        return self.nb_adapter.diff_from(self._source(locations_in_scope, **source_kwargs))

    @staticmethod
    def _location_attr_changes(diff):
        """Return the Locations whose own attributes the diff would write."""
        return {
            name: {side: change[side] for side in ("+", "-") if change.get(side)}
            for name, change in diff.dict().get("location", {}).items()
            if change.get("+") or change.get("-")
        }


class LocationDiffTestCase(LocationScopeTestCase):
    """What the diff considers, which decides whether children are reached at all."""

    def test_a_location_filtered_run_writes_only_to_the_devices_it_reads(self):
        adapter = NautobotDiffSync(
            job=unittest.mock.Mock(),
            sync=unittest.mock.Mock(),
            sync_ipfabric_tagged_only=False,
            location_filter=Location.objects.get(name=KNOWN_TO_BOTH),
        )
        adapter.load()
        self.assertEqual(set(adapter.get_in_scope_devices().values_list("name", flat=True)), {f"{KNOWN_TO_BOTH}-dev"})
        self.assertIsNotNone(nbutils.get_syncable_device(f"{KNOWN_TO_BOTH}-dev", scope=adapter.device_scope))
        self.assertIsNone(nbutils.get_syncable_device(f"{UNKNOWN_TO_IPFABRIC}-dev", scope=adapter.device_scope))

    def test_a_tagged_only_run_covers_only_the_devices_at_tagged_locations(self):
        self._location("untagged", tagged=False)
        self._device("untagged-dev", "untagged")
        self.nb_adapter.load()
        self.assertIsNone(nbutils.get_syncable_device("untagged-dev", scope=self.nb_adapter.device_scope))
        self.assertIsNotNone(nbutils.get_syncable_device(f"{KNOWN_TO_BOTH}-dev", scope=self.nb_adapter.device_scope))

    def test_a_run_over_every_location_names_none(self):
        adapter = self._adapter(tagged_only=False)
        adapter.load()
        self.assertIsNone(adapter.device_scope.location_name)

    def test_locations_in_scope_are_created_updated_and_deleted(self):
        """The default behaviour, recorded here so the out of scope case is a visible contrast."""
        changes = self._location_attr_changes(self._diff(locations_in_scope=True))

        self.assertEqual(set(changes), {KNOWN_TO_BOTH, UNLOADED_FROM_NAUTOBOT, UNKNOWN_TO_IPFABRIC})
        # The shared site is updated, since IP Fabric's site ID is not the one Nautobot recorded.
        self.assertEqual(changes[KNOWN_TO_BOTH]["+"], {"site_id": "ipf-id"})
        self.assertIn("+", changes[UNLOADED_FROM_NAUTOBOT])
        self.assertIn("-", changes[UNKNOWN_TO_IPFABRIC])

    def test_a_shared_location_has_no_attributes_to_write(self):
        """Matching placeholders on both sides are what stop the Location itself being updated."""
        changes = self._location_attr_changes(self._diff(locations_in_scope=False))

        self.assertNotIn(KNOWN_TO_BOTH, changes)

    def test_a_shared_location_still_carries_its_children(self):
        """The point of loading an out of scope Location at all: its Devices still diff."""
        diff = self._diff(locations_in_scope=False)

        devices = diff.dict()["location"][KNOWN_TO_BOTH]["device"]
        self.assertEqual(set(devices), {f"{KNOWN_TO_BOTH}-dev"})

    def test_an_unreported_location_shields_its_children(self):
        """A Location IP Fabric never reported is skipped whole, so its Devices are left alone.

        With Locations out of scope the sync has no opinion on which sites exist, so it cannot read
        a missing site as evidence that the Devices at it are gone.
        """
        diff = self._diff(locations_in_scope=False)

        self.assertNotIn(UNKNOWN_TO_IPFABRIC, diff.dict().get("location", {}))

    def test_an_unloaded_location_still_reaches_its_children(self):
        """A site this sync did not load is not skipped, so the Devices at it are still considered."""
        diff = self._diff(locations_in_scope=False, with_device_at=(UNLOADED_FROM_NAUTOBOT,))

        element = diff.dict()["location"][UNLOADED_FROM_NAUTOBOT]
        self.assertEqual(set(element["device"]), {f"{UNLOADED_FROM_NAUTOBOT}-newdev"})


class LocationSyncTestCase(LocationScopeTestCase):
    """What a real sync writes, which is where declining to create a Location is enforced."""

    def _sync(self, locations_in_scope, **source_kwargs):
        self._load(locations_in_scope)
        source = self._source(locations_in_scope, **source_kwargs)
        self.nb_adapter.sync_from(source)

    def test_an_unloaded_location_is_not_created(self):
        """Out of scope, the Location is another system's to create, so this sync leaves it absent."""
        self._sync(locations_in_scope=False, with_device_at=(UNLOADED_FROM_NAUTOBOT,))

        self.assertFalse(Location.objects.filter(name=UNLOADED_FROM_NAUTOBOT).exists())

    def test_a_device_at_a_missing_location_is_attempted_and_reported(self):
        """The Device cannot be placed, but the failure is logged rather than passed over silently."""
        self._sync(locations_in_scope=False, with_device_at=(UNLOADED_FROM_NAUTOBOT,))

        self.assertFalse(Device.objects.filter(name=f"{UNLOADED_FROM_NAUTOBOT}-newdev").exists())
        warnings = " ".join(str(call) for call in self.nb_adapter.job.logger.warning.call_args_list)
        self.assertIn(UNLOADED_FROM_NAUTOBOT, warnings)

    def test_a_device_lands_at_a_location_another_sync_already_created(self):
        """The case this is for: the Location exists but was not loaded, and the Device still lands.

        Another SSoT App owns Locations, so the Location it created carries no IP Fabric tag. It holds
        nothing this sync tagged yet, so the sync does not read it. The sync finds it by name instead,
        and places the Device there.
        """
        self._location(UNLOADED_FROM_NAUTOBOT, tagged=False)

        self._sync(locations_in_scope=False, with_device_at=(UNLOADED_FROM_NAUTOBOT,))

        device = Device.objects.get(name=f"{UNLOADED_FROM_NAUTOBOT}-newdev")
        self.assertEqual(device.location.name, UNLOADED_FROM_NAUTOBOT)

    def test_an_unreported_location_and_its_devices_survive(self):
        """Nothing about a site IP Fabric does not report is touched, Devices included."""
        self._sync(locations_in_scope=False, with_device_at=(UNLOADED_FROM_NAUTOBOT,))

        location = Location.objects.get(name=UNKNOWN_TO_IPFABRIC)
        self.assertEqual(location.status, self.active_status)
        device = Device.objects.get(name=f"{UNKNOWN_TO_IPFABRIC}-dev")
        self.assertEqual(device.status, self.active_status)

    def test_a_shared_locations_site_id_is_left_alone(self):
        """The custom field belongs to whoever owns Locations, so an out of scope run must not set it."""
        self._sync(locations_in_scope=False)

        location = Location.objects.get(name=KNOWN_TO_BOTH)
        self.assertIsNone(location.custom_field_data.get("ipfabric_site_id"))


class SiteWrittenInFullTestCase(LocationScopeTestCase):
    """A tagged-only run writes in full to the Devices it places at a site it did not load.

    Either a site it creates, or, with Locations out of scope, a site another App owns and never tags.
    The second run reads what the first wrote and updates it, so it goes through the scope rather than
    finding the Device in Bulk Write Mode's queue.
    """

    NEW_DEVICE = f"{UNLOADED_FROM_NAUTOBOT}-newdev"

    def _sync_site(self, *, locations_in_scope, bulk_write_mode, description=None, sync=True):
        """Sync the site, with a Device and an Interface on it, in a tagged-only run, or only diff it."""
        adapter = NautobotDiffSync(
            job=unittest.mock.Mock(),
            sync=unittest.mock.Mock(),
            sync_ipfabric_tagged_only=True,
            location_filter=None,
            bulk_write_mode=bulk_write_mode,
        )
        adapter.scope = SyncScope.from_job_kwargs({"sync_locations": locations_in_scope, "sync_vlans": False})
        adapter.load_data()
        source = self._source(locations_in_scope=locations_in_scope, with_device_at=(UNLOADED_FROM_NAUTOBOT,))
        device = source.get("device", {"name": self.NEW_DEVICE})
        interface = source.interface(
            name="eth0",
            device_name=device.name,
            status="Active",
            description=description,
            # What the sync writes where IP Fabric reports nothing, so that a run over unchanged data is empty.
            enabled=True,
            mac_address="00:00:00:00:00:01",
            mtu=1500,
            type="1000base-t",
            mgmt_only=False,
        )
        source.add(interface)
        device.add_child(interface)
        if not sync:
            return adapter.diff_from(source)
        adapter.sync_from(source)
        adapter.flush_pending_writes()
        return adapter

    def _assert_written_in_full(self, *, locations_in_scope, bulk_write_mode):
        self._sync_site(locations_in_scope=locations_in_scope, bulk_write_mode=bulk_write_mode)
        job_scoped_cache.clear_all()
        adapter = self._sync_site(
            locations_in_scope=locations_in_scope, bulk_write_mode=bulk_write_mode, description="uplink"
        )
        device = Device.objects.get(name=self.NEW_DEVICE)
        self.assertEqual(nbutils.get_syncable_device(device.name, scope=adapter.device_scope), device)
        self.assertEqual(device.interfaces.get(name="eth0").description, "uplink")
        job_scoped_cache.clear_all()
        unchanged = self._sync_site(
            locations_in_scope=locations_in_scope, bulk_write_mode=bulk_write_mode, description="uplink", sync=False
        )
        # Only the site under test: the fixture's other Devices are not reported by this source.
        self.assertNotIn(UNLOADED_FROM_NAUTOBOT, unchanged.dict().get("location", {}), unchanged.str())
        return device

    def test_a_site_created_in_the_run_takes_its_devices_interfaces(self):
        device = self._assert_written_in_full(locations_in_scope=True, bulk_write_mode=False)
        self.assertTrue(device.location.tags.filter(pk=self.ssot_tag.pk).exists())

    def test_a_site_created_in_a_bulk_run_takes_its_devices_interfaces(self):
        self._assert_written_in_full(locations_in_scope=True, bulk_write_mode=True)

    def test_another_apps_site_takes_its_devices_interfaces(self):
        self._location(UNLOADED_FROM_NAUTOBOT, tagged=False)
        device = self._assert_written_in_full(locations_in_scope=False, bulk_write_mode=False)
        self.assertFalse(device.location.tags.exists())

    def test_another_apps_site_takes_its_devices_interfaces_in_a_bulk_run(self):
        self._location(UNLOADED_FROM_NAUTOBOT, tagged=False)
        self._assert_written_in_full(locations_in_scope=False, bulk_write_mode=True)


class VlansAtAnotherAppsSitesTestCase(LocationScopeTestCase):
    """With Locations out of scope, a tagged-only run reads only the VLANs it tagged at the sites it reads."""

    def test_only_a_tagged_vlan_at_an_untagged_site_is_read(self):
        location = self._location("other-app-site", tagged=False)
        for vid, tagged in ((10, True), (20, False)):
            vlan = VLAN.objects.create(vid=vid, name=f"vlan{vid}", status=self.active_status)
            vlan.locations.add(location)
            if tagged:
                vlan.tags.add(self.ssot_tag)
        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_locations": False, "sync_interfaces": False})
        self.nb_adapter.load_data()
        self.assertEqual({vlan.vid for vlan in self.nb_adapter.get_all("vlan")}, {10})


class LocationReadTestCase(LocationScopeTestCase):
    """Which Locations a tagged-only run reads when Locations are another App's."""

    def _load_with_locations_out_of_scope(self, vlans=False):
        self.nb_adapter.scope = SyncScope.from_job_kwargs(
            {"sync_locations": False, "sync_interfaces": False, "sync_vlans": vlans}
        )
        self.nb_adapter.load_data()
        return {location.name for location in self.nb_adapter.get_all("location")}

    def test_only_the_locations_holding_what_the_sync_tagged_are_read(self):
        """An untagged Location is read only when it holds a Device the sync tagged."""
        self._location("other-app-site", tagged=False)
        holding = self._location("other-app-site-with-a-device", tagged=False)
        self._device("synced-dev", holding.name)
        self.assertEqual(
            self._load_with_locations_out_of_scope(),
            {KNOWN_TO_BOTH, UNKNOWN_TO_IPFABRIC, "other-app-site-with-a-device"},
        )

    def _add_vlan(self, location, vid, tagged=True, tenant=None):
        """Create a VLAN at the Location. It gets the synced Tag unless `tagged` is False."""
        vlan = VLAN.objects.create(vid=vid, name=f"vlan{vid}", status=self.active_status, tenant=tenant)
        vlan.locations.add(location)
        if tagged:
            vlan.tags.add(self.ssot_tag)

    def _vlan_site(self, name, vid, tagged=True, tenant=None):
        """Create an untagged Location holding only a VLAN."""
        location = self._location(name, tagged=False)
        self._add_vlan(location, vid, tagged=tagged, tenant=tenant)
        return location

    def test_a_location_holding_a_vlan_the_sync_tagged_is_read_with_vlans_in_scope(self):
        """With VLANs in scope, a Location is read for a VLAN the sync tagged, not for an untagged one."""
        self._vlan_site("tagged-vlan-site", 10)
        self._vlan_site("untagged-vlan-site", 20, tagged=False)
        read = self._load_with_locations_out_of_scope(vlans=True)
        self.assertIn("tagged-vlan-site", read)
        self.assertNotIn("untagged-vlan-site", read)

    def test_a_location_holding_only_a_vlan_is_not_read_with_vlans_out_of_scope(self):
        """With VLANs out of scope, a tagged VLAN does not make the sync read its Location."""
        self._vlan_site("tagged-vlan-site", 10)
        self.assertNotIn("tagged-vlan-site", self._load_with_locations_out_of_scope())

    def test_a_location_holding_another_tenants_vlan_is_not_read(self):
        """A Location is read only for a VLAN that both carries the Tag and belongs to the run's Tenant."""
        self.nb_adapter.tenant = Tenant.objects.create(name="customer-a")
        self._vlan_site("own-vlan-site", 10, tenant=self.nb_adapter.tenant)
        other_tenant = Tenant.objects.create(name="customer-b")
        self._vlan_site("other-vlan-site", 20, tenant=other_tenant)
        # Tagged, and the run's Tenant, but on two different VLANs: neither VLAN is one the run reads.
        mixed = self._vlan_site("mixed-vlan-site", 30, tenant=other_tenant)
        self._add_vlan(mixed, 40, tagged=False, tenant=self.nb_adapter.tenant)
        self.assertEqual(self._load_with_locations_out_of_scope(vlans=True), {"own-vlan-site"})

    def test_a_site_filter_narrows_them_to_its_location(self):
        """A Site Filter limits the Locations read to the one it names."""
        self.nb_adapter.location_filter = Location.objects.get(name=KNOWN_TO_BOTH)
        self.assertEqual(self._load_with_locations_out_of_scope(), {KNOWN_TO_BOTH})

    def test_two_locations_of_one_name_load_as_one(self):
        """Two Locations of one name under different parents load as one, with a warning."""
        floor_type = LocationType.objects.create(name="Floor", parent=self.site_type)
        floor_type.content_types.add(ContentType.objects.get_for_model(Device))
        for site_name in (KNOWN_TO_BOTH, UNKNOWN_TO_IPFABRIC):
            floor = Location.objects.create(
                name="Floor 1",
                location_type=floor_type,
                status=self.active_status,
                parent=Location.objects.get(name=site_name),
            )
            Device.objects.create(
                name=f"{site_name}-floor-dev",
                serial=f"{site_name}-floor-dev",
                status=self.active_status,
                role=self.role,
                location=floor,
                device_type=self.device_type,
            ).tags.add(self.ssot_tag)
        self.assertIn("Floor 1", self._load_with_locations_out_of_scope())
        floor = self.nb_adapter.get("location", "Floor 1")
        self.assertEqual(set(floor.devices), {f"{KNOWN_TO_BOTH}-floor-dev", f"{UNKNOWN_TO_IPFABRIC}-floor-dev"})
        self.assertIn("More than one Location is named Floor 1", job_log_text(self.nb_adapter.job.logger, "warning"))


class UnreportedSiteDependentsTestCase(LocationScopeTestCase):
    """With Locations out of scope, what belongs to a Device at a site the source does not report is kept."""

    DEPENDENTS = ("vrf_device_assignment", "interface_vrf", "interface_vlan", "cable")
    # Per model, how many records `_removed` returns with Locations in scope: one per Device, and one per Cable.
    EXPECTED_REMOVED = {"vrf_device_assignment": 2, "interface_vrf": 2, "interface_vlan": 2, "cable": 3}

    def _cable(self, end_a, end_b):
        self.nb_adapter.add(
            self.nb_adapter.cable(
                termination_a_device=end_a[0],
                termination_a_name=end_a[1],
                termination_b_device=end_b[0],
                termination_b_name=end_b[1],
                status="Connected",
            )
        )

    def _removed(self, locations_in_scope):
        """Diff a source reporting only the shared site, and return what it would remove, by model."""
        self.nb_adapter.scope = SyncScope.from_job_kwargs({"sync_locations": locations_in_scope})
        for site_name in (KNOWN_TO_BOTH, UNKNOWN_TO_IPFABRIC):
            device_name = f"{site_name}-dev"
            self.nb_adapter.add(
                self.nb_adapter.device(
                    name=device_name,
                    location_name=site_name,
                    model="dev_type1",
                    vendor="man1",
                    serial_number=device_name,
                    role="test",
                    status="Active",
                )
            )
            self.nb_adapter.add(self.nb_adapter.vrf_device_assignment(vrf_name="BLUE", device_name=device_name))
            self.nb_adapter.add(
                self.nb_adapter.interface_vrf(device_name=device_name, interface_name="eth0", vrf_name="BLUE")
            )
            self.nb_adapter.add(
                self.nb_adapter.interface_vlan(device_name=device_name, interface_name="eth0", mode="access")
            )
        known, unknown = f"{KNOWN_TO_BOTH}-dev", f"{UNKNOWN_TO_IPFABRIC}-dev"
        # Two Cables with one end at the unreported site, on the A side and then the B side, and one Cable
        # with both ends at the shared site.
        self._cable((known, "eth0"), (unknown, "eth0"))
        self._cable((unknown, "eth1"), (known, "eth1"))
        self._cable((known, "eth2"), (known, "eth3"))
        diff = self.nb_adapter.diff_from(self._source(locations_in_scope))
        return {
            # A removal has a "-" side and no "+" side. The "-" side is empty when the model has no attributes.
            model_name: {name for name, change in diff.dict().get(model_name, {}).items() if "+" not in change}
            for model_name in self.DEPENDENTS
        }

    def test_a_device_at_an_unreported_site_keeps_its_assignments_and_cables(self):
        """With Locations out of scope, only what belongs to the Device at the reported site is removed."""
        removed = self._removed(locations_in_scope=False)
        for model_name in self.DEPENDENTS:
            with self.subTest(model_name):
                self.assertEqual(len(removed[model_name]), 1)
                self.assertNotIn(UNKNOWN_TO_IPFABRIC, next(iter(removed[model_name])))

    def test_with_locations_in_scope_they_are_removed_with_the_site(self):
        """With Locations in scope, everything at the unreported site is removed along with it."""
        removed = self._removed(locations_in_scope=True)
        for model_name in self.DEPENDENTS:
            with self.subTest(model_name):
                self.assertEqual(len(removed[model_name]), self.EXPECTED_REMOVED[model_name])
