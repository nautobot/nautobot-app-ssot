"""Tests for taking Locations out of an IP Fabric sync's scope.

Locations are the root of the object tree, so they cannot simply be left unloaded: every Device and
VLAN is a child of one. Deselecting them withholds *writing* Locations while still using them to
reach their children, and these tests pin that distinction by diffing rather than by inspecting the
adapters, since it is the diff that decides what gets written.
"""

import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.sync_scope import (
    UNSYNCED_LOCATION_ATTRS,
    SyncScope,
    unsynced_location_flags,
)

# A site IP Fabric reports that Nautobot has never heard of.
UNKNOWN_TO_NAUTOBOT = "site-discovered"
# A site Nautobot holds that IP Fabric does not report.
UNKNOWN_TO_IPFABRIC = "site-unreported"
# A site both sides know, whose IP Fabric site ID differs from the one Nautobot has recorded.
KNOWN_TO_BOTH = "site-shared"


class LocationScopeTestCase(TestCase):
    """Diff a Nautobot estate against a source that disagrees about Locations three ways."""

    def setUp(self):
        populate_status_choices()
        self.active_status = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="test")
        role.content_types.add(device_ct)
        site_lt, _ = LocationType.objects.get_or_create(name="site")
        site_lt.content_types.add(device_ct)
        manufacturer = Manufacturer.objects.create(name="man1")
        device_type = DeviceType.objects.create(model="dev_type1", manufacturer=manufacturer)

        for site_name in (KNOWN_TO_BOTH, UNKNOWN_TO_IPFABRIC):
            location = Location.objects.create(name=site_name, location_type=site_lt, status=self.active_status)
            Device.objects.create(
                name=f"{site_name}-dev",
                serial=site_name,
                status=self.active_status,
                role=role,
                location=location,
                device_type=device_type,
            )

        self.nb_adapter = NautobotDiffSync(
            job=unittest.mock.Mock(),
            sync=unittest.mock.Mock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
        )

    def _source(self, locations_in_scope):
        """Return a source adapter reporting the shared site and one Nautobot has never seen."""
        source = DiffSyncModelAdapters()
        for site_name in (KNOWN_TO_BOTH, UNKNOWN_TO_NAUTOBOT):
            attrs = {"site_id": "ipf-id", "status": "Active"} if locations_in_scope else dict(UNSYNCED_LOCATION_ATTRS)
            location = source.location(name=site_name, **attrs)
            if not locations_in_scope:
                location.model_flags |= unsynced_location_flags()
            source.add(location)
        return source

    def _diff(self, locations_in_scope):
        """Load Nautobot with the given Location scope and diff it against the matching source."""
        self.nb_adapter.scope = SyncScope.from_job_kwargs(
            {"sync_locations": locations_in_scope, "sync_interfaces": False, "sync_vlans": False}
        )
        self.nb_adapter.load_data()
        return self.nb_adapter.diff_from(self._source(locations_in_scope))

    @staticmethod
    def _location_changes(diff):
        """Return the Locations the diff would write, and what it would write about each."""
        return {
            name: {side: change[side] for side in ("+", "-") if change.get(side)}
            for name, change in diff.dict().get("location", {}).items()
            if change.get("+") or change.get("-")
        }

    def test_locations_in_scope_are_created_updated_and_deleted(self):
        """The default behaviour, recorded here so the out of scope case is a visible contrast."""
        changes = self._location_changes(self._diff(locations_in_scope=True))

        self.assertEqual(set(changes), {KNOWN_TO_BOTH, UNKNOWN_TO_NAUTOBOT, UNKNOWN_TO_IPFABRIC})
        # The shared site is updated, since IP Fabric's site ID is not the one Nautobot recorded.
        self.assertEqual(changes[KNOWN_TO_BOTH]["+"], {"site_id": "ipf-id"})
        # The discovered site is created, and the unreported one deleted.
        self.assertIn("+", changes[UNKNOWN_TO_NAUTOBOT])
        self.assertIn("-", changes[UNKNOWN_TO_IPFABRIC])

    def test_locations_out_of_scope_are_never_written(self):
        """No Location is created, updated or deleted, whichever side it is missing from."""
        diff = self._diff(locations_in_scope=False)

        self.assertEqual(self._location_changes(diff), {})
        summary = diff.summary()
        self.assertEqual(summary["create"], 0)
        self.assertEqual(summary["update"], 0)

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

    def test_a_discovered_location_is_not_created_nor_its_children(self):
        """A site only IP Fabric knows is skipped, since its Devices would have nowhere to go."""
        diff = self._diff(locations_in_scope=False)

        self.assertNotIn(UNKNOWN_TO_NAUTOBOT, diff.dict().get("location", {}))
