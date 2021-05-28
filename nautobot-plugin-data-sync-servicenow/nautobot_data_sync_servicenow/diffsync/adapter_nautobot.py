"""DiffSync adapter class for Nautobot as source-of-truth."""

from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound

from nautobot.dcim.models import Device, Interface, Region, Site

from . import models


class NautobotDiffSync(DiffSync):
    """Nautobot adapter for DiffSync."""

    location = models.Location
    device = models.Device
    interface = models.Interface

    top_level = [
        "location",
    ]

    def load_regions(self, parent_location=None):
        """Recursively add Nautobot Region objects as DiffSync Location models."""
        parent_pk = parent_location.pk if parent_location else None
        for region_record in Region.objects.filter(parent=parent_pk):
            location = self.location(diffsync=self, name=region_record.name, pk=region_record.pk)
            if parent_location:
                parent_location.contained_locations.append(location)
                location.parent_location_name = parent_location.name
            self.add(location)
            self.load_regions(parent_location=location)

    def load_sites(self):
        """Add Nautobot Site objects as DiffSync Location models."""
        for site_record in Site.objects.all():
            # A Site and a Region may share the same name; if so they become part of the same Location record.
            try:
                location = self.get(self.location, site_record.name)
            except ObjectNotFound:
                location = self.location(diffsync=self, name=site_record.name)
                self.add(location)
            location.status = site_record.status
            if site_record.region:
                if location.name != site_record.region.name:
                    region_location = self.get(self.location, site_record.region.name)
                    region_location.contained_locations.append(location)
                    location.parent_location_name = region_location.name

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
        # Import all Nautobot Region records as Locations
        self.load_regions(parent_location=None)

        # Import all Nautobot Site records as Locations
        self.load_sites()

        for location in self.get_all(self.location):
            for device_record in Device.objects.filter(site=location.remote_site_id):
                device = self.device(
                    diffsync=self,
                    name=device_record.name,
                    platform=str(device_record.platform) if device_record.platform else None,
                    model=str(device_record.device_type),
                    role=str(device_record.device_role),
                    location_name=location.name,
                    vendor=str(device_record.device_type.manufacturer),
                    status=device_record.status,
                    pk=device_record.pk,
                )
                self.add(device)
                location.add_child(device)

                for interface_record in Interface.objects.filter(device=device_record):
                    self.load_interface(interface_record, device)
