"""Utility functions and classes for use with the DiffSync library."""

from typing import List

from typing_extensions import get_type_hints, ClassVar, get_args, Union, Type, Any
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
    def get_attr_annotation(cls, attr_name: str) -> Any:
        """Get custom annotation from attribute metadata, if it exists. Returns None if attribute is missing or not annotated."""
        type_hints_dict = cls.get_type_hints()
        type_hints = type_hints_dict.get(attr_name)
        if type_hints is None:
            return None
        for metadata in getattr(type_hints, "__metadata__", []):
            if isinstance(metadata, CustomAnnotation):
                return metadata
        return None

    @classmethod
    @lru_cache
    def get_attr_type(cls, attr_name: str) -> Union[Type, None]:
        """Get attribute class type from attributes with annotated. Returns None if attribute is missing or not typed."""
        type_hints_dict = get_type_hints(cls, include_extras=True)
        type_hint = type_hints_dict.get(attr_name)
        if type_hint is None:
            return None
        try:
            return get_args(type_hint)[0]
        except (IndexError, TypeError):
            # Not an annotated type or no args
            if isinstance(type_hint, type):
                return type_hint
            return None
