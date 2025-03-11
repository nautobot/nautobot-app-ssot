"""Nautobot Adapter for Cradlepoint Integration."""
from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.cradlepoint.diffsync.models.cradlepoint import (
    CradlepointDevice,
    CradlepointDeviceType,
    CradlepointRole,
    CradlepointStatus,
)
import pydantic
from typing_extensions import get_type_hints
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)


class Adapter(NautobotAdapter):
    """Nautobot Adapter for vSphere SSoT."""

    status = CradlepointStatus
    device_role = CradlepointRole
    device_type = CradlepointDeviceType
    device = CradlepointDevice

    top_level = ("status", "device_role", "device_type", "device")

    def __init__(self, *args, job=None, sync=None, config, **kwargs):
        """Initialize the adapter."""
        super().__init__(*args, job=job, sync=sync, **kwargs)
        self.config = config

    def load_param_mac_address(self, parameter_name, database_object):
        """Force mac address to string when loading it into the diffsync store."""
        return str(getattr(database_object, parameter_name))
