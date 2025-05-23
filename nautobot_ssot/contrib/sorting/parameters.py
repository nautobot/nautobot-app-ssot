"""Dataclasses for sorting parameters.

Parameter classes here are focused on identifying different types of sortable attributes and
contain the functionality and data to sort them when the class is called.


Naming Convention:
    Each final class should be named "Sort" + data type that is being sorted. For example,
    a sorting class that sorts a list of dictionaries would be `SortListTypeWithDict` as
    demonstrated in the class below.
    - Starts with "Sort"
    - Specifies primary data type with `ListType`
    - Specifies contents of primary data type with `WithDict`
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from typing_extensions import List, is_typeddict, Any, get_type_hints
from typing import _GenericAlias, TypeAlias
from nautobot_ssot.contrib.sorting.helpers import get_attribute_origin_and_args, get_dict_sort_key

@dataclass
class SortAttributeInterface(ABC):
    """Base class for sortable attribute types."""

    name: str

    @abstractmethod
    def __call__(self, data):
        """Call method for class to sort associated type."""


@dataclass
class SortListTypeWithDict(SortAttributeInterface):
    """Class for sorting lists of dictionaries."""

    sort_key: str

    def __call__(self, data):
        """Sort a list of dictionaries using specified sort key."""
        if not isinstance(data, list) or not isinstance(data[0], dict):
            raise TypeError(f"Invalid input. List of dictionaries required, got `{data.__class__}`.")
        return sorted(
            data,
            key=lambda x: x[self.sort_key],
        )


def _factory_list_types(name, args):
    """Function for getting sorting class for list types.

    Currently only returns a sorting class if:
    - List content type is a subclass of a dictionary
    - Dictionary is a `TypedDict` with `SortKey` specified in one of the keys
    """
    list_content_type = args.pop(0)

    # List of dictionaries
    if issubclass(list_content_type, dict):
        # Return Dict Parameter type
        # Content type should be first entry in args, pop it out
        if sort_key := get_dict_sort_key(list_content_type):
            return SortListTypeWithDict(
                name=name,
                sort_key=sort_key,
            )
    # Standard lists not needed right now, only lists of dictionaries.
    return None


def sorting_attribute_factory(attr_name: str, attr_type_hints: Any ):
    """Factory method for getting the correct sort class.
    
    TODO: Verify variations in type_hints input and add check for it
    """
    if not isinstance(attr_name, str):
        raise TypeError(f"Attribute name must be a string, got {attr_name.__class__}")
    if " " in attr_name:
        raise ValueError(f"Attribute names cannot have spaces, got `{attr_name}`.")
    # Origin determines the first level of annotations.
    # If single type hint with no annotations or metadata (in square brackets), it returns None
    origin, args = get_attribute_origin_and_args(attr_type_hints)

    if origin in (list, List):
        return _factory_list_types(attr_name, args)
    # Add other sort types here

    # If no sorting class found, return None
    return None
