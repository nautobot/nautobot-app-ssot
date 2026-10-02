"""Platform consolidation for the LibreNMS integration.

Remediates Platforms created under legacy naming, where the Ansible FQCN was used as both the
name and the `network_driver` (where it resolves to no driver mappings).

Three phases, in the order they are safe to run:

1. Repair drivers -- set a correct `network_driver` on FQCN-named rows. Safe in either mode.
2. Rename legacy platforms -- `cisco.ios.ios` to `cisco_ios`, preserving the primary key.
3. Merge duplicates -- collapse rows sharing a `network_driver` onto one survivor.

Phases 2 and 3 require consolidated mode; in legacy mode the sync looks Platforms up by FQCN
name and would re-create the row.

Callable without a Job instance so it is directly unit testable: the caller supplies a logger
and decides whether to write.
"""

import os
from dataclasses import dataclass, field

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from nautobot.dcim.models import Controller as ORMController
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import Platform as ORMPlatform
from nautobot.dcim.models import SoftwareImageFile as ORMSoftwareImageFile
from nautobot.dcim.models import SoftwareVersion as ORMSoftwareVersion
from nautobot.extras.models import ConfigContext, Note, RelationshipAssociation
from nautobot.virtualization.models import VirtualMachine as ORMVirtualMachine
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER

from nautobot_ssot.integrations.librenms.consolidation_utils import (
    ACTION_DELETE,
    ACTION_MERGE_INTO,
    ACTION_MERGE_SURVIVOR,
    ACTION_NONE,
    ACTION_RENAME,
    ACTION_REPAIR_DRIVER,
    BULK_UPDATE_THRESHOLD,
    build_csv,
    build_diff_dict,
    build_markdown_table,
    name_references,
    permission_references,
)
from nautobot_ssot.integrations.librenms.constants import PLUGIN_CFG
from nautobot_ssot.integrations.librenms.manufacturer_consolidation import (
    DEVICE_TYPE_MERGE,
    DEVICE_TYPE_REFUSE,
    MANUFACTURER_CSV_COLUMNS,
    ManufacturerConsolidatorMixin,
    ManufacturerPlan,
    intended_manufacturer_name,
    legacy_manufacturer_name,
    legacy_manufacturer_renames,
    manufacturer_reference_counts,
)

# Scope choices.
SCOPE_LIBRENMS = "librenms"
SCOPE_SELECTED = "selected"

# How to resolve a SoftwareVersion that already exists under the survivor.
COLLISION_REFUSE = "refuse"
COLLISION_MERGE = "merge"

# How to resolve a Platform whose Manufacturer contradicts the survivor's.
MANUFACTURER_SKIP = "skip"
MANUFACTURER_CLEAR = "clear"

CSV_COLUMNS = [
    "name",
    "network_driver",
    "intended_driver",
    "devices",
    "virtual_machines",
    "controllers",
    "software_versions",
    "planned_action",
    "refusal_reason",
    "references",
]

# Re-exported so callers and tests have one import site for the whole consolidation surface.
__all__ = [
    "ACTION_DELETE",
    "ACTION_MERGE_INTO",
    "ACTION_MERGE_SURVIVOR",
    "ACTION_NONE",
    "ACTION_RENAME",
    "ACTION_REPAIR_DRIVER",
    "COLLISION_MERGE",
    "COLLISION_REFUSE",
    "CSV_COLUMNS",
    "DEVICE_TYPE_MERGE",
    "DEVICE_TYPE_REFUSE",
    "MANUFACTURER_CLEAR",
    "MANUFACTURER_CSV_COLUMNS",
    "MANUFACTURER_SKIP",
    "SCOPE_LIBRENMS",
    "SCOPE_SELECTED",
    "ManufacturerPlan",
    "PlatformConsolidator",
    "PlatformPlan",
    "build_csv",
    "build_markdown_table",
    "get_software_lcm_model",
    "intended_driver_for",
    "intended_manufacturer_name",
    "legacy_manufacturer_name",
    "legacy_manufacturer_renames",
    "manufacturer_reference_counts",
    "needs_driver_repair",
    "resolve_scope",
]


