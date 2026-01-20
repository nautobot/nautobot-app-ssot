from enum import auto, Enum


class AttributeType(Enum):
    """Attribute types used in loading Nauboto models to DiffSync models."""

    STANDARD = auto()
    FOREIGN_KEY = auto()
    N_TO_MANY_RELATIONSHIP = auto()
    CUSTOM_FIELD = auto()
    CUSTOM_FOREIGN_KEY = auto()
    CUSTOM_N_TO_MANY_RELATIONSHIP = auto()


class RelationshipSideEnum(Enum):
    """This details which side of a custom relationship the model it's defined on is on."""

    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"
