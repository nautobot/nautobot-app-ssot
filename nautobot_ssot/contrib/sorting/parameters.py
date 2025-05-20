from abc import ABC, abstractmethod
from dataclasses import dataclass
from inspect import get_annotations

from typing_extensions import Annotated, List, get_args, get_origin

from nautobot_ssot.contrib.typeddicts import SortKey


@dataclass
class ParameterInterface(ABC):
    """Base class for sortable attribute types."""

    name: str

    @abstractmethod
    def __call__(self, input):
        """Call method for class to sort associated type."""


@dataclass
class SortListTypeWithDict(ParameterInterface):
    """Class for sorting lists of dictionaries."""

    sort_key: str

    def __call__(self, input):
        """Sort a list of dictionaries using specified sort key."""
        return sorted(
            input,
            key=lambda x: x[self.sort_key],
        )


def parameter_factory(name, type_hints):
    """Factory method for getting the correct sort class."""
    # Origin determines the first level of annotations.
    # If single type hint with no annotations or metadata (in square brackets), it returns None
    origin = get_origin(type_hints)
    args = list(get_args(type_hints))
    if origin == Annotated:
        # If annotated, get the origin of the first argument
        origin = get_origin(args.pop(0))

    if not origin:
        return None

    # Handle lists
    if origin in (list, List):
        if issubclass(args[0], dict):
            # Return Dict Parameter type
            # Content type should be first entry in args, pop it out
            content_type = args.pop(0)
            # Check if dict class has sort key specified
            for key_name, key_annotation in get_annotations(content_type).items():
                if get_origin(key_annotation) != Annotated:
                    continue
                if SortKey in get_args(key_annotation):
                    return SortListTypeWithDict(
                        name=name,
                        sort_key=key_name,
                    )
            # No sort key found for dictionary; nothing to sort
            return None

    # end if list type
    # Add other sort types here

    # If no sorting class found, return None
    return None
