"""Supporting classes for SSoT contib interfacing with Nautobot."""

from enum import Enum
from dataclasses import dataclass


class RelationshipSideEnum(Enum):
    """This details which side of a custom relationship the model it's defined on is on."""

    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"


@dataclass
class CustomRelationshipAnnotation:
    """Map a model field to an arbitrary custom relationship.

    For usage with `typing.Annotated`.

    This exists to map model fields to their corresponding relationship fields. All different types of relationships
    then work exactly the same as they normally do, just that you have to annotate the field(s) that belong(s) to the
    relationship.

    Example:
        Given a custom relationship called "Circuit provider to tenant":
        ```python
        class ProviderModel(NautobotModel):
            _model: Provider
            _identifiers = ("name",)
            _attributes = ("tenant__name",)

            tenant__name = Annotated[
                str,
                CustomRelationshipAnnotation(name="Circuit provider to tenant", side=RelationshipSideEnum.SOURCE)
            ]

        This then identifies the tenant to relate the provider to through its `name` field as well as the relationship
        name.
    """

    name: str
    side: RelationshipSideEnum


@dataclass
class CustomFieldAnnotation:
    """Map a model field to an arbitrary custom field name.

    For usage with `typing.Annotated`.

    This exists to map model fields to their corresponding custom fields. This solves the problem of Python object
    attributes not being able to include spaces, while custom field names/labels may.

    TODO: With Nautobot 2.0, the custom fields `key` field needs to be a valid Python identifier. This will probably
      simplify this a lot.

    Example:
        Given a boolean custom field "Is Global" on the Provider model:

        ```python
        class ProviderModel(NautobotModel):
            _model: Provider
            _identifiers = ("name",)
            _attributes = ("is_global",)

            name: str
            is_global: Annotated[bool, CustomFieldAnnotation(name="Is Global")
        ```

        This then maps the model field 'is_global' to the custom field 'Is Global'.
    """

    name: str
