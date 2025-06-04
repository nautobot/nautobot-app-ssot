"""Helper functions for SSoT."""

from django.db.models import Model
from nautobot.extras.models import Relationship
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.dataclasses.cache import ORMCache
from nautobot_ssot.contrib.types import (
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)


def get_nested_related_attribute_value(attr_name: str, obj: Model):
    """Get the value of an attribute for nested related objects."""
    if "__" not in attr_name:
        raise ValueError(f"Attribute `{attr_name}` is not a foreign key.")
    lookups = attr_name.split("__")
    related_object = getattr(obj, lookups.pop(0))
    related_attr_name = lookups.pop(-1)
    for lookup in lookups:
        related_object = getattr(related_object, lookup, None)
        if not related_object:
            break
    return getattr(related_object, related_attr_name) if related_object else None


def load_typed_dict(inner_type: type, db_obj: Model):
    """Create a TypedDict instance from a TypedDict type and Nautobot model."""
    typed_dict = {}
    for field_name in get_type_hints(inner_type):
        try:
            typed_dict[field_name] = (
                get_nested_related_attribute_value(field_name, db_obj)
                if "__" in field_name
                else getattr(db_obj, field_name)
            )
        except AttributeError:
            raise AttributeError()
    return typed_dict


def get_relationship_parameters(obj: Model, annotation: CustomRelationshipAnnotation, cache: ORMCache):
    """Get relationship parameters."""
    relationship: Relationship = cache.get_from_orm_cache({"label": annotation.name}, Relationship)
    relationship_association_parameters = {
        "relationship": relationship,
        "source_type": relationship.source_type,
        "destination_type": relationship.destination_type,
    }

    if annotation.side == RelationshipSideEnum.SOURCE:
        relationship_association_parameters["source_id"] = obj.id
    else:
        relationship_association_parameters["destination_id"] = obj.id
    return relationship_association_parameters
