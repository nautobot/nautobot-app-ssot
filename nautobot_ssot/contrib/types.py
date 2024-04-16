"""Contrib type classes for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from dataclasses import dataclass
from enum import Enum
from typing import Optional


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

    Note that for backwards compatibility purposes it is also possible to use `CustomFieldAnnotation.name` instead of
    `CustomFieldAnnotation.key`.

    Example:
        Given a boolean custom field with label "Is Global" and key "is_global" on the Provider model:

        ```python
        class ProviderModel(NautobotModel):
            _model: Provider
            _identifiers = ("name",)
            _attributes = ("is_global",)

            name: str
            is_global: Annotated[bool, CustomFieldAnnotation(key="is_global")
        ```

        This then maps the model field 'is_global' to the custom field with the key 'is_global'.
    """

    # TODO: Delete on 3.0, keep around for backwards compatibility for now
    name: Optional[str] = None

    key: Optional[str] = None

    def __post_init__(self):
        """Compatibility layer with using 'name' instead of 'key'.

        If `self.key` isn't set, fall back to the old behaviour.
        """
        if not self.key:
            if self.name:
                self.key = self.name
            else:
                raise ValueError("The 'key' field on CustomFieldAnnotation needs to be set.")
