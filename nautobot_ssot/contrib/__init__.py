"""The SSoT `contrib` module contains reusable code for creating custom SSoT jobs where
Nautobot is the source or target."""

from nautobot_ssot.contrib.adapter import NautobotAdapter
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.annotations import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)

__all__ = (
    "CustomFieldAnnotation",
    "CustomRelationshipAnnotation",
    "NautobotAdapter",
    "NautobotModel",
    "RelationshipSideEnum",
)
