"""Base Shared Models for Forward Enterprise integration with SSoT app."""
# pylint: disable=duplicate-code

from typing import List, Optional

try:
    from typing import Annotated  # Python>=3.9
except ImportError:
    from typing_extensions import Annotated

from diffsync import DiffSyncModel
from pydantic import Field, field_validator

from nautobot_ssot.contrib import CustomFieldAnnotation
from nautobot_ssot.contrib.typeddicts import VRFDict
from nautobot_ssot.integrations.forward_enterprise import constants


def ensure_not_none(value, default=""):
    """Utility function to ensure a value is not None, providing a default."""
    return value if value is not None else default


class PrefixModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise Prefixes."""

    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name")
    _attributes = ("description", "status__name", "vrfs", "system_of_record")
    _children = {}

    network: str
    prefix_length: int
    namespace__name: str
    description: Optional[str] = ""
    status__name: str = "Active"
    vrfs: List[VRFDict] = Field(default_factory=list)
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None


class IPAddressModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise IP Addresses."""

    _modelname = "ipaddress"
    _identifiers = ("host", "mask_length")
    _attributes = ("status__name", "parent__network", "parent__prefix_length", "system_of_record")
    _children = {}

    host: str
    mask_length: int
    status__name: str = "Active"
    parent__network: str
    parent__prefix_length: int
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None


class IPAssignmentModel(DiffSyncModel):
    """IPAssignment model for Forward Enterprise, mapping IP addresses to interfaces."""

    _modelname = "ipassignment"
    _identifiers = ("interface__device__name", "interface__name", "ip_address__host")
    _attributes = ()

    interface__device__name: str
    interface__name: str
    ip_address__host: str


class VRFModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise VRFs."""

    _modelname = "vrf"
    _identifiers = ("name", "namespace__name")
    _attributes = ("description", "rd", "tenant__name", "system_of_record")
    _children = {}

    name: str
    namespace__name: str
    description: Optional[str] = ""
    rd: Optional[str] = ""
    tenant__name: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None

    @field_validator("name")
    @classmethod
    def validate_vrf_name(cls, value):
        """Validate VRF name is present."""
        if not value:
            raise ValueError("VRF name cannot be empty")
        return value

    @field_validator("namespace__name")
    @classmethod
    def validate_namespace(cls, value):
        """Ensure namespace is set."""
        return value if value else "Global"

    @field_validator("description")
    @classmethod
    def ensure_description_not_none(cls, value):
        """Ensure description is never None."""
        return ensure_not_none(value)

    @field_validator("rd")
    @classmethod
    def ensure_rd_not_none(cls, value):
        """Ensure RD is never None."""
        return ensure_not_none(value)


class VLANModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise VLANs."""

    _modelname = "vlan"
    _identifiers = ("vid", "name", "vlan_group__name")
    _attributes = ("description", "status__name", "tenant__name", "role", "system_of_record")
    _children = {}

    vid: int
    name: str
    vlan_group__name: str
    description: Optional[str] = ""
    status__name: str = "Active"
    tenant__name: Optional[str] = None
    role: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None

    @field_validator("vid")
    @classmethod
    def validate_vid(cls, value):
        """Validate VLAN ID is within valid range."""
        if not isinstance(value, int) or value < constants.MIN_VLAN_ID or value > constants.MAX_VLAN_ID:
            raise ValueError(
                f"VLAN ID must be between {constants.MIN_VLAN_ID} and {constants.MAX_VLAN_ID}, got {value}"
            )
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        """Ensure VLAN name is present."""
        if not value or not value.strip():
            raise ValueError("VLAN name cannot be empty")
        return value.strip()
