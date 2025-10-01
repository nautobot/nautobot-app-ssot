
# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from typing import List

from typing_extensions import get_type_hints
from typing import Any

from typing import Union
from nautobot_ssot.contrib.types import CustomAnnotation, CustomFieldAnnotation, CustomRelationshipAnnotation
from typing import ClassVar, Type
from functools import lru_cache
from django.db.models import Model
from dataclasses import dataclass
from nautobot_ssot.contrib.enums import AttributeType


class ModelAttributeMethodsMixin:
    """A collection of methods to use with Nautobot Models for retrieiving attribute data."""

    _model: ClassVar[Model]

    @classmethod
    @lru_cache
    def get_type_hints(cls, include_extras=True) -> dict:
        """Get class type hints using cache."""
        return get_type_hints(cls, include_extras=include_extras)

    @classmethod
    @lru_cache
    def get_attr_metadata(cls, attr_name: str) -> List[Any]:
        """Get attribute metadata from class type hints using cache."""
        return getattr(cls.get_type_hints()[attr_name], "__metadata__", [])

    @classmethod
    @lru_cache
    def get_attr_custom_annotation(cls, attr_name: str) -> Union[CustomAnnotation, None]:
        """Get the CustomAnnotation instance from metadata, if present, and cache result."""
        for metadata in cls.get_attr_metadata(attr_name):
            if isinstance(metadata, CustomAnnotation):
                return metadata
        return None

    @classmethod
    @lru_cache
    def get_attribute_type(cls, attr_name: str) -> AttributeType:
        """Get the attribute type for a given attribute."""
        custom_annotation = cls.get_attr_custom_annotation(attr_name)
        is_foreign_key = "__" in attr_name

        if isinstance(custom_annotation, CustomFieldAnnotation):
            return AttributeType.CUSTOM_FIELD
        elif is_foreign_key and custom_annotation:
            return AttributeType.CUSTOM_FOREIGN_KEY
        elif is_foreign_key:
            return AttributeType.FOREIGN_KEY
        elif custom_annotation:
            return AttributeType.CUSTOM_TO_MANY_RELATIONSHIP

        db_field = cls._model._meta.get_field(attr_name)

        if db_field.many_to_many:
            return AttributeType.MANY_TO_MANY_RELATIONSHIP
        elif db_field.one_to_many:
            return AttributeType.ONE_TO_MANY_RELATIONSHIP
        return AttributeType.STANDARD
