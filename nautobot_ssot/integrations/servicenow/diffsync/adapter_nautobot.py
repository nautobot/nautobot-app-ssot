# pylint: disable=duplicate-code
"""DiffSync adapter class for Nautobot as source-of-truth."""

import datetime

from diffsync import Adapter
from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Location, Manufacturer
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Tag, TaggedItem

from . import models


class NautobotDiffSync(Adapter):
    """Nautobot adapter for DiffSync."""

    company = models.Company
    device = models.Device  # child of location
    interface = models.Interface  # child of device
    location = models.Location
    product_model = models.ProductModel  # child of company

    top_level = [
        "company",
        "location",
    ]

    def __init__(self, *args, job, sync, site_filter=None, **kwargs):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.site_filter = site_filter

    def load_manufacturers(self):
        """Add Manufacturers and their descendant DeviceTypes as DiffSyncModel instances."""
        for mfr_record in Manufacturer.objects.all():
            mfr = self.company(name=mfr_record.name, manufacturer=True, pk=mfr_record.id)
            self.add(mfr)
            for dtype_record in DeviceType.objects.filter(manufacturer=mfr_record):
                dtype = self.product_model(
                    manufacturer_name=mfr.name,
                    model_name=dtype_record.model,
                    model_number=dtype_record.model,
                    pk=dtype_record.id,
                )
                self.add(dtype)
                mfr.add_child(dtype)

        self.job.logger.info(
            f"Loaded {len(self.get_all('company'))} manufacturer records and "
            f"{len(self.get_all('product_model'))} device-type records from Nautobot."
        )

    def load_locations(self):
        """Load Nautobot Location objects as DiffSync Location models."""
        if self.site_filter is not None:
            # Load only direct ancestors of the given Site
            locations = [self.site_filter]
            ancestor = self.site_filter.parent
            while ancestor is not None:
                locations.insert(0, ancestor)
                ancestor = ancestor.parent
        else:
            locations = Location.objects.all()

        for location_record in locations:
            location = self.location(
                name=location_record.name,
                pk=location_record.id,
                parent_location_name=None,
            )
            if location_record.parent:
                location.parent_location_name = location_record.parent.name
            self.add(location)

        self.job.logger.info(f"Loaded {len(self.get_all('location'))} location records from Nautobot.")

    def load_interface(self, interface_record, device_model):
        """Import a single Nautobot Interface object as a DiffSync Interface model."""
        interface = self.interface(
            name=interface_record.name,
            device_name=device_model.name,
            description=interface_record.description,
            pk=interface_record.id,
        )
        self.add(interface)
        device_model.add_child(interface)

    def load(self):
        """Load data from Nautobot."""
        self.load_manufacturers()
        # Import all Nautobot Location records as Locations
        self.load_locations()

        for location in self.get_all(self.location):
            if location.pk is None:
                continue
            for device_record in Device.objects.filter(location__id=location.pk):
                device = self.device(
                    name=device_record.name,
                    location_name=location.name,
                    asset_tag=device_record.asset_tag or "",
                    manufacturer_name=device_record.device_type.manufacturer.name,
                    model_name=device_record.device_type.model,
                    serial=device_record.serial,
                    pk=device_record.id,
                )
                self.add(device)
                location.add_child(device)

                for interface_record in Interface.objects.filter(device=device_record):
                    self.load_interface(interface_record, device)

        self.job.logger.info(
            f"Loaded {len(self.get_all('device'))} device records and "
            f"{len(self.get_all('interface'))} interface records from Nautobot."
        )

    def tag_involved_objects(self, target):
        """Tag all objects that were successfully synced to the target."""
        # The SSoT Synced to ServiceNow Tag *should* have been created automatically during app installation
        # (see nautobot_ssot/integrations/servicenow/signals.py) but maybe a user deleted it inadvertently, so be safe:
        tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced to ServiceNow",
            defaults={
                "name": "SSoT Synced to ServiceNow",
                "description": "Object synced at some point from Nautobot to ServiceNow",
                "color": ColorChoices.COLOR_LIGHT_GREEN,
            },
        )
        # Ensure that the "ssot_synced_to_servicenow" CustomField is present; as above, it *should* already exist.
        custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_DATE,
            key="ssot_synced_to_servicenow",
            defaults={
                "label": "Last synced to ServiceNow",
            },
        )
        for model in [Device, DeviceType, Interface, Manufacturer, Location]:
            custom_field.content_types.add(ContentType.objects.get_for_model(model))

        today = datetime.date.today().isoformat()
        # Map each DiffSync model name to its corresponding Nautobot model class.
        nautobot_models = {
            "company": Manufacturer,
            "device": Device,
            "interface": Interface,
            "location": Location,
            "product_model": DeviceType,
        }
        for modelname, nautobot_model in nautobot_models.items():
            # Collect the PKs of all objects that now have a counterpart in the target DiffSync.
            synced_pks = []
            for local_instance in self.get_all(modelname):
                unique_id = local_instance.get_unique_id()
                try:
                    target.get(modelname, unique_id)
                except ObjectNotFound:
                    continue
                if local_instance.pk is not None:
                    synced_pks.append(local_instance.pk)

            if synced_pks:
                self.tag_objects(nautobot_model, synced_pks, tag, custom_field, today)

    def tag_objects(self, nautobot_model, pks, tag, custom_field, today):
        """Bulk-apply the given tag and custom field to many objects of a single Nautobot model.

        This deliberately uses bulk database operations rather than a per-object
        ``validated_save()``. Re-running each model's ``clean()`` and emitting a change-log
        entry for every object makes tagging tens of thousands of objects take hours; the bulk
        approach reduces this to minutes, at the cost of not change-logging the tag/custom-field
        bookkeeping update.
        """
        content_type = ContentType.objects.get_for_model(nautobot_model)

        # Apply the Tag through the TaggedItem table, skipping objects that already carry it.
        if hasattr(nautobot_model, "tags"):
            already_tagged = set(
                TaggedItem.objects.filter(tag=tag, content_type=content_type, object_id__in=pks).values_list(
                    "object_id", flat=True
                )
            )
            TaggedItem.objects.bulk_create(
                [
                    TaggedItem(tag=tag, content_type=content_type, object_id=pk)
                    for pk in pks
                    if pk not in already_tagged
                ],
                batch_size=1000,
                ignore_conflicts=True,
            )

        # Stamp the "last synced" date custom field, reading and writing _custom_field_data in bulk.
        if hasattr(nautobot_model, "cf"):
            objects_to_update = list(nautobot_model.objects.filter(pk__in=pks))
            for nautobot_object in objects_to_update:
                nautobot_object.cf[custom_field.key] = today
            nautobot_model.objects.bulk_update(objects_to_update, ["_custom_field_data"], batch_size=1000)
