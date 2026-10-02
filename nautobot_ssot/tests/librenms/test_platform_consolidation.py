"""Unit tests for the LibreNMS Platform Consolidation job's logic."""

from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType, LocationType, Manufacturer, SoftwareImageFile, SoftwareVersion
from nautobot.dcim.models import Location as ORMLocation
from nautobot.dcim.models import Platform as ORMPlatform
from nautobot.extras.jobs import DryRunVar
from nautobot.extras.models import ConfigContext, DynamicGroup, Note, Role, Status
from nautobot.users.models import ObjectPermission

from nautobot_ssot.integrations.librenms.jobs import (
    LibrenmsPlatformConsolidation,
)
from nautobot_ssot.integrations.librenms.jobs import (
    jobs as librenms_jobs,
)
from nautobot_ssot.integrations.librenms.platform_consolidation import (
    ACTION_MERGE_INTO,
    ACTION_RENAME,
    ACTION_REPAIR_DRIVER,
    COLLISION_MERGE,
    CSV_COLUMNS,
    DEVICE_TYPE_MERGE,
    MANUFACTURER_CLEAR,
    SCOPE_SELECTED,
    PlatformConsolidator,
    build_csv,
    get_software_lcm_model,
    legacy_manufacturer_renames,
    needs_driver_repair,
    resolve_scope,
)
from nautobot_ssot.jobs.base import DataSource, DataTarget

PLUGIN_CFG_PATH = "nautobot_ssot.integrations.librenms.constants.PLUGIN_CFG"
CONSOLIDATION_CFG_PATH = "nautobot_ssot.integrations.librenms.platform_consolidation.PLUGIN_CFG"


class ConsolidationTestCase(TestCase):  # pylint: disable=too-many-instance-attributes
    """Shared fixtures for the consolidation tests."""

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()
        self.logger = MagicMock()
        self.cisco, _ = Manufacturer.objects.get_or_create(name="Cisco")
        self.fortinet, _ = Manufacturer.objects.get_or_create(name="Fortinet")
        self.active, _ = Status.objects.get_or_create(name="Active")
        self.active.content_types.add(ContentType.objects.get_for_model(ORMDevice))
        self.active.content_types.add(ContentType.objects.get_for_model(SoftwareVersion))
        self.active.content_types.add(ContentType.objects.get_for_model(SoftwareImageFile))

        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        self.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))
        self.location = ORMLocation.objects.create(name="Test Site", location_type=self.site_type, status=self.active)
        self.role, _ = Role.objects.get_or_create(name="network")
        self.role.content_types.add(ContentType.objects.get_for_model(ORMDevice))
        self.device_type, _ = DeviceType.objects.get_or_create(model="C9300", manufacturer=self.cisco)

    def consolidator(self, **kwargs):
        """Build a consolidator scoped to every Platform, with sane test defaults."""
        options = {
            "logger": self.logger,
            "dry_run": False,
            "scope": SCOPE_SELECTED,
            "platforms": list(ORMPlatform.objects.all()),
        }
        options.update(kwargs)
        return PlatformConsolidator(**options)

    def make_device(self, name, platform, device_type=None):
        """Create a Device on the given Platform."""
        return ORMDevice.objects.create(
            name=name,
            device_type=device_type or self.device_type,
            role=self.role,
            location=self.location,
            status=self.active,
            platform=platform,
        )

    @staticmethod
    def consolidated_mode(enabled=True):
        """Patch the setting the rename and merge phases require."""
        return patch.dict(CONSOLIDATION_CFG_PATH, {"librenms_consolidated_platforms": enabled})


