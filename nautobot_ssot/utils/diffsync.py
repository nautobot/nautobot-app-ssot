"""Utility functions and classes for use with the DiffSync library."""

from functools import lru_cache
from typing import Annotated, ClassVar, Union, get_args, get_origin, get_type_hints

from nautobot_ssot.contrib.types import CustomAnnotation
from nautobot_ssot.utils.typing import get_inner_type

class DiffSyncModelUtilityMixin:
    """A `DiffSyncModel` utility mixin providing extended functionality to more easily get the data you need.

    Note:
        - This mixin acts only on attributes and methods found in `diffsync.DiffSyncModel`.
        - Class vars included in this mixin class mirror the `DiffSyncModel` class for type local hinting purposes only.
        - All methods expect that attribute names exist and are type-annotated; missing attributes will raise KeyError.
    """

    _identifiers: ClassVar[tuple]
    _attributes: ClassVar[tuple]

    @classmethod
    def get_synced_attributes(cls) -> list[str]:
        """Return a list of parameters synced as part of the SSoT Process.

        Returns:
            list[str]: All identifiers and attributes to be synced.
        """
        return list(cls._identifiers) + list(cls._attributes)

    @classmethod
    @lru_cache
    def get_type_hints(cls) -> dict[str, type]:
        """Return cached type hints for this model class, including extras (annotations).

        Returns:
            dict[str, type]: Mapping of attribute names to their type hints.
        """
        return get_type_hints(cls, include_extras=True)

    @classmethod
    @lru_cache
    def get_attr_args(cls, attr_name: str) -> tuple:
        """Get type arguments for the given attribute's type hint.

        Args:
            attr_name (str): Attribute name.

        Returns:
            tuple: Type arguments for the attribute's type hint.
        """
        return get_args(cls.get_type_hints()[attr_name])

    @classmethod
    @lru_cache
    def get_attr_annotation(cls, attr_name: str) -> Union[CustomAnnotation, None]:
        """Get custom annotation from attribute metadata, else None.

        Args:
            attr_name (str): Attribute name.

        Returns:
            Any: Custom annotation instance or None.
        """
        # Looping through args vs. returning static index ensures getting the annotation in the instance it's not in the [1] position.
        attr_args = cls.get_attr_args(attr_name)
        if attr_args and attr_args[0].__name__ in ["Annotated", "Optional"]:
            # When nested, we combine the metadata between the first and second levels to search for annotations.
            attr_args = list(attr_args) + list(get_args(attr_args[0]))
        for metadata in attr_args:
            if isinstance(metadata, CustomAnnotation):
                return metadata
        return None

    @classmethod
    @lru_cache
    def get_attr_type(cls, attr_name: str) -> type:
        """Get class type of specified attribute.

        Returns inner type if attribute is `Optional` and/or `Annotated`.
        
        Args:
            attr_name (str): Attribute name.

        Returns:
            type: The class type of the attribute.
        """
        attr_hints = cls.get_attr_args(attr_name)
        if not attr_hints:
            # Empty args means there are no annotations to decipher
            return cls.get_type_hints()[attr_name]
        while attr_hints[0].__name__ in ["Optional", "Annotated"]:
            attr_hints = get_args(attr_hints[0])
        return attr_hints[0]
