"""Unit tests for the IP Fabric per object type sync controls."""

from unittest import mock

from diffsync.enum import DiffSyncModelFlags
from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.ipfabric import sync_scope
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Location
from nautobot_ssot.integrations.ipfabric.sync_scope import (
    DISABLED_OBJECTS_SETTING,
    SYNCABLE_OBJECTS,
    UNSYNCED_LOCATION_ATTRS,
    UNSYNCED_LOCATION_FLAGS,
    SyncableObject,
    SyncScope,
    disabled_keys,
    form_fields,
    scope_field_order,
    selectable_objects,
    validate_registry,
)


def patched_config(**settings):
    """Patch the settings the registry reads, leaving the rest of `PLUGINS_CONFIG` alone."""
    return mock.patch.dict(sync_scope.CONFIG, settings, clear=False)


class SyncableObjectTestCase(TestCase):
    """Test the registration of a single object type."""

    def test_names_are_derived_from_the_key(self):
        """The form field and the settings key both follow from the key, so they cannot drift apart."""
        syncable = SyncableObject(key="widgets", label="Sync Widgets", description="Widgets.", default=True)
        self.assertEqual(syncable.field_name, "sync_widgets")
        self.assertEqual(syncable.setting_name, "ipfabric_sync_widgets")

    def test_default_selection_falls_back_to_the_registration(self):
        """With nothing configured, the registered default decides the form's initial state."""
        syncable = SyncableObject(key="widgets", label="Sync Widgets", description="Widgets.", default=False)
        self.assertFalse(syncable.default_selection())

    def test_default_selection_is_overridable_by_settings(self):
        """An installation can pre-select an object type the integration ships as off."""
        syncable = SyncableObject(key="widgets", label="Sync Widgets", description="Widgets.", default=False)
        with patched_config(ipfabric_sync_widgets=True):
            self.assertTrue(syncable.default_selection())

    def test_form_field_names_the_requirement(self):
        """An operator should be able to see from the form why a selection may not take effect."""
        syncable = SyncableObject(
            key="widgets",
            label="Sync Widgets",
            description="Widgets.",
            default=True,
            requires=("gadgets",),
        )
        help_text = syncable.form_field().field_attrs["help_text"]
        self.assertIn("Skipped unless 'gadgets' is also selected", help_text)

    def test_form_field_carries_the_registration(self):
        """The generated field is the only place the label and default reach the form."""
        syncable = SyncableObject(key="widgets", label="Sync Widgets", description="Widgets.", default=True)
        field_attrs = syncable.form_field().field_attrs
        self.assertEqual(field_attrs["label"], "Sync Widgets")
        self.assertTrue(field_attrs["initial"])
        self.assertEqual(field_attrs["help_text"], "Widgets.")

    def test_the_shipped_registry_validates(self):
        """The registry the integration ships must pass the checks applied at import."""
        self.assertEqual(validate_registry(SYNCABLE_OBJECTS).keys(), {s.key for s in SYNCABLE_OBJECTS})

    def test_validate_registry_rejects_an_unknown_requirement(self):
        """A requirement naming an unregistered object type would never be satisfied."""
        with self.assertRaises(ValueError) as caught:
            validate_registry(
                [SyncableObject(key="widgets", label="W", description="W.", default=True, requires=("gadgets",))]
            )
        self.assertIn("requires unknown object type 'gadgets'", str(caught.exception))

    def test_validate_registry_rejects_a_duplicate_key(self):
        """Two registrations sharing a key would collapse into one form field."""
        duplicate = SyncableObject(key="widgets", label="W", description="W.", default=True)
        with self.assertRaises(ValueError) as caught:
            validate_registry([duplicate, duplicate])
        self.assertIn("Duplicate object type 'widgets'", str(caught.exception))


class UnsyncedLocationTestCase(TestCase):
    """Test the pieces that make an out of scope Location a tree node rather than synced data."""

    def test_locations_are_selectable(self):
        """Locations must appear on the form, unlike the always on Devices."""
        self.assertIn("sync_locations", form_fields())

    def test_locations_default_to_on(self):
        """Deselecting Locations has to be a deliberate act, not the shipped behaviour."""
        self.assertTrue(SyncScope.from_job_kwargs({}).locations)

    def test_nothing_requires_locations(self):
        """Devices at Locations that already exist must still sync with Locations out of scope."""
        for syncable in SYNCABLE_OBJECTS:
            self.assertNotIn("locations", syncable.requires, syncable.key)

    def test_placeholder_attributes_cover_every_location_attribute(self):
        """A real attribute left out of the placeholder would still diff, and so still be written."""
        self.assertEqual(set(UNSYNCED_LOCATION_ATTRS), set(Location._attributes))  # pylint: disable=protected-access

    def test_flags_skip_deletion_only(self):
        """Deletes need a flag; creates are declined in `Location.create` so children are reached."""
        self.assertTrue(UNSYNCED_LOCATION_FLAGS & DiffSyncModelFlags.SKIP_UNMATCHED_DST)
        self.assertFalse(
            UNSYNCED_LOCATION_FLAGS & DiffSyncModelFlags.SKIP_UNMATCHED_SRC,
            "Skipping unmatched source Locations would drop the Devices at them from the diff.",
        )

    def test_flags_do_not_ignore_the_location(self):
        """IGNORE would drop the Location's children from the diff along with the Location."""
        self.assertFalse(UNSYNCED_LOCATION_FLAGS & DiffSyncModelFlags.IGNORE)


