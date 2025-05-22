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

from typing_extensions import List

from nautobot_ssot.contrib.sorting.helpers import get_dict_sort_key, get_attribute_origin_and_args

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

def sort_attribute_factory(name, type_hints):
    """Factory method for getting the correct sort class."""
    # Origin determines the first level of annotations.
    # If single type hint with no annotations or metadata (in square brackets), it returns None
    origin, args = get_attribute_origin_and_args(type_hints)

    if origin in (list, List):
        return _factory_list_types(name, args)
    # Add other sort types here

    # If no sorting class found, return None
    return None
