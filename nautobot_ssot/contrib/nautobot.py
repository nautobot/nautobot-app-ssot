
"""Base model module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from collections import defaultdict
from datetime import datetime

from diffsync import DiffSyncModel
from diffsync.exceptions import ObjectCrudException, ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned, ValidationError
from django.db.models import ProtectedError, QuerySet
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, RelationshipAssociation
from nautobot.extras.models.metadata import ObjectMetadata
from nautobot_ssot.contrib.adapter import NautobotAdapter
from nautobot_ssot.contrib.base import BaseNautobotModel, BaseNautobotAdapter
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)
from nautobot_ssot.utils.diffsync import DiffSyncModelUtilityMixin
from nautobot.core.models import BaseModel as ORMModel


def update_or_create_custom_relationship_foreign_key(obj: ORMModel, related_model_dict : dict, annotation: CustomRelationshipAnnotation, adapter: NautobotAdapter):
    """"""
    relationship = adapter.get_from_orm_cache({"label": annotation.name}, Relationship)
    parameters = {
        "relationship": relationship,
        "source_type": relationship.source_type,
        "destination_type": relationship.destination_type,
    }
    defaults = {}
    if annotation.side == RelationshipSideEnum.SOURCE:
        parameters["source_id"] = obj.id
        defaults["destination_id"] = adapter.get_from_orm_cache(related_model_dict, relationship.destination_type.model_class()).id
    else:
        parameters["destination_id"] = obj.id
        defaults["source_id"] = adapter.get_from_orm_cache(related_model_dict, relationship.source_type.model_class()).id
    return RelationshipAssociation.objects.update_or_create(
        **parameters,
        defaults=defaults,
    )