class TestDriverRepair(ConsolidationTestCase):
    """Phase 1: repair network drivers."""

    def test_repairs_fqcn_row_with_fqcn_driver(self):
        """The shape the LibreNMS integration used to create."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")

        self.consolidator().run()

        platform.refresh_from_db()
        self.assertEqual(platform.network_driver, "cisco_ios")

    def test_repairs_fqcn_row_with_blank_driver(self):
        """A blank driver is also repaired."""
        platform = ORMPlatform.objects.create(name="junipernetworks.junos.junos", network_driver="")

        self.consolidator().run()

        platform.refresh_from_db()
        self.assertEqual(platform.network_driver, "juniper_junos")

    def test_ignores_dna_center_style_row(self):
        """dna_center writes a correct driver alongside the FQCN name; leave it alone."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        self.assertFalse(needs_driver_repair(platform))

        self.consolidator().run()

        platform.refresh_from_db()
        self.assertEqual(platform.network_driver, "cisco_ios")

    def test_ignores_operator_named_row(self):
        """A hand-named Platform is never given an invented driver."""
        platform = ORMPlatform.objects.create(name="Cisco IOS", network_driver="")
        self.assertFalse(needs_driver_repair(platform))

        self.consolidator().run()

        platform.refresh_from_db()
        self.assertEqual(platform.network_driver, "")

    def test_never_overwrites_a_disagreeing_driver(self):
        """An FQCN-named row already claimed by another driver is left alone."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_nxos")

        self.consolidator().run()

        platform.refresh_from_db()
        self.assertEqual(platform.network_driver, "cisco_nxos")

    def test_repair_is_safe_in_legacy_mode(self):
        """The repair phase does not require consolidated mode."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")

        with self.consolidated_mode(False):
            self.consolidator().run()

        platform.refresh_from_db()
        self.assertEqual(platform.network_driver, "cisco_ios")

    def test_dry_run_writes_nothing(self):
        """Dry run is a genuine read-only pass."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")

        plans = self.consolidator(dry_run=True).run()

        platform.refresh_from_db()
        self.assertEqual(platform.network_driver, "cisco.ios.ios")
        self.assertIn(ACTION_REPAIR_DRIVER, plans[0].actions)
        self.assertEqual(plans[0].intended_driver, "cisco_ios")


class TestRename(ConsolidationTestCase):
    """Phase 2: rename legacy platforms."""

    def test_refuses_while_flag_is_off(self):
        """In legacy mode the sync would just re-create the FQCN row."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")

        with self.consolidated_mode(False):
            self.consolidator(repair_network_drivers=False, rename_legacy_platforms=True).run()

        platform.refresh_from_db()
        self.assertEqual(platform.name, "cisco.ios.ios")
        self.logger.error.assert_called()

    def test_renames_when_target_is_free(self):
        """The primary key is preserved, so every foreign key survives."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        device = self.make_device("router-1", platform)

        with self.consolidated_mode():
            self.consolidator(rename_legacy_platforms=True).run()

        platform.refresh_from_db()
        self.assertEqual(platform.name, "cisco_ios")
        device.refresh_from_db()
        self.assertEqual(device.platform_id, platform.pk)

    def test_refuses_when_target_name_is_taken(self):
        """Renaming onto an existing name is a merge, not a rename."""
        legacy = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios")

        with self.consolidated_mode():
            plans = self.consolidator(repair_network_drivers=False, rename_legacy_platforms=True).run()

        legacy.refresh_from_db()
        self.assertEqual(legacy.name, "cisco.ios.ios")
        legacy_plan = next(plan for plan in plans if plan.platform.pk == legacy.pk)
        self.assertIn("already used", legacy_plan.refusal_reason)

    def test_refuses_when_an_object_permission_references_the_name(self):
        """Rewriting a permission constraint could widen or narrow access."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        permission = ObjectPermission.objects.create(
            name="ios-only", actions=["view"], constraints={"platform__name": "cisco.ios.ios"}
        )
        permission.object_types.add(ContentType.objects.get_for_model(ORMDevice))

        with self.consolidated_mode():
            plans = self.consolidator(repair_network_drivers=False, rename_legacy_platforms=True).run()

        platform.refresh_from_db()
        self.assertEqual(platform.name, "cisco.ios.ios")
        self.assertIn("ObjectPermission", plans[0].refusal_reason)

    def test_reports_dynamic_group_reference_without_rewriting_by_default(self):
        """Name-based references are reported; rewriting them is opt-in."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        group = self._device_dynamic_group(platform_names=["cisco.ios.ios"])

        with self.consolidated_mode():
            plans = self.consolidator(repair_network_drivers=False, rename_legacy_platforms=True).run()

        platform.refresh_from_db()
        self.assertEqual(platform.name, "cisco_ios")
        group.refresh_from_db()
        self.assertEqual(group.filter["platform"], ["cisco.ios.ios"])
        self.assertIn(f"DynamicGroup:{group.name}", plans[0].references)

    def test_rewrites_dynamic_group_filter_when_opted_in(self):
        """DeviceFilterSet.platform stores names, so a stale filter silently stops matching."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        group = self._device_dynamic_group(platform_names=["cisco.ios.ios"])

        with self.consolidated_mode():
            self.consolidator(
                repair_network_drivers=False,
                rename_legacy_platforms=True,
                update_dynamic_group_filters=True,
            ).run()

        platform.refresh_from_db()
        self.assertEqual(platform.name, "cisco_ios")
        group.refresh_from_db()
        self.assertEqual(group.filter["platform"], ["cisco_ios"])

    def _device_dynamic_group(self, platform_names):
        """Create a Device dynamic group filtering on platform names."""
        return DynamicGroup.objects.create(
            name="ios-devices",
            content_type=ContentType.objects.get_for_model(ORMDevice),
            filter={"platform": platform_names},
        )


