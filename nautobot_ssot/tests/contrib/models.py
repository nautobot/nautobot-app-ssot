"""Example NautobotModel instances for unittests."""

from typing import Annotated, List, Optional

from nautobot.dcim.models import Device, LocationType

from nautobot_ssot.contrib.enums import RelationshipSideEnum
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
)
from nautobot_ssot.tests.contrib.typeddicts import DeviceDict, SoftwareImageFileDict, TagDict


class LocationTypeModel(NautobotModel):
    """Example model for LocationType in unittests."""

    _modelname = "location_type"
    _model = LocationType

    name: str
    nestable: bool


class DeviceModel(NautobotModel):
    """Example model for unittests.

    NOTE: We only need the typehints for this set of unittests.
    """

    _modelname = "device"
    _model = Device

    # Standard Attributes
    name: str
    vc_position: Optional[int]

    # Foreign Keys
    status__name: str
    tenant__name: Optional[str]

    # N to many Relationships
    tags: List[TagDict] = []
    software_image_files: Optional[List[SoftwareImageFileDict]]

    # Custom Fields
    custom_str: Annotated[str, CustomFieldAnnotation(name="custom_str")]
    custom_int: Annotated[int, CustomFieldAnnotation(name="custom_int")]
    custom_bool: Optional[Annotated[bool, CustomFieldAnnotation(name="custom_bool")]]

    # Custom Foreign Keys
    parent__name: Annotated[str, CustomRelationshipAnnotation(name="device_parent", side=RelationshipSideEnum.SOURCE)]

    # Custom N to Many Relationships
    children: Annotated[
        List[DeviceDict],
        CustomRelationshipAnnotation(name="device_children", side=RelationshipSideEnum.DESTINATION),
    ]

    # Invalid Fields
    invalid_field: str
