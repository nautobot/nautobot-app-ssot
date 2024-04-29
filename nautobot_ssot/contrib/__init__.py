"""SSoT Contrib."""

from nautobot_ssot.contrib.adapter import NautobotAdapter
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.types import (
    RelationshipSideEnum,
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
)

__all__ = (
    "CustomFieldAnnotation",
    "CustomRelationshipAnnotation",
    "NautobotAdapter",
    "NautobotModel",
    "RelationshipSideEnum",
)