class TestMerge(ConsolidationTestCase):
    """Phase 3: merge duplicate platforms."""

    def _duplicate_pair(self):
        """A driver-named survivor and an FQCN-named loser sharing one driver."""
        survivor = ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios")
        loser = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        return survivor, loser

    def test_refuses_while_flag_is_off(self):
        """Merging in legacy mode would be undone by the next sync."""
        survivor, loser = self._duplicate_pair()
        device = self.make_device("router-1", loser)

        with self.consolidated_mode(False):
            self.consolidator(repair_network_drivers=False, merge_duplicates=True).run()

        device.refresh_from_db()
        self.assertEqual(device.platform_id, loser.pk)
        self.assertTrue(ORMPlatform.objects.filter(pk=survivor.pk).exists())
        self.logger.error.assert_called()

    def test_survivor_is_the_exactly_named_row(self):
        """A row named after the driver wins regardless of object counts."""
        survivor, loser = self._duplicate_pair()
        device = self.make_device("router-1", loser)

        with self.consolidated_mode():
            self.consolidator(repair_network_drivers=False, merge_duplicates=True).run()

        device.refresh_from_db()
        self.assertEqual(device.platform_id, survivor.pk)

    def test_moves_devices_and_config_contexts(self):
        """Devices and ConfigContext assignments both follow the merge."""
        survivor, loser = self._duplicate_pair()
        device = self.make_device("router-1", loser)
        config_context = ConfigContext.objects.create(name="ios-context", weight=100, data={"a": 1})
        config_context.platforms.add(loser)

        with self.consolidated_mode():
            self.consolidator(repair_network_drivers=False, merge_duplicates=True).run()

        device.refresh_from_db()
        self.assertEqual(device.platform_id, survivor.pk)
        self.assertTrue(ConfigContext.objects.filter(pk=config_context.pk, platforms=survivor).exists())
        self.assertFalse(ConfigContext.objects.filter(pk=config_context.pk, platforms=loser).exists())

    def test_moves_notes(self):
        """Notes have no GenericRelation, so they would otherwise be orphaned."""
        survivor, loser = self._duplicate_pair()
        note = Note.objects.create(
            assigned_object_type=ContentType.objects.get_for_model(ORMPlatform),
            assigned_object_id=loser.pk,
            user_name="tester",
            note="keep me",
        )

        with self.consolidated_mode():
            self.consolidator(repair_network_drivers=False, merge_duplicates=True).run()

        note.refresh_from_db()
        self.assertEqual(note.assigned_object_id, survivor.pk)

    def test_moves_non_colliding_software_versions(self):
        """A version unique to the loser is simply repointed."""
        survivor, loser = self._duplicate_pair()
        version = SoftwareVersion.objects.create(platform=loser, version="17.3.1", status=self.active)

        with self.consolidated_mode():
            self.consolidator(repair_network_drivers=False, merge_duplicates=True).run()

        version.refresh_from_db()
        self.assertEqual(version.platform_id, survivor.pk)

    def test_refuses_on_software_version_collision_by_default(self):
        """(platform, version) is unique, so a collision cannot just be repointed."""
        survivor, loser = self._duplicate_pair()
        SoftwareVersion.objects.create(platform=survivor, version="17.3.1", status=self.active)
        loser_version = SoftwareVersion.objects.create(platform=loser, version="17.3.1", status=self.active)
        device = self.make_device("router-1", loser)

        with self.consolidated_mode():
            plans = self.consolidator(repair_network_drivers=False, merge_duplicates=True).run()

        loser_version.refresh_from_db()
        self.assertEqual(loser_version.platform_id, loser.pk)
        device.refresh_from_db()
        self.assertEqual(device.platform_id, loser.pk, "Nothing should move when the merge is refused.")
        loser_plan = next(plan for plan in plans if plan.platform.pk == loser.pk)
        self.assertIn("17.3.1", loser_plan.refusal_reason)

    def test_merges_software_versions_when_opted_in(self):
        """Colliding versions fold together, repointing the devices that used them."""
        survivor, loser = self._duplicate_pair()
        survivor_version = SoftwareVersion.objects.create(platform=survivor, version="17.3.1", status=self.active)
        loser_version = SoftwareVersion.objects.create(platform=loser, version="17.3.1", status=self.active)
        device = self.make_device("router-1", loser)
        device.software_version = loser_version
        device.validated_save()

        with self.consolidated_mode():
            self.consolidator(
                repair_network_drivers=False,
                merge_duplicates=True,
                software_version_collisions=COLLISION_MERGE,
            ).run()

        device.refresh_from_db()
        self.assertEqual(device.platform_id, survivor.pk)
        self.assertEqual(device.software_version_id, survivor_version.pk)
        self.assertFalse(SoftwareVersion.objects.filter(pk=loser_version.pk).exists())

    def test_merges_software_image_files_preserving_device_types(self):
        """A colliding image file folds its device types into the surviving one."""
        survivor, loser = self._duplicate_pair()
        survivor_version = SoftwareVersion.objects.create(platform=survivor, version="17.3.1", status=self.active)
        loser_version = SoftwareVersion.objects.create(platform=loser, version="17.3.1", status=self.active)
        survivor_image = SoftwareImageFile.objects.create(
            software_version=survivor_version, image_file_name="17.3.1.bin", status=self.active
        )
        loser_image = SoftwareImageFile.objects.create(
            software_version=loser_version, image_file_name="17.3.1.bin", status=self.active
        )
        loser_image.device_types.add(self.device_type)

        with self.consolidated_mode():
            self.consolidator(
                repair_network_drivers=False,
                merge_duplicates=True,
                software_version_collisions=COLLISION_MERGE,
            ).run()

        self.assertFalse(SoftwareImageFile.objects.filter(pk=loser_image.pk).exists())
        survivor_image.refresh_from_db()
        self.assertIn(self.device_type, survivor_image.device_types.all())

    def test_refuses_on_manufacturer_conflict(self):
        """Moving devices onto a survivor of another Manufacturer would fail Device.clean()."""
        survivor = ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios", manufacturer=self.fortinet)
        loser = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios", manufacturer=self.cisco)
        device = self.make_device("router-1", loser)

        with self.consolidated_mode():
            plans = self.consolidator(repair_network_drivers=False, merge_duplicates=True).run()

        device.refresh_from_db()
        self.assertEqual(device.platform_id, loser.pk)
        loser_plan = next(plan for plan in plans if plan.platform.pk == loser.pk)
        self.assertIn("Manufacturer", loser_plan.refusal_reason)
        self.assertTrue(ORMPlatform.objects.filter(pk=survivor.pk).exists())

    def test_clears_manufacturer_when_opted_in(self):
        """The explicit escape hatch for a manufacturer conflict."""
        survivor = ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios", manufacturer=self.fortinet)
        loser = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios", manufacturer=self.cisco)
        device = self.make_device("router-1", loser)

        with self.consolidated_mode():
            self.consolidator(
                repair_network_drivers=False,
                merge_duplicates=True,
                manufacturer_conflicts=MANUFACTURER_CLEAR,
            ).run()

        survivor.refresh_from_db()
        self.assertIsNone(survivor.manufacturer)
        device.refresh_from_db()
        self.assertEqual(device.platform_id, survivor.pk)

    def test_never_deletes_a_platform_with_software_versions(self):
        """Deleting would CASCADE and destroy the version history and its image files."""
        _survivor, loser = self._duplicate_pair()
        SoftwareVersion.objects.create(platform=loser, version="17.3.1", status=self.active)

        with self.consolidated_mode():
            plans = self.consolidator(
                repair_network_drivers=False,
                merge_duplicates=True,
                delete_merged_platforms=True,
                # Refuse the collision path so the version stays put and blocks the delete.
                software_version_collisions=COLLISION_MERGE,
            ).run()

        # The version moved, so the emptied platform is safe to delete.
        self.assertFalse(ORMPlatform.objects.filter(pk=loser.pk).exists())
        self.assertTrue(any(plan.platform.pk == loser.pk for plan in plans))

    def test_refuses_delete_while_versions_remain(self):
        """A version that could not move keeps the platform alive."""
        survivor, loser = self._duplicate_pair()
        # Give the survivor a colliding version and refuse collisions, so nothing can move.
        SoftwareVersion.objects.create(platform=survivor, version="17.3.1", status=self.active)
        SoftwareVersion.objects.create(platform=loser, version="17.3.1", status=self.active)

        with self.consolidated_mode():
            self.consolidator(repair_network_drivers=False, merge_duplicates=True, delete_merged_platforms=True).run()

        self.assertTrue(ORMPlatform.objects.filter(pk=loser.pk).exists())

    def test_never_deletes_a_platform_with_lifecycle_software_records(self):
        """SoftwareLCM.device_platform is a second CASCADE FK; deleting would destroy its rows."""
        software_lcm = get_software_lcm_model()
        if software_lcm is None:
            self.skipTest("nautobot-device-lifecycle-mgmt is not installed")
        _survivor, loser = self._duplicate_pair()
        software_lcm.objects.create(device_platform=loser, version="17.3.1")

        with self.consolidated_mode():
            plans = self.consolidator(
                repair_network_drivers=False, merge_duplicates=True, delete_merged_platforms=True
            ).run()

        self.assertTrue(ORMPlatform.objects.filter(pk=loser.pk).exists())
        loser_plan = next(plan for plan in plans if plan.platform.pk == loser.pk)
        self.assertIn("Lifecycle", loser_plan.refusal_reason)

    def test_dry_run_changes_nothing(self):
        """Snapshot every relevant table before and after."""
        survivor, loser = self._duplicate_pair()
        device = self.make_device("router-1", loser)
        version = SoftwareVersion.objects.create(platform=loser, version="17.3.1", status=self.active)

        before = {
            "platforms": set(ORMPlatform.objects.values_list("pk", "name", "network_driver")),
            "device_platform": device.platform_id,
            "version_platform": version.platform_id,
        }

        with self.consolidated_mode():
            plans = self.consolidator(dry_run=True, merge_duplicates=True, delete_merged_platforms=True).run()

        device.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(set(ORMPlatform.objects.values_list("pk", "name", "network_driver")), before["platforms"])
        self.assertEqual(device.platform_id, before["device_platform"])
        self.assertEqual(version.platform_id, before["version_platform"])
        loser_plan = next(plan for plan in plans if plan.platform.pk == loser.pk)
        self.assertIn(ACTION_MERGE_INTO, loser_plan.actions)
        self.assertEqual(loser_plan.survivor_name, survivor.name)


