# pylint: disable=duplicate-code
"""Nautobot Adapter for SolarWinds SSoT app."""

from nautobot_ssot.contrib.adapter import NautobotAdapter as BaseNautobotAdapter
from nautobot_ssot.integrations.solarwinds.diffsync.models.base import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    IPAddressModel,
    LocationModel,
    ManufacturerModel,
    PlatformModel,
    PrefixModel,
    RoleModel,
    SoftwareVersionModel,
)
from nautobot_ssot.integrations.solarwinds.diffsync.models.nautobot import (
    NautobotIPAddressToInterfaceModel,
)

# Per-model lookup paths used to scope the Nautobot side of the diff to the
# Job's chosen Tenant. Models not listed (Location, Manufacturer, Platform,
# Role, DeviceType, SoftwareVersion) have no tenancy concept and load globally.
TENANT_LOOKUPS = {
    "device": "tenant__name",
    "interface": "device__tenant__name",
    "prefix": "tenant__name",
    "ipaddress": "tenant__name",
    "ipassignment": "ip_address__tenant__name",
}


class NautobotAdapter(BaseNautobotAdapter):
    """DiffSync adapter for Nautobot."""

    location = LocationModel
    platform = PlatformModel
    role = RoleModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    softwareversion = SoftwareVersionModel
    device = DeviceModel
    interface = InterfaceModel
    prefix = PrefixModel
    ipaddress = IPAddressModel
    ipassignment = NautobotIPAddressToInterfaceModel

    top_level = [
        "location",
        "manufacturer",
        "platform",
        "role",
        "softwareversion",
        "device",
        "prefix",
        "ipaddress",
        "ipassignment",
    ]

    def __init__(self, *args, tenant=None, **kwargs):
        """Capture the Job's Tenant so we can scope per-model querysets at load time."""
        super().__init__(*args, **kwargs)
        self.tenant = tenant

    def _load_objects(self, diffsync_model):
        """Load Nautobot objects, narrowing each queryset to the Job's Tenant when applicable."""
        parameter_names = diffsync_model.get_synced_attributes()
        queryset = diffsync_model._get_queryset()
        lookup = TENANT_LOOKUPS.get(diffsync_model._modelname)
        if lookup and self.tenant is not None:
            queryset = queryset.filter(**{lookup: self.tenant.name})
        for database_object in queryset:
            self._load_single_object(database_object, diffsync_model, parameter_names)

    def load_param_mac_address(self, parameter_name, database_object):
        """Custom loader for 'mac_address' parameter."""
        mac_addr = getattr(database_object, parameter_name)
        if mac_addr is not None:
            return str(mac_addr)
        return mac_addr
