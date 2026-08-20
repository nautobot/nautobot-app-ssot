"""Manufacturer consolidation for the LibreNMS integration.

Before the platform-handling fix, the Manufacturer was resolved by round-tripping the Platform name
back through the OS mappers, with that name as the fallback. Only the 7 OS values in
`LIBRENMS_LIB_MAPPER` round-tripped, so the other 210 produced a Manufacturer named after the OS
string -- `panos` rather than `Palo Alto`.

New devices now get the correct vendor, but existing rows are left alone until an operator opts in
to this phase. Renaming is preferred over merging: it keeps the primary key, so no DeviceType or
Device moves at all.
"""

from dataclasses import dataclass, field
from functools import lru_cache

from django.core.exceptions import ValidationError
from django.db import transaction
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType as ORMDeviceType
from nautobot.dcim.models import Manufacturer as ORMManufacturer
from nautobot.dcim.models import Platform as ORMPlatform
from nautobot.extras.models import ConfigContext
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER, ANSIBLE_LIB_MAPPER_REVERSE

from nautobot_ssot.integrations.librenms.consolidation_utils import (
    ACTION_DELETE,
    ACTION_MERGE_INTO,
    ACTION_NONE,
    ACTION_RENAME,
    get_model_or_none,
    name_references,
    permission_references,
)
from nautobot_ssot.integrations.librenms.constants import (
    LIBRENMS_LIB_MAPPER,
    LIBRENMS_LIB_MAPPER_REVERSE,
    os_manufacturer_map,
)

# How to resolve a DeviceType whose (manufacturer, model) already exists under the survivor.
DEVICE_TYPE_REFUSE = "refuse"
DEVICE_TYPE_MERGE = "merge"

MANUFACTURER_CSV_COLUMNS = [
    "name",
    "intended_name",
    "device_types",
    "platforms",
    "inventory_items",
    "module_types",
    "planned_action",
    "refusal_reason",
    "references",
]


@dataclass
class ManufacturerPlan:  # pylint: disable=too-many-instance-attributes
    """What is planned for one Manufacturer, and why."""

    manufacturer: object
    name: str
    intended_name: str = ""
    device_types: int = 0
    platforms: int = 0
    inventory_items: int = 0
    module_types: int = 0
    actions: list = field(default_factory=list)
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
            "intended_name": self.intended_name,
            "device_types": self.device_types,
            "platforms": self.platforms,
            "inventory_items": self.inventory_items,
            "module_types": self.module_types,
            "planned_action": self.planned_action,
            "refusal_reason": self.refusal_reason,
            "references": "; ".join(self.references),
        }


def legacy_manufacturer_name(librenms_os: str) -> str:
    """Manufacturer name the pre-fix code would have produced for this LibreNMS `os`."""
    # Replays the old expression exactly: the Platform name was round-tripped back through the
    # OS mappers, with that name itself as the fallback.
    driver = LIBRENMS_LIB_MAPPER.get(librenms_os, librenms_os)
    platform_name = ANSIBLE_LIB_MAPPER_REVERSE.get(driver, driver)
    return os_manufacturer_map.get(
        LIBRENMS_LIB_MAPPER_REVERSE.get(ANSIBLE_LIB_MAPPER.get(platform_name, platform_name)),
        platform_name,
    )


@lru_cache(maxsize=1)
def legacy_manufacturer_renames() -> dict:
    """Map a mis-created Manufacturer name to the vendor it should have been.

    Built by replaying the old buggy resolution over `os_manufacturer_map`, so it can only ever
    match a name that resolution could actually have produced. Entries are dropped when two OS
    values disagree on the correct vendor, or when the wrong name is also a legitimate vendor
    name, so a real Manufacturer is never a candidate.
    """
    candidates = {}
    for librenms_os, correct in os_manufacturer_map.items():
        wrong = legacy_manufacturer_name(librenms_os)
        if wrong == correct:
            continue
        candidates.setdefault(wrong, set()).add(correct)

    legitimate = set(os_manufacturer_map.values())
    return {
        wrong: next(iter(correct))
        for wrong, correct in candidates.items()
        if len(correct) == 1 and wrong not in legitimate
    }


def intended_manufacturer_name(manufacturer) -> str:
    """Vendor this Manufacturer should be named, or "" when it looks correct already."""
    return legacy_manufacturer_renames().get(manufacturer.name, "")


def manufacturer_reference_counts(manufacturer) -> dict:
    """Count everything referencing this Manufacturer. All such FKs are PROTECT."""
    counts = {
        "device types": ORMDeviceType.objects.filter(manufacturer=manufacturer).count(),
        "platforms": ORMPlatform.objects.filter(manufacturer=manufacturer).count(),
    }
    for label, field_name, name in [
        ("dcim.InventoryItem", "manufacturer", "inventory items"),
        ("dcim.ModuleType", "manufacturer", "module types"),
        ("cloud.CloudAccount", "provider", "cloud accounts"),
        ("cloud.CloudResourceType", "provider", "cloud resource types"),
    ]:
        model = get_model_or_none(label)
        counts[name] = model.objects.filter(**{field_name: manufacturer}).count() if model else 0
    return counts


