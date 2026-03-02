"""Utility functions and classes for use with the DiffSync library."""

from typing import List

from typing import get_type_hints, ClassVar, get_args, Type, Any, get_origin, Tuple, Annotated
from nautobot_ssot.contrib.types import CustomAnnotation
from functools import lru_cache


class DiffSyncModelUtilityMixin:
    """A `DiffSyncModel` utility mixin providing extended functionality to more easily get the data you need.

    NOTE: This mixin acts only on attributes and methods found in `diffsync.DiffSyncModel`. Class vars included
          in this mixin class mirror the `DiffSyncModel` class for type local hinting purposes only.
    """

    _identifiers: ClassVar[tuple]
    _attributes: ClassVar[tuple]

    @classmethod
    def get_synced_attributes(cls) -> List[str]:
        """Return a list of parameters synced as part of the SSoT Process."""
        return list(cls._identifiers) + list(cls._attributes)

    @classmethod
    @lru_cache
    def get_type_hints(cls) -> dict[str, type]:
        """Return cached type hints for this model class."""
        return get_type_hints(cls, include_extras=True)

    @classmethod
    @lru_cache
    def get_attr_args(cls, attr_name: str) -> Tuple:
        return get_args(cls.get_type_hints()[attr_name])

    @classmethod
    @lru_cache
    def get_attr_annotation(cls, attr_name: str) -> Any:
        """Get custom annotation from attribute metadata, if it exists. Returns None if attribute is missing or not annotated."""
        # Looping through args vs. returning static index ensures getting the annotation in the instance it's not in the [1] position.
        for metadata in cls.get_attr_args(attr_name):
            if isinstance(metadata, CustomAnnotation):
                return metadata
        return None

    @classmethod
    @lru_cache
    def is_attr_annotated(cls, attr_name: str) -> bool:
        """"""
        return get_origin(cls.get_type_hints()[attr_name]) in [Annotated]

    @classmethod
    @lru_cache
    def get_attr_type(cls, attr_name: str) -> Type:
        """Get class type of specified attribute.

        NOTE: If attribute is `Annotated`, we return the inner type, not `Annotated`.
        """
        if cls.is_attr_annotated(attr_name):
            return cls.get_attr_args(attr_name)[0]
        return cls.get_type_hints()[attr_name]
