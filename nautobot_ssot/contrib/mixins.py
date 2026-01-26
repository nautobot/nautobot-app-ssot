""""""

from typing import get_args, get_type_hints, ClassVar
from nautobot_ssot.utils.typing import get_inner_type


from functools import lru_cache
from nautobot_ssot.contrib.enums import AttributeType

from django.db.models import Model as ModelObj

from nautobot_ssot.contrib.annotations import (
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
    def get_inner_type(cls, attr_name: str):
        try:
            return get_args(get_type_hints(cls)[attr_name])[0]
        except IndexError as err:
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
