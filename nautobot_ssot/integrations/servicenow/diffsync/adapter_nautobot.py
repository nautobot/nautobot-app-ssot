"""DiffSync adapter class for Nautobot as source-of-truth."""

import datetime

from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound

from django.contrib.contenttypes.models import ContentType

from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer, Region, Site
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Tag
from nautobot.utilities.choices import ColorChoices

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
            mfr = self.company(diffsync=self, name=mfr_record.name, manufacturer=True, pk=mfr_record.pk)
            self.add(mfr)
            for dtype_record in DeviceType.objects.filter(manufacturer=mfr_record):
                dtype = self.product_model(
                    diffsync=self,
                    manufacturer_name=mfr.name,
                    model_name=dtype_record.model,
                    model_number=dtype_record.model,
                    pk=dtype_record.pk,
                )
                self.add(dtype)
                mfr.add_child(dtype)

        self.job.log_info(
            message=f"Loaded {len(self.get_all('company'))} manufacturer records and "
            f"{len(self.get_all('product_model'))} device-type records from Nautobot."
        )

    def load_regions(self, parent_location=None):
        """Recursively add Nautobot Region objects as DiffSync Location models."""
        if self.site_filter is not None:
            # Load only direct ancestors of the given Site
            regions = []
            ancestor = self.site_filter.region
            while ancestor is not None:
                regions.insert(0, ancestor)
                ancestor = ancestor.parent
        else:
            parent_pk = parent_location.region_pk if parent_location else None
            regions = Region.objects.filter(parent=parent_pk)

        for region_record in regions:
            location = self.location(
                diffsync=self,
                name=region_record.name,
                region_pk=region_record.pk,
            )
            if region_record.parent:
                location.parent_location_name = region_record.parent.name
                if not parent_location:
                    parent_location = self.get(self.location, region_record.parent.name)
                if parent_location:
                    parent_location.contained_locations.append(location)
            self.add(location)
            if self.site_filter is None:
                # Recursively load children of the given Region
                self.load_regions(parent_location=location)

    def load_sites(self):
        """Add Nautobot Site objects as DiffSync Location models."""
        for location in self.get_all(self.location):
            self.job.log_debug(f"Getting Sites associated with {location}")
            for site_record in Site.objects.filter(region__name=location.name):
                if self.site_filter is not None and site_record != self.site_filter:
                    self.job.log_debug(f"Skipping site {site_record} due to site filter")
                    continue
                # A Site and a Region may share the same name; if so they become part of the same Location record.
                try:
                    region_location = self.get(self.location, site_record.name)
                    region_location.site_pk = site_record.pk
                except ObjectNotFound:
                    site_location = self.location(
                        diffsync=self,
                        name=site_record.name,
                        latitude=site_record.latitude or "",
                        longitude=site_record.longitude or "",
                        site_pk=site_record.pk,
                    )
                    self.add(site_location)
                    if site_record.region:
                        if site_record.name != site_record.region.name:
                            region_location = self.get(self.location, site_record.region.name)
                            region_location.contained_locations.append(site_location)
                        site_location.parent_location_name = site_record.region.name

        self.job.log_info(
            message=f"Loaded {len(self.get_all('location'))} aggregated site and region records from Nautobot."
        )

    def load_interface(self, interface_record, device_model):
        """Import a single Nautobot Interface object as a DiffSync Interface model."""
        interface = self.interface(
            diffsync=self,
            name=interface_record.name,
            device_name=device_model.name,
            description=interface_record.description,
            pk=interface_record.pk,
        )
        self.add(interface)
        device_model.add_child(interface)

    def load(self):
        """Load data from Nautobot."""
        self.load_manufacturers()
        # Import all Nautobot Region records as Locations
        self.load_regions()

        # Import all Nautobot Site records as Locations
        self.load_sites()

        for location in self.get_all(self.location):
            if location.site_pk is None:
                continue
            for device_record in Device.objects.filter(site__pk=location.site_pk):
                device = self.device(
                    diffsync=self,
                    name=device_record.name,
                    location_name=location.name,
                    asset_tag=device_record.asset_tag or "",
                    manufacturer_name=device_record.device_type.manufacturer.name,
                    model_name=device_record.device_type.model,
                    serial=device_record.serial,
                    pk=device_record.pk,
                )
                self.add(device)
                location.add_child(device)

                for interface_record in Interface.objects.filter(device=device_record):
                    self.load_interface(interface_record, device)

        self.job.log_info(
            message=f"Loaded {len(self.get_all('device'))} device records and "
            f"{len(self.get_all('interface'))} interface records from Nautobot."
        )

    def tag_involved_objects(self, target):
        """Tag all objects that were successfully synced to the target."""
        # The ssot-synced-to-servicenow tag *should* have been created automatically during plugin installation
        # (see nautobot_ssot_servicenow/signals.py) but maybe a user deleted it inadvertently, so be safe:
        tag, _ = Tag.objects.get_or_create(
            slug="ssot-synced-to-servicenow",
            defaults={
                "name": "SSoT Synced to ServiceNow",
                "description": "Object synced at some point from Nautobot to ServiceNow",
                "color": ColorChoices.COLOR_LIGHT_GREEN,
            },
        )
        # Ensure that the "ssot-synced-to-servicenow" custom field is present; as above, it *should* already exist.
        custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_DATE,
            name="ssot-synced-to-servicenow",
            defaults={
                "label": "Last synced to ServiceNow on",
            },
        )
        for model in [Device, DeviceType, Interface, Manufacturer, Region, Site]:
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
                nautobot_object.cf[custom_field.name] = today
            nautobot_object.validated_save()

        if modelname == "company":
            _tag_object(Manufacturer.objects.get(pk=model_instance.pk))
        elif modelname == "device":
            _tag_object(Device.objects.get(pk=model_instance.pk))
        elif modelname == "interface":
            _tag_object(Interface.objects.get(pk=model_instance.pk))
        elif modelname == "location":
            if model_instance.region_pk is not None:
                _tag_object(Region.objects.get(pk=model_instance.region_pk))
            if model_instance.site_pk is not None:
                _tag_object(Site.objects.get(pk=model_instance.site_pk))
        elif modelname == "product_model":
            _tag_object(DeviceType.objects.get(pk=model_instance.pk))