class ManufacturerConsolidatorMixin:
    """Manufacturer repair phase.

    Expects the host class to provide `dry_run`, `device_type_collisions`, `counts`,
    `manufacturer_plans`, and the `_log` helper.
    """

    def repair_manufacturer_names(self) -> list:
        """Rename or merge Manufacturers the old resolution named after the device OS.

        Scoped by the `legacy_manufacturer_renames()` name map rather than by the Platform scope,
        because the map can only match a name the buggy resolution could have produced. Renaming
        is preferred: it keeps the primary key, so no DeviceType or Device moves at all.
        """
        renames = legacy_manufacturer_renames()
        repaired = []
        for manufacturer in ORMManufacturer.objects.filter(name__in=list(renames)).order_by("name"):
            plan = self._manufacturer_plan_for(manufacturer)
            correct = renames[manufacturer.name]
            plan.intended_name = correct

            references = name_references(manufacturer.name)
            plan.references = references
            permission_hits = permission_references(references)
            if permission_hits:
                self._refuse_manufacturer(
                    plan,
                    f"an ObjectPermission constrains on this name ({', '.join(permission_hits)}). "
                    "Rewriting a permission could widen or narrow access, so update it by hand first.",
                )
                continue

            survivor = ORMManufacturer.objects.filter(name__iexact=correct).exclude(pk=manufacturer.pk).first()
            if survivor is None:
                if self._rename_manufacturer(plan, manufacturer, correct):
                    repaired.append(manufacturer)
            elif self._merge_manufacturer(plan, manufacturer, survivor):
                repaired.append(manufacturer)
        return repaired

    def _rename_manufacturer(self, plan: ManufacturerPlan, manufacturer, correct: str) -> bool:
        """Rename in place, preserving the primary key so nothing moves."""
        plan.actions.append(ACTION_RENAME)
        if self.dry_run:
            self._log("info", f'Would rename Manufacturer "{manufacturer.name}" to "{correct}".', manufacturer)
            return True
        old_name = manufacturer.name
        with transaction.atomic():
            manufacturer.name = correct
            try:
                manufacturer.validated_save()
            except ValidationError as err:
                self._refuse_manufacturer(plan, f"rename failed validation: {err}")
                return False
        self.counts["manufacturers_renamed"] += 1
        self._log("success", f'Renamed Manufacturer "{old_name}" to "{correct}".', manufacturer)
        return True

    def _merge_manufacturer(self, plan: ManufacturerPlan, loser, survivor) -> bool:
        """Move everything off `loser` onto the correctly-named `survivor`."""
        colliding = self._colliding_device_types(loser, survivor)
        if colliding and self.device_type_collisions != DEVICE_TYPE_MERGE:
            models = ", ".join(sorted(colliding))
            self._refuse_manufacturer(
                plan,
                f'these device type models already exist under "{survivor.name}": {models}. Merging '
                "them moves real Devices between DeviceTypes, so re-run with device_type_collisions "
                '"merge" if that is what you want.',
            )
            return False

        plan.actions.append(ACTION_MERGE_INTO)
        if self.dry_run:
            self._log(
                "info",
                f'Would merge Manufacturer "{loser.name}" into "{survivor.name}" '
                f"({plan.device_types} device types, {plan.platforms} platforms, "
                f"{plan.inventory_items} inventory items, {plan.module_types} module types).",
                loser,
            )
            return True

        with transaction.atomic():
            self._move_device_types(loser, survivor)
            # Platform, InventoryItem, ModuleType and the cloud models are plain FKs with no
            # unique constraint involving the manufacturer, so a bulk update is safe.
            for label, field_name in [
                ("dcim.Platform", "manufacturer"),
                ("dcim.InventoryItem", "manufacturer"),
                ("dcim.ModuleType", "manufacturer"),
                ("cloud.CloudAccount", "provider"),
                ("cloud.CloudResourceType", "provider"),
            ]:
                model = get_model_or_none(label)
                if model is None:
                    continue
                moved = model.objects.filter(**{field_name: loser}).update(**{field_name: survivor})
                if moved:
                    self.counts["objects_moved"] += moved
                    self._log("info", f'Moved {moved} {model._meta.verbose_name_plural} to "{survivor.name}".')
            self._merge_manufacturer_custom_fields(loser, survivor)

        self.counts["manufacturers_merged"] += 1
        self._log("success", f'Merged Manufacturer "{loser.name}" into "{survivor.name}".', survivor)
        self._delete_emptied_manufacturer(plan, loser)
        return True

    def _colliding_device_types(self, loser, survivor) -> set:
        """Device type models present under both Manufacturers.

        `(manufacturer, model)` is unique, so these cannot simply be repointed.
        """
        loser_models = set(ORMDeviceType.objects.filter(manufacturer=loser).values_list("model", flat=True))
        survivor_models = set(ORMDeviceType.objects.filter(manufacturer=survivor).values_list("model", flat=True))
        return loser_models & survivor_models

    def _move_device_types(self, loser, survivor):
        """Repoint the loser's DeviceTypes, folding together any that collide."""
        for device_type in ORMDeviceType.objects.filter(manufacturer=loser):
            twin = ORMDeviceType.objects.filter(manufacturer=survivor, model=device_type.model).first()
            if twin is None:
                device_type.manufacturer = survivor
                try:
                    device_type.validated_save()
                except ValidationError as err:
                    self._log("failure", f"Could not move DeviceType {device_type}: {err}", device_type)
                    continue
                self.counts["objects_moved"] += 1
                self._log("info", f'Moved DeviceType "{device_type.model}" to "{survivor.name}".', device_type)
                continue
            self._fold_device_type(device_type, twin)

    def _fold_device_type(self, loser, twin):
        """Repoint everything off a duplicate DeviceType, then retire it if it is safe to."""
        for device in ORMDevice.objects.filter(device_type=loser):
            device.device_type = twin
            try:
                device.validated_save()
            except ValidationError as err:
                self._log("failure", f"Could not move device {device}: {err}", device)
                continue
            self.counts["objects_moved"] += 1

        # ConfigContext.device_types and the software-image links are M2Ms; move then detach.
        for config_context in ConfigContext.objects.filter(device_types=loser):
            config_context.device_types.add(twin)
            config_context.device_types.remove(loser)
        for image in list(loser.software_image_files.all()):
            twin.software_image_files.add(image)
            loser.software_image_files.remove(image)

        remaining = ORMDevice.objects.filter(device_type=loser).count()
        if remaining:
            self._log(
                "warning",
                f'Left DeviceType "{loser.model}" in place: {remaining} device(s) could not be moved.',
                loser,
            )
            return

        hardware_lcm = get_model_or_none("nautobot_device_lifecycle_mgmt.HardwareLCM")
        if hardware_lcm is not None and hardware_lcm.objects.filter(device_type=loser).exists():
            self._log(
                "warning",
                f'Left the emptied DeviceType "{loser.model}" in place: it has Device Lifecycle '
                "Management hardware notices, which would CASCADE and be destroyed.",
                loser,
            )
            return

        model_name = loser.model
        loser.delete()
        self.counts["device_types_merged"] += 1
        self._log("success", f'Folded duplicate DeviceType "{model_name}" into the survivor.', twin)

    def _merge_manufacturer_custom_fields(self, loser, survivor):
        """Copy only custom field keys blank on the survivor."""
        changed = False
        for key, value in (loser.custom_field_data or {}).items():
            if value in (None, ""):
                continue
            if survivor.custom_field_data.get(key) in (None, ""):
                survivor.custom_field_data[key] = value
                changed = True
        if changed:
            survivor.validated_save()

    def _delete_emptied_manufacturer(self, plan: ManufacturerPlan, manufacturer):
        """Delete the loser once nothing references it.

        Every foreign key onto Manufacturer is PROTECT, so an emptied row holds no data and
        leaving it behind would defeat the point of the phase.
        """
        remaining = manufacturer_reference_counts(manufacturer)
        if any(remaining.values()):
            held = ", ".join(f"{count} {name}" for name, count in remaining.items() if count)
            self._log(
                "warning",
                f'Left Manufacturer "{manufacturer.name}" in place: still referenced by {held}.',
                manufacturer,
            )
            return
        plan.actions.append(ACTION_DELETE)
        name = manufacturer.name
        manufacturer.delete()
        self._log("success", f'Deleted the emptied Manufacturer "{name}".')

    def _manufacturer_plan_for(self, manufacturer) -> ManufacturerPlan:
        """This Manufacturer's plan row, created on first touch."""
        if manufacturer.pk not in self.manufacturer_plans:
            counts = manufacturer_reference_counts(manufacturer)
            self.manufacturer_plans[manufacturer.pk] = ManufacturerPlan(
                manufacturer=manufacturer,
                name=manufacturer.name,
                device_types=counts["device types"],
                platforms=counts["platforms"],
                inventory_items=counts["inventory items"],
                module_types=counts["module types"],
            )
        return self.manufacturer_plans[manufacturer.pk]

    def _refuse_manufacturer(self, plan: ManufacturerPlan, reason: str):
        """Record a refusal against a Manufacturer plan."""
        plan.refusal_reason = reason
        self.counts["refusals"] += 1
        self._log("warning", f'Refusing to act on Manufacturer "{plan.name}": {reason}', plan.manufacturer)