@dataclass
class PlatformPlan:  # pylint: disable=too-many-instance-attributes
    """What is planned for one Platform, and why."""

    platform: object
    name: str
    network_driver: str
    intended_driver: str = ""
    devices: int = 0
    virtual_machines: int = 0
    controllers: int = 0
    software_versions: int = 0
    actions: list = field(default_factory=list)
    target_name: str = ""
    survivor_name: str = ""
    refusal_reason: str = ""
    references: list = field(default_factory=list)

    @property
    def planned_action(self) -> str:
        """Render every planned action as one CSV cell."""
        return "; ".join(self.actions) if self.actions else ACTION_NONE

    def as_csv_row(self) -> dict:
        """Flatten to a CSV row."""
        return {
            "name": self.name,
            "network_driver": self.network_driver,
            "intended_driver": self.intended_driver,
            "devices": self.devices,
            "virtual_machines": self.virtual_machines,
            "controllers": self.controllers,
            "software_versions": self.software_versions,
            "planned_action": self.planned_action,
            "refusal_reason": self.refusal_reason,
            "references": "; ".join(self.references),
        }


def get_software_lcm_model():
    """Optional Device Lifecycle Management SoftwareLCM model, or None."""
    # SoftwareLCM.device_platform is a second CASCADE FK onto Platform, so deleting a Platform
    # destroys lifecycle rows too. Optional dependency, hence the lookup over an import.
    try:
        return apps.get_model("nautobot_device_lifecycle_mgmt.SoftwareLCM")
    except LookupError:
        return None


def system_of_record() -> str:
    """System of Record value stamped on objects this integration manages."""
    return os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")


def consolidated_platforms_enabled() -> bool:
    """Whether driver-named Platforms are opted in."""
    return bool(PLUGIN_CFG.get("librenms_consolidated_platforms", False))


def is_ansible_fqcn(name: str) -> bool:
    """Whether this name is an Ansible FQCN netutils recognizes."""
    return name in ANSIBLE_LIB_MAPPER


def intended_driver_for(platform) -> str:
    """Driver an FQCN-named Platform should carry, else "" (don't guess)."""
    # Narrow on purpose: only FQCN names qualify, which keeps repair off dna_center and
    # device42 rows (FQCN name + correct driver) and off hand-named ones like "Cisco IOS".
    if not is_ansible_fqcn(platform.name):
        return ""
    return ANSIBLE_LIB_MAPPER[platform.name]


def needs_driver_repair(platform) -> bool:
    """Whether `network_driver` is the legacy FQCN or missing."""
    intended = intended_driver_for(platform)
    if not intended:
        return False
    current = (platform.network_driver or "").strip()
    if current == intended:
        return False
    # Only claim a row nobody else has staked a real driver on.
    return not current or current == platform.name


def resolve_scope(scope: str = SCOPE_LIBRENMS, platforms=None):
    """Platforms this run may touch.

    Default scope is LibreNMS-synced: Platforms on Devices this integration owns, plus
    FQCN-named Platforms with no Devices (orphaned by a previous sync).

    Args:
        scope (str): SCOPE_LIBRENMS or SCOPE_SELECTED.
        platforms (iterable, optional): Explicit Platforms, required for SCOPE_SELECTED.

    Returns:
        QuerySet: In-scope Platforms.
    """
    if scope == SCOPE_SELECTED:
        if not platforms:
            return ORMPlatform.objects.none()
        return ORMPlatform.objects.filter(pk__in=[platform.pk for platform in platforms])

    sor_devices = ORMDevice.objects.filter(
        platform__isnull=False,
        _custom_field_data__system_of_record=system_of_record(),
    ).values_list("platform_id", flat=True)

    orphan_fqcn_names = [
        platform.name for platform in ORMPlatform.objects.filter(devices__isnull=True) if is_ansible_fqcn(platform.name)
    ]

    return ORMPlatform.objects.filter(Q(pk__in=list(sor_devices)) | Q(name__in=orphan_fqcn_names)).distinct()


