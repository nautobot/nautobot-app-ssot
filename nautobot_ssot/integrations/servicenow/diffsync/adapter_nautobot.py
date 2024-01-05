# pylint: disable=duplicate-code
"""DiffSync adapter class for Nautobot as source-of-truth."""

import datetime

from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound

from django.contrib.contenttypes.models import ContentType

from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer, Location
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Tag
from nautobot.core.choices import ColorChoices

from . import models


class NautobotDiffSync(DiffSync):
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
            mfr = self.company(diffsync=self, name=mfr_record.name, manufacturer=True, pk=mfr_record.id)
            self.add(mfr)
            for dtype_record in DeviceType.objects.filter(manufacturer=mfr_record):
                dtype = self.product_model(
                    diffsync=self,
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
            locations = []
            ancestor = self.site_filter.parent
            while ancestor is not None:
                locations.insert(0, ancestor)
        else:
            locations = Location.objects.all()

        for location_record in locations:
            location = self.location(
                diffsync=self,
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
            diffsync=self,
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
                    diffsync=self,
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

        for modelname in [
            "company",
            "device",
            "interface",
            "location",
            "product_model",
        ]:
            for local_instance in self.get_all(modelname):
                unique_id = local_instance.get_unique_id()
                # Verify that the object now has a counterpart in the target DiffSync
                try:
                    target.get(modelname, unique_id)
                except ObjectNotFound:
                    continue

                self.tag_object(modelname, unique_id, tag, custom_field)

    def tag_object(self, modelname, unique_id, tag, custom_field):
        """Apply the given tag and custom field to the identified object."""
        model_instance = self.get(modelname, unique_id)
        today = datetime.date.today().isoformat()

        def _tag_object(nautobot_object):
            """Apply custom field and tag to object, if applicable."""
            if hasattr(nautobot_object, "tags"):
                nautobot_object.tags.add(tag)
            if hasattr(nautobot_object, "cf"):
                nautobot_object.cf[custom_field.key] = today
            nautobot_object.validated_save()

        if modelname == "company":
            _tag_object(Manufacturer.objects.get(pk=model_instance.pk))
        elif modelname == "device":
            _tag_object(Device.objects.get(pk=model_instance.pk))
        elif modelname == "interface":
            _tag_object(Interface.objects.get(pk=model_instance.pk))
        elif modelname == "location":
            if model_instance.pk is not None:
                _tag_object(Location.objects.get(pk=model_instance.pk))
        elif modelname == "product_model":
            _tag_object(DeviceType.objects.get(pk=model_instance.pk))
