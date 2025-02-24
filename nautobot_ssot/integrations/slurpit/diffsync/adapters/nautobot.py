# pylint: disable=R0801
"""DiffSync adapter for Nautobot."""

from diffsync.exceptions import ObjectAlreadyExists

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.slurpit.diffsync.models import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    InventoryItemModel,
    IPAddressModel,
    LocationModel,
    ManufacturerModel,
    NautobotIPAddressToInterfaceModel,
    PlatformModel,
    PrefixModel,
    RoleModel,
    VLANModel,
    VRFModel,
)


class NautobotDiffSyncAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    def _load_objects(self, diffsync_model):
        """Given a diffsync model class, load a list of models from the database and return them. Passing in job kwargs for model filtering."""
        parameter_names = self._get_parameter_names(diffsync_model)
        for database_object in diffsync_model._get_queryset(data=self.job.kwargs):  # pylint: disable=W0212
            try:
                self._load_single_object(database_object, diffsync_model, parameter_names)
            except ObjectAlreadyExists:
                continue

    location = LocationModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    platform = PlatformModel
    role = RoleModel
    device = DeviceModel
    interface = InterfaceModel
    inventory_item = InventoryItemModel
    vlan = VLANModel
    vrf = VRFModel
    prefix = PrefixModel
    ipaddress = IPAddressModel
    ipassignment = NautobotIPAddressToInterfaceModel
    top_level = (
        "location",
        "manufacturer",
        "device_type",
        "platform",
        "role",
        "device",
        "vlan",
        "vrf",
        "prefix",
        "ipaddress",
        "interface",
        "ipassignment",
    )
