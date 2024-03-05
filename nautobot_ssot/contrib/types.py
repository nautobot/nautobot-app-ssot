"""Contrib type classes for interfacing with Nautobot in SSoT."""
from dataclasses import dataclass
from enum import Enum

from typing import FrozenSet, Tuple, Hashable

# This type describes a set of parameters to use as a dictionary key for the cache. As such, its needs to be hashable
# and therefore a frozenset rather than a normal set or a list.
#
# The following is an example of a parameter set that describes a tenant based on its name and group:
# frozenset(
#  [
#   ("name", "ABC Inc."),
#   ("group__name", "Customers"),
#  ]
# )
ParameterSet = FrozenSet[Tuple[str, Hashable]]


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

    This exists to map model fields to their corresponding custom fields. This serves to explicitly differentiate
    normal fields from custom fields.

    Example:
        Given a boolean custom field with name "Is Global" and key "is_global" on the Provider model:

        ```python
        class ProviderModel(NautobotModel):
            _model: Provider
            _identifiers = ("name",)
            _attributes = ("is_global",)

            name: str
            is_global: Annotated[bool, CustomFieldAnnotation(name="Is Global")
        ```

        This then maps the model field 'is_global' to the custom field with the name 'Is Global'.
    """

    name: str