def _object_counts(platform) -> dict:
    """Count what would move if this Platform were merged away."""
    return {
        "devices": ORMDevice.objects.filter(platform=platform).count(),
        "virtual_machines": ORMVirtualMachine.objects.filter(platform=platform).count(),
        "controllers": ORMController.objects.filter(platform=platform).count(),
        "software_versions": ORMSoftwareVersion.objects.filter(platform=platform).count(),
    }


def _new_plan(platform) -> PlatformPlan:
    """Plan row pre-populated with current state and object counts."""
    counts = _object_counts(platform)
    return PlatformPlan(
        platform=platform,
        name=platform.name,
        network_driver=(platform.network_driver or "").strip(),
        intended_driver=intended_driver_for(platform),
        **counts,
    )


class PlatformConsolidator(ManufacturerConsolidatorMixin):  # pylint: disable=too-many-instance-attributes
    """Plans and optionally applies Platform consolidation.

    `plan()` for a read-only report, `run()` to plan and apply. Dry run is genuinely read-only
    rather than a rolled-back transaction: `validated_save()` fires webhooks, custom validators
    and job hooks that no rollback undoes.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        logger,
        dry_run: bool = True,
        scope: str = SCOPE_LIBRENMS,
        platforms=None,
        repair_network_drivers: bool = True,
        rename_legacy_platforms: bool = False,
        merge_duplicates: bool = False,
        software_version_collisions: str = COLLISION_REFUSE,
        manufacturer_conflicts: str = MANUFACTURER_SKIP,
        delete_merged_platforms: bool = False,
        update_dynamic_group_filters: bool = False,
        repair_manufacturers: bool = False,
        device_type_collisions: str = DEVICE_TYPE_REFUSE,
    ):
        """Store the run's options."""
        self.logger = logger
        self.dry_run = dry_run
        self.scope = scope
        self.selected_platforms = platforms
        self.repair_network_drivers = repair_network_drivers
        self.rename_legacy_platforms = rename_legacy_platforms
        self.merge_duplicates = merge_duplicates
        self.software_version_collisions = software_version_collisions
        self.manufacturer_conflicts = manufacturer_conflicts
        self.delete_merged_platforms = delete_merged_platforms
        self.update_dynamic_group_filters = update_dynamic_group_filters
        self.repair_manufacturers = repair_manufacturers
        self.device_type_collisions = device_type_collisions

        self.plans = {}
        self.manufacturer_plans = {}
        self.counts = {
            "drivers_repaired": 0,
            "platforms_renamed": 0,
            "platforms_merged": 0,
            "platforms_deleted": 0,
            "manufacturers_renamed": 0,
            "manufacturers_merged": 0,
            "device_types_merged": 0,
            "objects_moved": 0,
            "refusals": 0,
        }

    # -- plumbing --------------------------------------------------------------------------

    def _log(self, level: str, message: str, obj=None):
        """Log, attaching the object so Nautobot links it in the job log."""
        if self.logger is None:
            return
        extra = {"object": obj} if obj is not None else {}
        getattr(self.logger, level)(message, extra=extra)

    def _refuse(self, plan: PlatformPlan, reason: str):
        """Record a refusal with its remediation."""
        plan.refusal_reason = reason
        self.counts["refusals"] += 1
        self._log("warning", f'Refusing to act on Platform "{plan.name}": {reason}', plan.platform)

    def _plan_for(self, platform) -> PlatformPlan:
        """This Platform's plan row, created on first touch."""
        if platform.pk not in self.plans:
            self.plans[platform.pk] = _new_plan(platform)
        return self.plans[platform.pk]

    def _requires_consolidated_mode(self, phase: str) -> bool:
        """Guard phases that only make sense once the setting is on."""
        if consolidated_platforms_enabled():
            return True
        self._log(
            "error",
            f"Skipping the {phase} phase because librenms_consolidated_platforms is False. In legacy "
            "mode the sync looks Platforms up by their FQCN name, so a renamed or merged Platform "
            "would simply be re-created on the next run. Enable the setting first.",
        )
        self.counts["refusals"] += 1
        return False

    # -- phase 1: repair drivers -----------------------------------------------------------

    def repair_drivers(self, in_scope) -> list:
        """Set a correct `network_driver` on FQCN-named Platforms."""
        repaired = []
        for platform in in_scope:
            plan = self._plan_for(platform)
            if not needs_driver_repair(platform):
                continue
            plan.actions.append(ACTION_REPAIR_DRIVER)
            repaired.append(platform)
            if self.dry_run:
                self._log(
                    "info",
                    f'Would set network driver "{plan.intended_driver}" on Platform "{platform.name}" '
                    f'(currently {platform.network_driver or "blank"!r}).',
                    platform,
                )
                continue
            with transaction.atomic():
                platform.network_driver = plan.intended_driver
                try:
                    platform.validated_save()
                except ValidationError as err:
                    self._refuse(plan, f"network driver failed validation: {err}")
                    continue
            self.counts["drivers_repaired"] += 1
            self._log(
                "success",
                f'Set network driver "{plan.intended_driver}" on Platform "{platform.name}".',
                platform,
            )
        return repaired

    # -- phase 2: rename -------------------------------------------------------------------

    def rename_platforms(self, in_scope) -> list:
        """Rename FQCN-named Platforms onto their driver name.

        Preserves the primary key, so FKs, ConfigContext assignments, notes, metadata,
        relationships and PK-based dynamic groups all survive. Prefer over a merge.
        """
        renamed = []
        for platform in in_scope:
            plan = self._plan_for(platform)
            target = intended_driver_for(platform)
            if not target or target == platform.name:
                continue
            plan.target_name = target

            taken = ORMPlatform.objects.filter(name__iexact=target).exclude(pk=platform.pk).first()
            if taken is not None:
                self._refuse(
                    plan,
                    f'the target name "{target}" is already used by another Platform. Use the merge '
                    "phase to collapse them instead.",
                )
                continue

            references = name_references(platform.name)
            plan.references = references
            permission_hits = permission_references(references)
            if permission_hits:
                self._refuse(
                    plan,
                    f"an ObjectPermission constrains on this name ({', '.join(permission_hits)}). "
                    "Rewriting a permission could widen or narrow access, so update it by hand first.",
                )
                continue
            for reference in references:
                self._log(
                    "warning",
                    f'"{platform.name}" is referenced by name in {reference}. Renaming will not update '
                    "it automatically.",
                    platform,
                )

            plan.actions.append(ACTION_RENAME)
            renamed.append(platform)
            if self.dry_run:
                self._log("info", f'Would rename Platform "{platform.name}" to "{target}".', platform)
                continue

            with transaction.atomic():
                old_name = platform.name
                platform.name = target
                if not (platform.network_driver or "").strip():
                    platform.network_driver = target
                try:
                    platform.validated_save()
                except ValidationError as err:
                    self._refuse(plan, f"rename failed validation: {err}")
                    continue
                if self.update_dynamic_group_filters:
                    self._rewrite_dynamic_group_filters(old_name, target)
            self.counts["platforms_renamed"] += 1
            self._log("success", f'Renamed Platform "{old_name}" to "{target}".', platform)
        return renamed

    def _rewrite_dynamic_group_filters(self, old_name: str, new_name: str):
        """Replace a Platform name inside DynamicGroup filters. Opt-in only."""
        # DeviceFilterSet.platform stores names, so a stale filter silently stops matching.
        # Exact entries only, never substrings.
        dynamic_group_model = apps.get_model("extras.DynamicGroup")
        for group in dynamic_group_model.objects.all():
            group_filter = group.filter or {}
            changed = False
            for key, value in list(group_filter.items()):
                if isinstance(value, list) and old_name in value:
                    group_filter[key] = [new_name if entry == old_name else entry for entry in value]
                    changed = True
                elif value == old_name:
                    group_filter[key] = new_name
                    changed = True
            if changed:
                group.filter = group_filter
                group.validated_save()
                self._log("success", f'Updated DynamicGroup "{group.name}" filter to use "{new_name}".', group)

    # -- phase 3: merge --------------------------------------------------------------------

    def merge_duplicate_platforms(self, in_scope) -> list:
        """Collapse Platforms that share a `network_driver` onto one survivor."""
        groups = {}
        for platform in in_scope:
            driver = (platform.network_driver or "").strip()
            if not driver:
                continue
            groups.setdefault(driver.lower(), []).append(platform)

        merged = []
        for driver, platforms in sorted(groups.items()):
            if len(platforms) < 2:
                continue
            survivor = self._pick_survivor(platforms, driver)
            losers = [platform for platform in platforms if platform.pk != survivor.pk]
            survivor_plan = self._plan_for(survivor)
            survivor_plan.actions.append(ACTION_MERGE_SURVIVOR)
            self._log(
                "info",
                f'Network driver "{driver}" is shared by {len(platforms)} Platforms. ' f'Survivor: "{survivor.name}".',
                survivor,
            )
            for loser in losers:
                if self._merge_one(loser, survivor):
                    merged.append(loser)
        return merged

    def _pick_survivor(self, platforms, driver: str):
        """Which Platform of a driver group to keep."""

        # Exact name, then most objects, then oldest; name breaks ties for reproducibility.
        def rank(platform):
            counts = _object_counts(platform)
            assigned = counts["devices"] + counts["virtual_machines"] + counts["controllers"]
            return (platform.name.lower() != driver, -assigned, platform.created, platform.name)

        return sorted(platforms, key=rank)[0]

    def _merge_one(self, loser, survivor) -> bool:  # pylint: disable=too-many-return-statements
        """Move everything off `loser` onto `survivor`. Returns whether the merge happened."""
        plan = self._plan_for(loser)
        plan.survivor_name = survivor.name

        # All refusals evaluated before the first write.
        conflicting = self._manufacturer_conflicts(loser, survivor)
        if conflicting and self.manufacturer_conflicts != MANUFACTURER_CLEAR:
            self._refuse(
                plan,
                f'its Devices would fail validation against survivor "{survivor.name}" whose '
                f'Manufacturer is "{survivor.manufacturer}". Re-run with manufacturer_conflicts '
                '"clear" to clear the survivor\'s Manufacturer instead.',
            )
            return False

        collisions = self._software_version_collisions(loser, survivor)
        if collisions and self.software_version_collisions != COLLISION_MERGE:
            versions = ", ".join(sorted(collisions))
            self._refuse(
                plan,
                f'these SoftwareVersions already exist under survivor "{survivor.name}": {versions}. '
                'Re-run with software_version_collisions "merge" to fold them together.',
            )
            return False

        plan.actions.append(ACTION_MERGE_INTO)
        if self.dry_run:
            self._log(
                "info",
                f'Would merge Platform "{loser.name}" into "{survivor.name}" '
                f"({plan.devices} devices, {plan.virtual_machines} VMs, {plan.controllers} controllers, "
                f"{plan.software_versions} software versions).",
                loser,
            )
            self._plan_delete(plan, loser, dry_run=True)
            return True

        with transaction.atomic():
            if conflicting and self.manufacturer_conflicts == MANUFACTURER_CLEAR:
                survivor.manufacturer = None
                survivor.validated_save()
                self._log("warning", f'Cleared the Manufacturer on Platform "{survivor.name}".', survivor)

            # SoftwareVersion first: required CASCADE FK, unique on (platform, version) --
            # the most fragile, and destroyed outright if the loser is deleted.
            self._move_software_versions(loser, survivor)
            moved = self._move_platform_objects(loser, survivor)
            self._move_config_contexts(loser, survivor)
            self._move_generic_associations(loser, survivor)
            self._merge_custom_fields(loser, survivor)
            self.counts["objects_moved"] += moved

        self.counts["platforms_merged"] += 1
        self._log("success", f'Merged Platform "{loser.name}" into "{survivor.name}".', survivor)
        self._plan_delete(plan, loser, dry_run=False)
        return True

    def _manufacturer_conflicts(self, loser, survivor) -> bool:
        """Whether moving the loser's Devices would trip Device.clean()'s manufacturer check."""
        if survivor.manufacturer_id is None:
            return False
        return (
            ORMDevice.objects.filter(platform=loser)
            .exclude(device_type__manufacturer_id=survivor.manufacturer_id)
            .exists()
        )

    def _software_version_collisions(self, loser, survivor) -> set:
        """Versions under both Platforms, which cannot simply be repointed."""
        loser_versions = set(ORMSoftwareVersion.objects.filter(platform=loser).values_list("version", flat=True))
        survivor_versions = set(ORMSoftwareVersion.objects.filter(platform=survivor).values_list("version", flat=True))
        return loser_versions & survivor_versions

    def _move_software_versions(self, loser, survivor):
        """Repoint the loser's SoftwareVersions, folding together any that collide."""
        for version in ORMSoftwareVersion.objects.filter(platform=loser):
            twin = ORMSoftwareVersion.objects.filter(platform=survivor, version=version.version).first()
            if twin is None:
                version.platform = survivor
                version.validated_save()
                self._log("info", f'Moved SoftwareVersion "{version.version}" to "{survivor.name}".', version)
                continue

            # Repoint references to the duplicate, then retire it.
            ORMDevice.objects.filter(software_version=version).update(software_version=twin)
            ORMVirtualMachine.objects.filter(software_version=version).update(software_version=twin)
            apps.get_model("dcim.InventoryItem").objects.filter(software_version=version).update(software_version=twin)
            self._merge_software_image_files(version, twin)
            version.delete()
            self._log(
                "warning",
                f'Folded duplicate SoftwareVersion "{version.version}" into the copy already under '
                f'"{survivor.name}".',
                twin,
            )

    def _merge_software_image_files(self, version, twin):
        """Move image files onto the surviving SoftwareVersion, keeping device type links."""
        # (image_file_name, software_version) is unique, so a colliding file has its device
        # types folded into the survivor before being dropped.
        for image in ORMSoftwareImageFile.objects.filter(software_version=version):
            existing = ORMSoftwareImageFile.objects.filter(
                software_version=twin, image_file_name=image.image_file_name
            ).first()
            if existing is None:
                image.software_version = twin
                image.validated_save()
                continue
            # DeviceType.software_image_files goes through DeviceTypeToSoftwareImageFile, whose
            # FK is PROTECTED -- detach before deleting or it raises.
            for device_type in list(image.device_types.all()):
                existing.device_types.add(device_type)
                image.device_types.remove(device_type)
            image.delete()

    def _move_platform_objects(self, loser, survivor) -> int:
        """Repoint Devices, VirtualMachines and Controllers onto the survivor."""
        moved = 0
        for model in (ORMDevice, ORMVirtualMachine, ORMController):
            queryset = model.objects.filter(platform=loser)
            total = queryset.count()
            if not total:
                continue
            if total > BULK_UPDATE_THRESHOLD:
                self._log(
                    "warning",
                    f"Moving {total} {model._meta.verbose_name_plural} with bulk_update; per-object "
                    "change records will not be written.",
                )
                for obj in queryset:
                    obj.platform = survivor
                queryset.model.objects.bulk_update(queryset, ["platform"])
                moved += total
                continue
            for obj in queryset:
                obj.platform = survivor
                try:
                    obj.validated_save()
                except ValidationError as err:
                    self._log("failure", f"Could not move {model._meta.verbose_name} {obj}: {err}", obj)
                    continue
                moved += 1
        return moved

    def _move_config_contexts(self, loser, survivor):
        """Move ConfigContext assignments."""
        # ConfigContext.platforms uses related_name="+", so filter() is the only access path.
        for config_context in ConfigContext.objects.filter(platforms=loser):
            config_context.platforms.add(survivor)
            config_context.platforms.remove(loser)
            self._log("info", f'Moved ConfigContext "{config_context.name}" to "{survivor.name}".', config_context)

    def _move_generic_associations(self, loser, survivor):
        """Repoint generic-relation rows, dropping any that would violate a unique constraint."""
        # Duplicates are detected up front, not by catching the save: an IntegrityError inside
        # transaction.atomic() poisons the transaction even when caught, aborting the merge.
        content_type = apps.get_model("contenttypes.ContentType").objects.get_for_model(ORMPlatform)

        # Notes have no GenericRelation, so they would otherwise be orphaned. Their unique
        # constraint includes `created`, so collisions aren't a practical concern.
        Note.objects.filter(assigned_object_type=content_type, assigned_object_id=loser.pk).update(
            assigned_object_id=survivor.pk
        )

        associations = [
            ("extras.ObjectMetadata", "assigned_object_type", "assigned_object_id"),
            ("extras.ContactAssociation", "associated_object_type", "associated_object_id"),
            ("extras.StaticGroupAssociation", "associated_object_type", "associated_object_id"),
        ]
        for label, type_field, id_field in associations:
            model = apps.get_model(label)
            manager = getattr(model, "all_objects", model.objects)
            for row in manager.filter(**{type_field: content_type, id_field: loser.pk}):
                if self._association_would_collide(model, manager, row, id_field, survivor.pk):
                    self._log(
                        "info",
                        f'Dropping duplicate {model._meta.verbose_name} during merge; "{survivor.name}" '
                        "already has an equivalent row.",
                        loser,
                    )
                    row.delete()
                    continue
                setattr(row, id_field, survivor.pk)
                row.save()

        for type_field, id_field in [("source_type", "source_id"), ("destination_type", "destination_id")]:
            for row in RelationshipAssociation.objects.filter(**{type_field: content_type, id_field: loser.pk}):
                if self._association_would_collide(
                    RelationshipAssociation, RelationshipAssociation.objects, row, id_field, survivor.pk
                ):
                    self._log(
                        "info",
                        f'Dropping duplicate RelationshipAssociation during merge; "{survivor.name}" '
                        "already has an equivalent row.",
                        loser,
                    )
                    row.delete()
                    continue
                setattr(row, id_field, survivor.pk)
                row.save()

    @staticmethod
    def _association_would_collide(model, manager, row, id_field, new_id) -> bool:
        """Whether repointing `row` at `new_id` would duplicate an existing row."""
        # Checks each unique_together tuple that includes the field being changed.
        for unique_fields in model._meta.unique_together:
            if id_field not in unique_fields:
                continue
            lookup = {}
            for name in unique_fields:
                lookup[name] = new_id if name == id_field else getattr(row, f"{name}_id", getattr(row, name, None))
            if manager.filter(**lookup).exclude(pk=row.pk).exists():
                return True
        return False

    def _merge_custom_fields(self, loser, survivor):
        """Copy only custom field keys blank on the survivor; log conflicts."""
        changed = False
        for key, value in (loser.custom_field_data or {}).items():
            if value in (None, ""):
                continue
            if survivor.custom_field_data.get(key) in (None, ""):
                survivor.custom_field_data[key] = value
                changed = True
            elif survivor.custom_field_data.get(key) != value:
                self._log(
                    "warning",
                    f'Leaving custom field "{key}" on "{survivor.name}" alone; "{loser.name}" '
                    f"disagrees ({value!r} vs {survivor.custom_field_data.get(key)!r}).",
                    survivor,
                )
        if changed:
            survivor.validated_save()

    def _plan_delete(self, plan: PlatformPlan, platform, dry_run: bool):
        """Delete an emptied Platform, refusing while anything would CASCADE off it."""
        if not self.delete_merged_platforms:
            return

        remaining_versions = ORMSoftwareVersion.objects.filter(platform=platform).count()
        if remaining_versions:
            self._refuse(
                plan,
                f"it still has {remaining_versions} SoftwareVersion(s). Deleting it would CASCADE and "
                "destroy that version history along with its image files.",
            )
            return

        software_lcm = get_software_lcm_model()
        if software_lcm is not None:
            remaining_lcm = software_lcm.objects.filter(device_platform=platform).count()
            if remaining_lcm:
                self._refuse(
                    plan,
                    f"it still has {remaining_lcm} Device Lifecycle Management Software record(s), which "
                    "would CASCADE and be destroyed.",
                )
                return

        for model, label in [
            (ORMDevice, "device"),
            (ORMVirtualMachine, "virtual machine"),
            (ORMController, "controller"),
        ]:
            remaining = model.objects.filter(platform=platform).count()
            if remaining:
                self._refuse(plan, f"it still has {remaining} {label}(s) assigned.")
                return

        plan.actions.append(ACTION_DELETE)
        if dry_run:
            self._log("info", f'Would delete the emptied Platform "{platform.name}".', platform)
            return
        name = platform.name
        platform.delete()
        self.counts["platforms_deleted"] += 1
        self._log("success", f'Deleted the emptied Platform "{name}".')

    # -- entry points ----------------------------------------------------------------------

    def plan(self) -> list:
        """Report without writing anything."""
        was_dry_run = self.dry_run
        self.dry_run = True
        try:
            self._execute()
        finally:
            self.dry_run = was_dry_run
        return self.ordered_plans()

    def run(self) -> list:
        """Execute the selected phases, honoring `dry_run`."""
        self._execute()
        return self.ordered_plans()

    def _execute(self):
        """Run each selected phase over a freshly resolved scope."""
        self.plans = {}
        self.manufacturer_plans = {}
        self.counts = {key: 0 for key in self.counts}
        legacy_manufacturer_renames.cache_clear()
        in_scope = list(resolve_scope(self.scope, self.selected_platforms))
        self._log("info", f"Platform consolidation scope: {len(in_scope)} Platform(s).")
        if self.dry_run:
            self._log("info", "Dry run: no changes will be written.")

        # Row per in-scope platform so the CSV describes the whole landscape.
        for platform in in_scope:
            self._plan_for(platform)

        if self.repair_network_drivers:
            self.repair_drivers(in_scope)

        if self.rename_legacy_platforms and self._requires_consolidated_mode("rename"):
            # Re-read: repair may have changed the drivers we group on.
            self.rename_platforms(list(resolve_scope(self.scope, self.selected_platforms)))

        if self.merge_duplicates and self._requires_consolidated_mode("merge"):
            self.merge_duplicate_platforms(list(resolve_scope(self.scope, self.selected_platforms)))

        # Independent of the platform phases and of the naming mode: a Manufacturer named after
        # the OS is wrong either way.
        if self.repair_manufacturers:
            self.repair_manufacturer_names()

        for name, count in self.counts.items():
            if count:
                self._log("info", f"{name.replace('_', ' ').capitalize()}: {count}")

    def ordered_plans(self) -> list:
        """Platform plans sorted by name, so reports are reproducible."""
        return sorted(self.plans.values(), key=lambda plan: plan.name)

    def ordered_manufacturer_plans(self) -> list:
        """Manufacturer plans sorted by name."""
        return sorted(self.manufacturer_plans.values(), key=lambda plan: plan.name)

    def as_csv(self) -> str:
        """Platform plan as CSV. The deliverable in a dry run."""
        return build_csv(self.ordered_plans(), CSV_COLUMNS)

    def as_manufacturer_csv(self) -> str:
        """Manufacturer plan as CSV."""
        return build_csv(self.ordered_manufacturer_plans(), MANUFACTURER_CSV_COLUMNS)

    def as_diff(self) -> dict:
        """Plan in SSoT's diff format, for a `Sync` record's diff view."""
        return build_diff_dict(self.ordered_plans(), self.ordered_manufacturer_plans())

    def diff_summary(self) -> dict:
        """Counts in the shape `Sync.summary` expects."""
        changed = sum(1 for plan in self.plans.values() if plan.actions and not plan.refusal_reason)
        changed += sum(1 for plan in self.manufacturer_plans.values() if plan.actions and not plan.refusal_reason)
        total = len(self.plans) + len(self.manufacturer_plans)
        return {
            "create": 0,
            "update": changed,
            "delete": self.counts["platforms_deleted"],
            "no-change": total - changed,
            "skip": self.counts["refusals"],
        }

    def as_markdown(self) -> str:
        """Platform plan as a markdown table, for the job log."""
        return build_markdown_table(self.ordered_plans(), CSV_COLUMNS)

    def as_manufacturer_markdown(self) -> str:
        """Manufacturer plan as a markdown table, for the job log."""
        return build_markdown_table(self.ordered_manufacturer_plans(), MANUFACTURER_CSV_COLUMNS)
