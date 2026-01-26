"""Base model module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from collections import defaultdict
from datetime import datetime
from typing import Annotated, List, Union, get_type_hints

from nautobot.core.models import BaseModel

from diffsync import DiffSyncModel
from diffsync.exceptions import ObjectCrudException, ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned, ValidationError
from django.db.models import ProtectedError, QuerySet
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, RelationshipAssociation
from nautobot.extras.models.metadata import ObjectMetadata
from functools import lru_cache
from django.db.models import Model as ModelObj

from nautobot_ssot.contrib.enums import AttributeType

from nautobot_ssot.contrib.base import BaseNautobotModel
from nautobot_ssot.contrib.annotations import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)
from nautobot_ssot.utils.orm import get_content_type
from diffsync.exceptions import ObjectNotCreated
from nautobot_ssot.utils.cache import get_orm_object
from dataclasses import dataclass, field
from nautobot_ssot.contrib.cache import get_custom_relationship

# @dataclass
# class CustomNToManyRelationship:
#     """"""

#     associations: dict = defaultdict(dict[CustomRelationshipAnnotation, List[dict]])
    
#     def add_association(self, annotation: CustomRelationshipAnnotation, objects):
#         """"""
#         if not isinstance(annotation, CustomRelationshipAnnotation):
#             raise TypeError(f"field `annotation` must be of type `CustomRelationshipAnnotation`, got `{type(annotation)}`")
        



def new(annotation: CustomRelationshipAnnotation, objects: list[dict]):
    """"""



def update_standard_attribute(db_obj):
    """"""


def update_custom_n_to_many_field(db_obj: BaseModel, dictionary: dict):
    """"""
    annotation = dictionary.pop("annotation")
    objects = dictionary.pop("objects")
    relationship = get_custom_relationship(annotation.name)

    associations = []
    for obj_to_relate in objects:
        association_parameters = {
            "relationship": relationship,
            "source_type": relationship.source_type,
            "destination_type": relationship.destination_type,
        }
        if annotation.side == RelationshipSideEnum.SOURCE:
            association_parameters["source_id"] = db_obj.id
            association_parameters["destination_id"] = obj_to_relate.id
        else:
            association_parameters["source_id"] = obj_to_relate.id
            association_parameters["destination_id"] = db_obj.id

        try:
            association = get_orm_object(RelationshipAssociation, association_parameters)
        except RelationshipAssociation.DoesNotExist:
            # Create new association and save to database
            association = RelationshipAssociation(**association_parameters)
            association.validated_save()
        associations.append(association)
        #associations.append(adapter.cache.get_or_create(RelationshipAssociation, association_parameters))

    # Now we need to clean up any associations that we're not `get_or_create`'d in order to achieve
    # declarativeness.
    # TODO: This may benefit from an ORM cache with `filter` capabilities, but I guess the gain in most cases
    # would be fairly minor.
    for existing_association in RelationshipAssociation.objects.filter(
        relationship=relationship,
        source_type=relationship.source_type,
        destination_type=relationship.destination_type,
    ):
        if existing_association not in associations:
            existing_association.delete()


def update_custom_foreign_key(db_obj: BaseModel, related_model_dict: dict):
    annotation: CustomRelationshipAnnotation = related_model_dict.pop("_annotation")
    relationship = get_orm_object(Relationship, {"label": annotation.name})

    parameters = {
        "relationship": relationship,
        "source_type": relationship.source_type,
        "destination_type": relationship.destination_type,
    }





    if annotation.side == RelationshipSideEnum.SOURCE:
        parameters["source_id"] = db_obj.id
        related_model_class = relationship.destination_type.model_class()
        try:
            destination_object = get_orm_object(related_model_class, related_model_dict)
            # destination_object = adapter.get_from_orm_cache(related_model_dict, related_model_class)
        except related_model_class.DoesNotExist as error:
            raise ObjectCrudException(
                f"Couldn't resolve custom relationship {relationship.name}, no such {related_model_class._meta.verbose_name} object with parameters {related_model_dict}."
            ) from error
        except related_model_class.MultipleObjectsReturned as error:
            raise ObjectCrudException(
                f"Couldn't resolve custom relationship {relationship.name}, multiple {related_model_class._meta.verbose_name} objects with parameters {related_model_dict}."
            ) from error
        RelationshipAssociation.objects.update_or_create(
            **parameters,
            defaults={"destination_id": destination_object.id},
        )
    else:
        parameters["destination_id"] = db_obj.id
        source_object = get_orm_object(relationship.source_type.model_class(), related_model_dict)
        #source_object = adapter.get_from_orm_cache(related_model_dict, relationship.source_type.model_class())
        RelationshipAssociation.objects.update_or_create(**parameters, defaults={"source_id": source_object.id})
