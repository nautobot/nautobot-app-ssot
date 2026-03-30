"""Enums used in SSoT contrib processes."""

from enum import auto, Enum


class SortType(Enum):
    """Enum for identifying sortable field types when sorting SSoT fields.

    Enum used for future extension if required.
    """

    DICT = 1


class RelationshipSideEnum(Enum):
    """This details which side of a custom relationship the model it's defined on is on."""

    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"


class AttributeType(Enum):
    """Enum for identifying DiffSync model attribute types as used in contrib."""

    STANDARD = auto()
    FOREIGN_KEY = auto()
    N_TO_MANY_RELATIONSHIP = auto()
    CUSTOM_FIELD = auto()
    CUSTOM_FOREIGN_KEY = auto()
    CUSTOM_N_TO_MANY_RELATIONSHIP = auto()
