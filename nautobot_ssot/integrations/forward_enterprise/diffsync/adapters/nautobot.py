# pylint: disable=R0801
"""Forward Enterprise Nautobot adapter for nautobot-ssot plugin."""

from diffsync.exceptions import ObjectAlreadyExists
from django.core.exceptions import ObjectDoesNotExist

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.forward_enterprise.diffsync.models.models import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    LocationModel,
    ManufacturerModel,
    NautobotIPAddressModel,
    NautobotIPAssignmentModel,
    NautobotPrefixModel,
    NautobotVLANModel,
    NautobotVRFModel,
    PlatformModel,
    RoleModel,
)


class NautobotDiffSyncAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    def _load_objects(self, diffsync_model):
        """Given a diffsync model class, load a list of models from the database and return them.

        Uses job instance attributes (sync_forward_tagged_only) for model filtering.
        """
        parameter_names = self._get_parameter_names(diffsync_model)
        # Build data dict from job attributes instead of job.kwargs
        data = {"sync_forward_tagged_only": True}  # Always use tagged-only mode for Forward Enterprise
        for database_object in diffsync_model._get_queryset(data=data):  # pylint: disable=W0212
            try:
                # Special handling for DeviceModel to check for broken location references
                if diffsync_model.__name__ == "DeviceModel":
                    try:
                        # Test if location access works (this will raise RelatedObjectDoesNotExist if broken)
                        _ = database_object.location
                    except (ObjectDoesNotExist, AttributeError) as exception:
                        if self.job:
                            self.job.logger.warning(
                                "Skipping device %s due to broken location reference: %s",
                                database_object.name,
                                str(exception),
                            )
                        continue

                self._load_single_object(database_object, diffsync_model, parameter_names)
            except ObjectAlreadyExists:
                continue

    def load_param_device__name(self, _parameter_name, database_object):
        """Custom parameter handler for device__name lookup field."""
        return database_object.device.name

    def load_param_location_type__name(self, _parameter_name, database_object):
        """Custom parameter handler for location_type__name lookup field."""
        return database_object.location_type.name

    def load_param_status__name(self, _parameter_name, database_object):
        """Custom parameter handler for status__name lookup field."""
        return database_object.status.name

    def load_param_tags(self, _parameter_name, database_object):
        """Custom parameter handler for tags many-to-many field."""
        return [{"name": tag.name} for tag in database_object.tags.all()]

    def load_param_mac_address(self, _parameter_name, database_object):
        """Custom parameter handler for mac_address field to convert EUI to string."""
        mac_addr = database_object.mac_address
        return str(mac_addr) if mac_addr else ""

    def load_param_mtu(self, _parameter_name, database_object):
        """Custom parameter handler for mtu field to handle None values."""
        return database_object.mtu if database_object.mtu is not None else 1500

    def load(self):
        """Load data from Nautobot into the DiffSync store."""
        if self.job:
            self.job.logger.info("Loading existing objects from Nautobot database")

        # Call parent load method
        super().load()

        if self.job:
            # Log summary of loaded objects
            summary = []
            for model_name in self.top_level:
                count = len(list(self.get_all(model_name)))
                summary.append(f"{model_name}: {count}")
            self.job.logger.info(f"Loaded objects from Nautobot: {', '.join(summary)}")

    # Model mappings
    location = LocationModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    platform = PlatformModel
    role = RoleModel
    device = DeviceModel
    interface = InterfaceModel
    vrf = NautobotVRFModel
    prefix = NautobotPrefixModel
    ipaddress = NautobotIPAddressModel
    ipassignment = NautobotIPAssignmentModel
    vlan = NautobotVLANModel

    top_level = (
        "location",
        "manufacturer",
        "device_type",
        "platform",
        "role",
        "device",
        "interface",
        "vrf",
        "prefix",
        "ipaddress",
        "ipassignment",
        "vlan",
    )