class TestScopeAndReporting(ConsolidationTestCase):
    """Scope resolution and the CSV deliverable."""

    def test_librenms_scope_includes_synced_devices_platforms(self):
        """A Platform attached to a LibreNMS-owned Device is in scope."""
        platform = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")
        device = self.make_device("router-1", platform)
        device.custom_field_data["system_of_record"] = "LibreNMS"
        device.validated_save()

        self.assertIn(platform, list(resolve_scope()))

    def test_librenms_scope_excludes_other_owners_platforms(self):
        """A Platform used only by devices this integration does not own is out of scope."""
        platform = ORMPlatform.objects.create(name="hand-made", network_driver="")
        self.make_device("router-1", platform)

        self.assertNotIn(platform, list(resolve_scope()))

    def test_librenms_scope_includes_orphaned_fqcn_platforms(self):
        """An FQCN-named Platform with no devices was created by a previous sync."""
        platform = ORMPlatform.objects.create(name="cisco.nxos.nxos", network_driver="cisco.nxos.nxos")

        self.assertIn(platform, list(resolve_scope()))

    def test_selected_scope_limits_to_given_platforms(self):
        """Explicit selection never reaches outside itself."""
        chosen = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")
        other = ORMPlatform.objects.create(name="cisco.nxos.nxos", network_driver="cisco.nxos.nxos")

        in_scope = list(resolve_scope(SCOPE_SELECTED, [chosen]))

        self.assertEqual(in_scope, [chosen])
        other.refresh_from_db()
        self.assertEqual(other.network_driver, "cisco.nxos.nxos")

    def test_out_of_scope_platforms_are_untouched(self):
        """The repair phase respects the scope."""
        chosen = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")
        other = ORMPlatform.objects.create(name="cisco.nxos.nxos", network_driver="cisco.nxos.nxos")

        PlatformConsolidator(logger=self.logger, dry_run=False, scope=SCOPE_SELECTED, platforms=[chosen]).run()

        chosen.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(chosen.network_driver, "cisco_ios")
        self.assertEqual(other.network_driver, "cisco.nxos.nxos")

    def test_csv_lists_every_in_scope_platform(self):
        """In a dry run the CSV is the deliverable, so it must describe the whole landscape."""
        ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")
        ORMPlatform.objects.create(name="already_fine", network_driver="cisco_nxos")

        consolidator = self.consolidator(dry_run=True)
        consolidator.run()
        csv_text = consolidator.as_csv()

        self.assertIn("name,network_driver,intended_driver", csv_text)
        self.assertIn("cisco.ios.ios", csv_text)
        self.assertIn("already_fine", csv_text)
        self.assertIn(ACTION_REPAIR_DRIVER, csv_text)

    def test_csv_reports_counts_and_refusals(self):
        """Object counts and refusal reasons both reach the CSV."""
        survivor = ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios", manufacturer=self.fortinet)
        loser = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios", manufacturer=self.cisco)
        self.make_device("router-1", loser)

        with self.consolidated_mode():
            consolidator = self.consolidator(repair_network_drivers=False, merge_duplicates=True)
            plans = consolidator.run()

        csv_text = build_csv(plans, CSV_COLUMNS)
        self.assertIn("Manufacturer", csv_text)
        loser_plan = next(plan for plan in plans if plan.platform.pk == loser.pk)
        self.assertEqual(loser_plan.devices, 1)
        self.assertTrue(ORMPlatform.objects.filter(pk=survivor.pk).exists())

    def test_rename_action_is_recorded(self):
        """The rename phase reports its target name."""
        ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")

        with self.consolidated_mode():
            plans = self.consolidator(dry_run=True, repair_network_drivers=False, rename_legacy_platforms=True).run()

        self.assertIn(ACTION_RENAME, plans[0].actions)
        self.assertEqual(plans[0].target_name, "cisco_ios")


