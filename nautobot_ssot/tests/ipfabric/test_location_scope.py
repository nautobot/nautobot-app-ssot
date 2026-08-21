"""Tests for taking Locations out of an IP Fabric sync's scope.

Locations are the root of the object tree, so they cannot simply be left unloaded: every Device and
VLAN is a child of one. Deselecting them withholds *writing* Locations while still using them to
reach their children, and these tests pin that distinction where it is decided — in the diff for what
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

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.sync_scope import (
    UNSYNCED_LOCATION_ATTRS,
    SyncScope,
    unsynced_location_flags,
)
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

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
        self.site_type.content_types.add(device_ct)
        manufacturer = Manufacturer.objects.create(name="man1")
        self.device_type = DeviceType.objects.create(model="dev_type1", manufacturer=manufacturer)
        self.ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN},
        )
        self.ssot_tag.content_types.add(device_ct)
        self.ssot_tag.content_types.add(ContentType.objects.get_for_model(Location))

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
        """Return a source adapter reporting the shared site and one this sync did not load."""
        source = DiffSyncModelAdapters()
        for site_name in (KNOWN_TO_BOTH, UNLOADED_FROM_NAUTOBOT):
            attrs = {"site_id": "ipf-id", "status": "Active"} if locations_in_scope else dict(UNSYNCED_LOCATION_ATTRS)
            location = source.location(name=site_name, **attrs)
            if not locations_in_scope:
                location.model_flags |= unsynced_location_flags()
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

        Another SSoT App owns Locations, so the one it created carries no IP Fabric tag and a
        tagged-only run does not load it. Looking it up by name is what lets the Device be placed.
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
