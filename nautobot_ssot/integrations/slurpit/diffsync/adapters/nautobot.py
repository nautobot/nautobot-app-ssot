# pylint: disable=R0801
"""DiffSync adapter for Nautobot."""

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.slurpit.diffsync.models import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    InventoryItemModel,
    IPAddressModel,
    LocationModel,
    ManufacturerModel,
    PlatformModel,
    PrefixModel,
    RoleModel,
    VLANModel,
    VRFModel,
)


class NautobotDiffSyncAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    def __init__(self, *args, job, sync=None, data=None, **kwargs):
        """Initialize the NautobotDiffSyncAdapter."""
        self.data = data if data is not None else {}
        super().__init__(*args, job=job, sync=sync, **kwargs)

    def _load_objects(self, diffsync_model):
        """Given a diffsync model class, load a list of models from the database and return them."""
        parameter_names = self._get_parameter_names(diffsync_model)
        for database_object in diffsync_model._get_queryset(data=self.data):  # pylint: disable=W0212
            self._load_single_object(database_object, diffsync_model, parameter_names)

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
    )
