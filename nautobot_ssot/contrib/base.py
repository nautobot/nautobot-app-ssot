"""Abstract base classes for primary contrib module classes.

NOTE: Classes in this file should not have any implementation.

These base classes are meant to define the expected interactions between the various classes
within contrib to allow for additional customization and extension based on individual needs.

Althought the contrib module provides helpful functionality that cuts for most use cases, significantly
cutting down development time, not every integration of SSoT will will use both `NautobotModel` and `NautobotAdapter`.

As such, we must identify the requirements and expectations each class has on the other in addition to
the attributes and methods in the parent classes. The intent is any SSoT integration using one contrib
class, but not the other, can inherit from the associated class in their custom definition to ensure the
contrib-provided class can properly interact without raising errors.
"""
from nautobot_ssot.contrib.enums import AttributeType

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional
from uuid import UUID

from diffsync import DiffSyncModel
from django.db.models import Model, QuerySet
from nautobot.extras.jobs import BaseJob
from nautobot.extras.models.metadata import MetadataType
from nautobot_ssot.contrib.mixins import ModelAttributeMethods
from diffsync import Adapter, DiffSyncModel
from nautobot_ssot.utils.cache import ORMCache

from functools import lru_cache
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    CustomAnnotation,
)

from typing import get_args, get_type_hints, ClassVar
from nautobot_ssot.utils.typing import get_inner_type

class BaseNautobotAdapter(ABC):
    """Abstract Base Class for `NautobotAdapter`."""

    cache: ORMCache
    job: BaseJob
    metadata_type: MetadataType
    metadata_scope_fields: dict[DiffSyncModel, list]


class BaseNautobotModel():
    """Abstract Base Class for `NautobotModel`."""

    _model: ClassVar[Model]
    _type_hints: ClassVar[dict[str, Any]]
    adapter: Optional[BaseNautobotAdapter]

    # DB Object Attributes
    pk: Optional[UUID] = None  # For storing and tracking ORM object primary keys. Not synced.

    @classmethod
    @abstractmethod
    def get_synced_attributes(cls) -> list[str]:
        """Abstract method for returning a list of all attributes synced during the SSoT process."""

    @classmethod
    @abstractmethod
    def _get_queryset(cls) -> QuerySet:
        """Abstract method for retreiving data from Nautobot about associated model."""





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
    def get_inner_type(cls, attr_name: str):
        try:
            return get_args(get_type_hints(cls)[attr_name])[0]
        except IndexError as err:
            return None
            #raise TypeError("Class attribute does not have inner type defined.") from err
        except KeyError as err:
            return None
            #raise AttributeError(f"type object '{cls}' has no attribute '{attr_name}'") from err

        try:
            return get_inner_type(cls, attr_name)
        except AttributeError:
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