class TestConsolidationJobRegistration(TestCase):
    """The job must be registered, but must not appear on the SSoT dashboard."""

    databases = ("default", "job_logs")

    def test_job_is_registered_with_the_integration(self):
        """It ships alongside the two sync jobs."""
        self.assertIn(LibrenmsPlatformConsolidation, librenms_jobs)

    def test_job_is_not_a_data_source_or_target(self):
        """It remediates Nautobot data in place, so get_data_jobs() must not pick it up."""
        self.assertFalse(issubclass(LibrenmsPlatformConsolidation, (DataSource, DataTarget)))

    def test_dry_run_is_a_plain_boolean_var_defaulting_to_true(self):
        """DryRunVar forces default=False, so an API or scheduled run would execute destructively."""
        dry_run = LibrenmsPlatformConsolidation.dry_run
        self.assertNotIsInstance(dry_run, DryRunVar)
        self.assertTrue(dry_run.field_attrs["initial"])


class TestManufacturerRepair(ConsolidationTestCase):
    """Phase 4: repair Manufacturers the old resolution named after the device OS."""

    def test_rename_map_is_narrow_and_unambiguous(self):
        """It can only match names the buggy resolution could have produced."""
        renames = legacy_manufacturer_renames()

        self.assertEqual(renames["airos"], "Ubiquiti")
        self.assertEqual(renames["fortios"], "Fortinet")
        self.assertEqual(renames["routeros"], "Mikrotik")
        # Real vendor names are never candidates.
        for legitimate in ["Cisco", "Ubiquiti", "Fortinet", "Juniper", "Mikrotik"]:
            self.assertNotIn(legitimate, renames)
        # The 7 OS values that round-tripped correctly produced no wrong name.
        for correct in ["ios", "iosxe", "nxos", "junos", "iosxr", "arista_eos", "procera"]:
            self.assertNotIn(correct, renames)

    def test_renames_in_place_when_vendor_name_is_free(self):
        """Preferred path: keeps the primary key, so no DeviceType or Device moves."""
        wrong = Manufacturer.objects.create(name="airos")
        device_type = DeviceType.objects.create(model="NanoStation", manufacturer=wrong)

        self.consolidator(repair_network_drivers=False, repair_manufacturers=True).run()

        wrong.refresh_from_db()
        self.assertEqual(wrong.name, "Ubiquiti")
        device_type.refresh_from_db()
        self.assertEqual(device_type.manufacturer_id, wrong.pk)
        self.assertEqual(Manufacturer.objects.filter(name__in=["airos", "Ubiquiti"]).count(), 1)

    def test_merges_when_vendor_name_is_taken(self):
        """After a post-fix sync both rows exist, so the wrong one is merged away."""
        correct = Manufacturer.objects.create(name="Ubiquiti")
        wrong = Manufacturer.objects.create(name="airos")
        device_type = DeviceType.objects.create(model="NanoStation", manufacturer=wrong)
        platform = ORMPlatform.objects.create(name="airos", network_driver="", manufacturer=wrong)

        self.consolidator(repair_network_drivers=False, repair_manufacturers=True).run()

        device_type.refresh_from_db()
        platform.refresh_from_db()
        self.assertEqual(device_type.manufacturer_id, correct.pk)
        self.assertEqual(platform.manufacturer_id, correct.pk)
        self.assertFalse(Manufacturer.objects.filter(name="airos").exists())

    def test_refuses_device_type_collision_by_default(self):
        """(manufacturer, model) is unique, and merging moves real Devices between DeviceTypes."""
        correct = Manufacturer.objects.create(name="Ubiquiti")
        wrong = Manufacturer.objects.create(name="airos")
        DeviceType.objects.create(model="NanoStation", manufacturer=correct)
        loser_type = DeviceType.objects.create(model="NanoStation", manufacturer=wrong)

        consolidator = self.consolidator(repair_network_drivers=False, repair_manufacturers=True)
        consolidator.run()

        loser_type.refresh_from_db()
        self.assertEqual(loser_type.manufacturer_id, wrong.pk)
        self.assertTrue(Manufacturer.objects.filter(name="airos").exists())
        plan = consolidator.ordered_manufacturer_plans()[0]
        self.assertIn("NanoStation", plan.refusal_reason)

    def test_merges_device_types_when_opted_in(self):
        """The explicit escape hatch: devices move onto the surviving DeviceType."""
        correct = Manufacturer.objects.create(name="Ubiquiti")
        wrong = Manufacturer.objects.create(name="airos")
        survivor_type = DeviceType.objects.create(model="NanoStation", manufacturer=correct)
        loser_type = DeviceType.objects.create(model="NanoStation", manufacturer=wrong)
        device = self.make_device("ap-1", None, device_type=loser_type)

        self.consolidator(
            repair_network_drivers=False,
            repair_manufacturers=True,
            device_type_collisions=DEVICE_TYPE_MERGE,
        ).run()

        device.refresh_from_db()
        self.assertEqual(device.device_type_id, survivor_type.pk)
        self.assertFalse(DeviceType.objects.filter(pk=loser_type.pk).exists())
        self.assertFalse(Manufacturer.objects.filter(name="airos").exists())

    def test_leaves_correctly_named_manufacturers_alone(self):
        """A real vendor is never touched."""
        cisco_before = self.cisco.pk
        custom = Manufacturer.objects.create(name="Acme Networks")

        self.consolidator(repair_network_drivers=False, repair_manufacturers=True).run()

        self.cisco.refresh_from_db()
        custom.refresh_from_db()
        self.assertEqual(self.cisco.pk, cisco_before)
        self.assertEqual(self.cisco.name, "Cisco")
        self.assertEqual(custom.name, "Acme Networks")

    def test_phase_is_off_by_default(self):
        """Nothing happens unless the operator opts in."""
        wrong = Manufacturer.objects.create(name="airos")

        self.consolidator(repair_network_drivers=False).run()

        wrong.refresh_from_db()
        self.assertEqual(wrong.name, "airos")

    def test_runs_in_legacy_mode(self):
        """A Manufacturer named after the OS is wrong regardless of the naming mode."""
        wrong = Manufacturer.objects.create(name="airos")

        with self.consolidated_mode(False):
            self.consolidator(repair_network_drivers=False, repair_manufacturers=True).run()

        wrong.refresh_from_db()
        self.assertEqual(wrong.name, "Ubiquiti")

    def test_merges_into_a_vendor_that_already_exists(self):
        """`Fortinet` is already present, so `fortios` is merged away rather than renamed."""
        wrong = Manufacturer.objects.create(name="fortios")
        device_type = DeviceType.objects.create(model="FortiGate-60F", manufacturer=wrong)

        self.consolidator(repair_network_drivers=False, repair_manufacturers=True).run()

        self.assertFalse(Manufacturer.objects.filter(pk=wrong.pk).exists())
        device_type.refresh_from_db()
        self.assertEqual(device_type.manufacturer_id, self.fortinet.pk)

    def test_dry_run_changes_nothing(self):
        """Snapshot before and after."""
        wrong = Manufacturer.objects.create(name="airos")
        DeviceType.objects.create(model="NanoStation", manufacturer=wrong)

        consolidator = self.consolidator(dry_run=True, repair_network_drivers=False, repair_manufacturers=True)
        consolidator.run()

        wrong.refresh_from_db()
        self.assertEqual(wrong.name, "airos")
        plan = consolidator.ordered_manufacturer_plans()[0]
        self.assertEqual(plan.intended_name, "Ubiquiti")
        self.assertIn(ACTION_RENAME, plan.actions)
        self.assertIn("airos", consolidator.as_manufacturer_csv())

    def test_refuses_when_an_object_permission_references_the_name(self):
        """Same reasoning as the Platform rename phase."""
        wrong = Manufacturer.objects.create(name="airos")
        permission = ObjectPermission.objects.create(
            name="airos-only", actions=["view"], constraints={"manufacturer__name": "airos"}
        )
        permission.object_types.add(ContentType.objects.get_for_model(DeviceType))

        consolidator = self.consolidator(repair_network_drivers=False, repair_manufacturers=True)
        consolidator.run()

        wrong.refresh_from_db()
        self.assertEqual(wrong.name, "airos")
        self.assertIn("ObjectPermission", consolidator.ordered_manufacturer_plans()[0].refusal_reason)


