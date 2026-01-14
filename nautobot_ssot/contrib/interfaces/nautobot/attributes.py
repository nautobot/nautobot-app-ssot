"""
Collection of interface functions to load data from Django/Nautobot ORM into the required formats
required by DiffSync models and SSoT operations.

- Functions to load individual attribute values
- Load attributes into DiffSync-compatible dictionary
"""

from django.db.models import Model
from nautobot_ssot.contrib.base import BaseNautobotModel, BaseNautobotAdapter
from typing import Type
from nautobot_ssot.contrib.enums import AttributeType
from nautobot_ssot.contrib.types import CustomFieldAnnotation, CustomRelationshipAnnotation, RelationshipSideEnum
from nautobot.core.models.generics import PrimaryModel
from nautobot.extras.models import Relationship
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot_ssot.utils.orm import (
    get_custom_relationship_associations,
    load_typed_dict,
    orm_attribute_lookup,
    load_list_of_typed_dicts,
    # get_custom_foreign_key_value,

)
from functools import lru_cache
from django.contrib.contenttypes.models import ContentType
from diffsync.exceptions import ObjectCrudException

@lru_cache
def get_custom_relationship(label: str):
    return Relationship.objects.get(label=label)


@lru_cache
def get_nautobot_orm_class(app_label: str, model: str):
    return ContentType.objects.get(app_label=app_label, model=model)



def get_standard_attribute(attributes: dict, obj: PrimaryModel, attr_name: str, **kwargs):
    attributes[attr_name] = getattr(obj, attr_name)
    return attributes


def get_foreign_key_attribute(attributes: dict, obj: PrimaryModel, attr_name: str, **kwargs):
    attributes[attr_name] = orm_attribute_lookup(obj, attr_name)
    return attributes

def get_n_to_many_relationship_attribute(attributes: dict, obj: PrimaryModel, attr_name: str, inner_type, **kwargs):
    """"""
    attributes[attr_name] = load_list_of_typed_dicts(
        inner_type,
        getattr(obj, attr_name).all(),
    )
    return attributes


def get_custom_field_attribute(attributes: dict, obj: PrimaryModel, attr_name: str, annotation: CustomFieldAnnotation, **kwargs):
    if annotation.key in obj.cf:
        attributes[attr_name] = obj.cf[annotation.key]
    return attributes


def get_custom_foreign_key(
        attributes: dict,
        obj: Model,
        attr_name: str,
        annotation: CustomRelationshipAnnotation,
        **kwargs,
    ):
    relationship = get_custom_relationship(label=annotation.name)
    associations, count = get_custom_relationship_associations(
        relationship=relationship,
        db_obj=obj,
        relationship_side=annotation.side,
    )

    if count == 0:
        return None
    if count > 1:
        raise ValueError(
            f"Foreign key ({obj.__name__}.{attr_name}) "
            "custom relationship matched two or more associations - this shouldn't happen."
        )

    attributes[attr_name] = orm_attribute_lookup(
        getattr(
            associations.first(),
            "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination",
        ),
        # Discard the first part of the paramater name as it references the initial related object
        attr_name.split("__", maxsplit=1)[1],
    )
    return attributes


def get_custom_n_to_many_relationship_attribute(attributes: dict, obj: PrimaryModel, attr_name: str, annotation: CustomRelationshipAnnotation, inner_type: Type):
    relationship_obj = get_custom_relationship(annotation.name)
    # relationship_associations = get_custom_relationship_associations(relationship_obj, obj, annotation.side)

    attributes_list = []
    for association in get_custom_relationship_associations(relationship_obj, obj, annotation.side)[0]:

        related_object = getattr(association,
            "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination"
        )
        dictionary_representation = load_typed_dict(inner_type, related_object)
        # Only use those where there is a single field defined, all 'None's will not help us.
        if any(dictionary_representation.values()):
            attributes_list.append(dictionary_representation)
    
    # For one-to-many, we need to return an object, not a list of objects
    if (relationship_obj.type == RelationshipTypeChoices.TYPE_ONE_TO_MANY 
            and annotation.side == RelationshipSideEnum.DESTINATION):
        if not attributes_list:
            attributes[attr_name] = None
            # return None
        elif len(attributes_list) == 1:
            attributes[attr_name] = attributes_list[0]
            # return attributes_list[0]
        else:
            raise ObjectCrudException(
                f"More than one related objects for a {RelationshipTypeChoices.TYPE_ONE_TO_MANY} relationship: "
            )
    else:
        attributes[attr_name] = attributes_list
    return attributes


ATTRIBUTE_TYPE_MAPPER = {
    AttributeType.STANDARD: get_standard_attribute,
    AttributeType.FOREIGN_KEY: get_foreign_key_attribute,
    AttributeType.N_TO_MANY_RELATIONSHIP: get_n_to_many_relationship_attribute,
    AttributeType.CUSTOM_FIELD: get_custom_field_attribute,
    AttributeType.CUSTOM_FOREIGN_KEY: get_custom_foreign_key,
    AttributeType.CUSTOM_N_TO_MANY_RELATIONSHIP: get_custom_n_to_many_relationship_attribute,
}


def build_attributes_dict(diffsync_model: Type[BaseNautobotModel], obj: PrimaryModel, adapter: BaseNautobotAdapter):
    """Load model attributes into a dictionary with value formats used by the DiffSync Models."""
    attributes = {}
    for attr_name in diffsync_model.get_synced_attributes():
        try:
            inner_type = diffsync_model.get_inner_type(attr_name)
        except (IndexError, KeyError, TypeError):
            inner_type = None

        if hasattr(adapter, f"load_param_{attr_name}"):
            attributes[attr_name] = getattr(adapter, f"load_param_{attr_name}")(attr_name, obj)
        else:
            ATTRIBUTE_TYPE_MAPPER[diffsync_model.get_attr_type(attr_name)](
                attributes=attributes,
                obj=obj,
                attr_name=attr_name,
                annotation=diffsync_model.get_annotation(attr_name),
                inner_type=inner_type,
            )
    return attributes
