"""Enums used in SSoT contrib processes."""

from enum import Enum


class SortType(Enum):
    """Enum for identifying sortable field types when sorting SSoT fields.

    Enum used for future extension if required.
    """

    DICT = 1


class RelationshipSideEnum(Enum):
    """This details which side of a custom relationship the model it's defined on is on."""

    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"
