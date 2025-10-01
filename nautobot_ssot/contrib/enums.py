from enum import Enum


class AttributeType(Enum):
    """Enum for identifying a `NautobotModel` attribute type."""

    STANDARD = 0
    FOREIGN_KEY = 1
    ONE_TO_MANY_RELATIONSHIP = 2
    MANY_TO_MANY_RELATIONSHIP = 3
    CUSTOM_FIELD = 4
    CUSTOM_FOREIGN_KEY = 5
    CUSTOM_TO_MANY_RELATIONSHIP = 6


class SortType(Enum):
    """Enum for identifying sortable field types when sorting SSoT fields.

    Enum used for future extension if required.
    """

    DICT = 1


class RelationshipSideEnum(Enum):
    """This details which side of a custom relationship the model it's defined on is on."""

    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"
