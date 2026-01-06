
# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from collections import defaultdict
from datetime import datetime
from typing import Annotated, List, Union, get_type_hints, get_args, ClassVar

from diffsync import DiffSyncModel
from diffsync.exceptions import ObjectCrudException, ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned, ValidationError
from django.db.models import ProtectedError, QuerySet
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, RelationshipAssociation
from nautobot.extras.models.metadata import ObjectMetadata
from functools import lru_cache
from nautobot_ssot.contrib.enums import AttributeType

from django.db.models import Model as ModelObj

from nautobot_ssot.contrib.base import BaseNautobotModel
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    CustomAnnotation,
)
from nautobot_ssot.contrib.enums import AttributeType


class ModelAttributeMethods:
    """"""
    
    _model: ClassVar[ModelObj]

    @classmethod
    @lru_cache
    def get_field(cls, attr_name: str):
        return cls._model._meta.get_field(attr_name)

    @classmethod
    @lru_cache
    def get_type_hints(cls) -> dict:
        """Return type hints for model class and use caching when doing so."""
        return get_type_hints(cls, include_extras=True)

    @classmethod
    @lru_cache
    def get_annotation(cls, attr_name: str):
        """Get attribute type hint annotation/metadata if found."""
        type_hints = cls.get_type_hints()[attr_name]
        for metadata in getattr(type_hints, "__metadata__", []):
            if isinstance(metadata, CustomAnnotation):
                return metadata
        return None

    @classmethod
    @lru_cache
    def get_attr_type(cls, attr_name: str):
        is_foreign_key = True if "__" in attr_name else False
        annotation = cls.get_annotation(attr_name)

        if isinstance(annotation, CustomFieldAnnotation):
            return AttributeType.CUSTOM_FIELD
        if is_foreign_key:
            if isinstance(annotation, CustomRelationshipAnnotation):
                return AttributeType.CUSTOM_FOREIGN_KEY
            return AttributeType.FOREIGN_KEY
        if annotation:
            return AttributeType.CUSTOM_N_TO_MANY_RELATIONSHIP
        db_field = cls.get_field(attr_name)
        if db_field.many_to_many or db_field.one_to_many:
            return AttributeType.N_TO_MANY_RELATIONSHIP
        return AttributeType.STANDARD