class TestDiffReporting(ConsolidationTestCase):
    """The plan is rendered through SSoT's own diff format rather than a bespoke report."""

    def test_driver_repair_appears_as_an_attribute_change(self):
        """A repair reads as a before/after on network_driver."""
        ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")

        consolidator = self.consolidator(dry_run=True)
        consolidator.run()
        diff = consolidator.as_diff()

        entry = diff["dcim.platform"]["cisco.ios.ios"]
        self.assertEqual(entry["-"]["network_driver"], "cisco.ios.ios")
        self.assertEqual(entry["+"]["network_driver"], "cisco_ios")

    def test_blank_driver_is_labelled_rather_than_empty(self):
        """An empty before-value would otherwise render as nothing at all."""
        ORMPlatform.objects.create(name="cisco.nxos.nxos", network_driver="")

        consolidator = self.consolidator(dry_run=True)
        consolidator.run()

        entry = consolidator.as_diff()["dcim.platform"]["cisco.nxos.nxos"]
        self.assertEqual(entry["-"]["network_driver"], "(blank)")

    def test_manufacturer_rename_appears_under_its_own_record_type(self):
        """Manufacturers get their own section, like a second DiffSync model would."""
        Manufacturer.objects.create(name="airos")

        consolidator = self.consolidator(dry_run=True, repair_network_drivers=False, repair_manufacturers=True)
        consolidator.run()

        entry = consolidator.as_diff()["dcim.manufacturer"]["airos"]
        self.assertEqual(entry["-"]["name"], "airos")
        self.assertEqual(entry["+"]["name"], "Ubiquiti")

    def test_refusals_carry_their_reason(self):
        """A refusal is reported rather than silently omitted."""
        ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios")
        ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")

        with self.consolidated_mode():
            consolidator = self.consolidator(dry_run=True, repair_network_drivers=False, rename_legacy_platforms=True)
            consolidator.run()

        entry = consolidator.as_diff()["dcim.platform"]["cisco.ios.ios"]
        self.assertIn("already used", entry["refused"]["reason"])

    def test_unchanged_platforms_are_omitted(self):
        """Only rows with a planned action reach the diff."""
        ORMPlatform.objects.create(name="already_fine", network_driver="cisco_nxos")

        consolidator = self.consolidator(dry_run=True)
        consolidator.run()

        self.assertEqual(consolidator.as_diff(), {})

    def test_summary_counts_changes_and_refusals(self):
        """`Sync.summary` drives the counts shown in SSoT Sync History."""
        ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco.ios.ios")
        ORMPlatform.objects.create(name="already_fine", network_driver="cisco_nxos")

        consolidator = self.consolidator(dry_run=True)
        consolidator.run()

        summary = consolidator.diff_summary()
        self.assertEqual(summary["update"], 1)
        self.assertEqual(summary["no-change"], 1)
        self.assertEqual(summary["skip"], 0)