class SyncScopeTestCase(TestCase):
    """Test resolving a submitted selection into the scope a run works from."""

    def test_selected_object_types_are_in_scope(self):
        """A selection with its requirements met is honoured."""
        scope = SyncScope(("interfaces", "vlans"))
        self.assertTrue(scope.interfaces)
        self.assertTrue(scope.vlans)
        self.assertTrue(scope.is_enabled("vlans"))

    def test_unselected_object_types_are_out_of_scope(self):
        self.assertFalse(SyncScope(("vlans",)).cables)

    def test_unknown_object_types_are_ignored(self):
        """A stale keyword argument naming a removed object type must not appear in scope."""
        scope = SyncScope(("vlans", "widgets"))
        self.assertEqual(list(scope), ["vlans"])

    def test_unregistered_attribute_still_raises(self):
        """Attribute access must not answer for object types that were never registered."""
        with self.assertRaises(AttributeError):
            SyncScope(()).widgets  # pylint: disable=expression-not-assigned,pointless-statement

    def test_requirement_not_met_drops_the_selection(self):
        """Cables need Interfaces in the store, so selecting Cables alone cannot be honoured."""
        scope = SyncScope(("cables",))
        self.assertFalse(scope.cables)
        self.assertEqual(
            scope.explanations(),
            ["Not syncing 'cables' as it requires 'interfaces', which is not in scope."],
        )

    def test_requirement_chains_collapse_in_full(self):
        """Dropping Interfaces has to take IP Addresses with it, and Primary IP with those."""
        scope = SyncScope(("ip_addresses", "primary_ip", "cables"))
        self.assertEqual(list(scope), [])
        self.assertEqual(len(scope.explanations()), 3)

    def test_iteration_follows_registration_order(self):
        """The log and the form should list object types in the same order."""
        scope = SyncScope(("vlans", "interfaces"))
        self.assertEqual(list(scope), ["interfaces", "vlans"])

    def test_describe_reports_every_object_type(self):
        """The job log needs the types that are off as much as the ones that are on."""
        described = SyncScope(("interfaces",)).describe()
        self.assertIn("interfaces: True", described)
        self.assertIn("vlans: False", described)

    def test_repr_names_the_object_types_in_scope(self):
        self.assertEqual(repr(SyncScope(("vlans",))), "SyncScope(vlans)")
        self.assertEqual(repr(SyncScope(())), "SyncScope(nothing)")

    def test_from_job_kwargs_reads_the_submitted_form(self):
        scope = SyncScope.from_job_kwargs({"sync_interfaces": True, "sync_vlans": False, "sync_cables": True})
        self.assertTrue(scope.cables)
        self.assertFalse(scope.vlans)

    def test_from_job_kwargs_falls_back_to_defaults(self):
        """A run created before an object type existed must behave as the form would now."""
        scope = SyncScope.from_job_kwargs({})
        self.assertTrue(scope.interfaces)
        self.assertTrue(scope.vlans)
        self.assertFalse(scope.cables)

    def test_from_job_kwargs_respects_configured_defaults(self):
        """An installation that pre-selects Cables gets them without touching the form."""
        with patched_config(ipfabric_sync_cables=True):
            self.assertTrue(SyncScope.from_job_kwargs({}).cables)


class AdministrativeDisableTestCase(TestCase):
    """Test denying an object type for a whole Nautobot instance."""

    def test_disabled_object_types_are_absent_from_the_form(self):
        """A denied object type must not be selectable, rather than merely defaulted off."""
        with patched_config(**{DISABLED_OBJECTS_SETTING: ["vlans"]}):
            self.assertNotIn("sync_vlans", form_fields())
            self.assertNotIn("vlans", [syncable.key for syncable in selectable_objects()])

    def test_disabled_object_types_are_dropped_from_a_submitted_scope(self):
        """A selection made through the API cannot get around the deny list."""
        with patched_config(**{DISABLED_OBJECTS_SETTING: ["vlans"]}):
            scope = SyncScope(("interfaces", "vlans"))
        self.assertFalse(scope.vlans)
        self.assertTrue(scope.interfaces)
        self.assertEqual(
            scope.explanations(),
            [
                "Not syncing 'vlans' as it is disabled for this Nautobot instance by the "
                "'ipfabric_disabled_sync_objects' setting."
            ],
        )

    def test_disabling_a_parent_disables_its_children(self):
        """Denying Interfaces has to deny Cables too, since Cables cannot load without them."""
        with patched_config(**{DISABLED_OBJECTS_SETTING: ["interfaces"]}):
            scope = SyncScope(("interfaces", "ip_addresses", "cables"))
        self.assertEqual(list(scope), [])

    def test_unknown_disabled_object_types_are_ignored(self):
        """A typo in the deny list must not silently deny everything, or nothing recognisable."""
        with patched_config(**{DISABLED_OBJECTS_SETTING: ["widgets"]}):
            self.assertEqual(disabled_keys(), ())
            self.assertEqual(len(selectable_objects()), len(SYNCABLE_OBJECTS))

    def test_field_order_names_every_object_type(self):
        """Ordering must not shift with settings, so it names denied object types as well."""
        with patched_config(**{DISABLED_OBJECTS_SETTING: ["vlans"]}):
            self.assertIn("sync_vlans", scope_field_order())
        self.assertEqual(len(scope_field_order()), len(SYNCABLE_OBJECTS))
