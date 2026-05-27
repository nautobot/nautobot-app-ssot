"""Public exports for SSoT contrib helpers.

Keep imports in this module safe during Django startup by avoiding eager imports
of modules that touch ORM models at import time.
"""

from nautobot_ssot.contrib.component_autocreation import is_suppression_active, skip_component_autocreation
from nautobot_ssot.contrib.types import CustomFieldAnnotation, CustomRelationshipAnnotation, RelationshipSideEnum


def __getattr__(name):
    """Lazily load Django/ORM-dependent exports."""
    if name == "NautobotAdapter":
        from nautobot_ssot.contrib.adapter import NautobotAdapter  # pylint: disable=import-outside-toplevel

        return NautobotAdapter
    if name == "NautobotModel":
        from nautobot_ssot.contrib.model import NautobotModel  # pylint: disable=import-outside-toplevel

        return NautobotModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = (
    "CustomFieldAnnotation",
    "CustomRelationshipAnnotation",
    "NautobotAdapter",
    "NautobotModel",
    "RelationshipSideEnum",
    "is_suppression_active",
    "skip_component_autocreation",
)
