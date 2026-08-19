"""Utility functions related to `typing` and `typing_extensions` libraries."""

from dataclasses import dataclass
from typing import (
    Type, 
    get_args, 
    get_type_hints, 
    Annotated, 
    _AnnotatedAlias,
    get_args,
    is_typeddict,
    Dict,
    _type_repr,
    _is_unpacked_typevartuple,
    _type_check,
    Iterable,
    Any,
    _tp_cache,
)
import operator


def get_inner_type(class_type: Type, attribute_name: str):
    """Get inner type of a class attribute with a type and inner type defined.

    Args:
        class_type (Type): Class type with defined class attributes containing type hints.
        attribute_name (str): Name of class attribute with type and inner type defined.

    Returns:
        Type: Returns inner type of provided attribute name.

    Raises:
        TypeError: Raised when type hints for attribute do not contain defined inner type.
        AttributeError: Raised when class type does not have specified attribute.

    Example:
        Given `TypedDict` class `DeviceDict`.

        ```python

        class LocationModel(NautobotModel):
            devices: List[DeviceDict] = []

        print(get_inner_type(LocationModel, "devices"))

        > DeviceDict
        ```
    """
    try:
        return get_args(get_type_hints(class_type)[attribute_name])[0]
    except IndexError as err:
        raise TypeError("Class attribute does not have inner type defined.") from err
    except KeyError as err:
        raise AttributeError(f"type object '{class_type}' has no attribute '{attribute_name}'") from err


@dataclass
class SortKey:
    """Dataclass for `SortedList` to identify a sort key in lists of dictionaries."""

    key: str


class SortedListAlias(_AnnotatedAlias, _root=True):
    """"""

    def __init__(self, origin, metadata):
        if isinstance(origin, SortedListAlias):
            metadata = origin.__metadata__ + metadata
            origin = origin.__origin__
        super().__init__(origin, origin)
        self.__metadata__ = metadata

    def __repr__(self):
        if len(self.__metadata__) >= 1:
            return "nautobot_ssot.utils.typing.SortedList[{}, {}]".format(
                _type_repr(self.__origin__),
                ", ".join(repr(a) for a in self.__metadata__)
            )
        return "nautobot_ssot.utils.typing.SortedList[{}]".format(_type_repr(self.__origin__))

    def __reduce__(self):
        return operator.getitem, (
            Annotated, (self.__origin__,) + self.__metadata__
        )

    def __eq__(self, other):
        if not isinstance(other, SortedListAlias):
            return NotImplemented
        return (self.__origin__ == other.__origin__
                and self.__metadata__ == other.__metadata__)

    def __getattr__(self, attr):
        if attr in {'__name__', '__qualname__'}:
            return 'SortedList'
        return super().__getattr__(attr)


class SortedList(list):
    """"""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        raise TypeError("Type SortedList cannot be instantiated.")

    @classmethod
    def _get_sort_key(cls, metadata: Iterable):
        for data in metadata:
            if isinstance(data, SortKey):
                return data
        return None
    
    def __class_getitem__(cls, params):
        if not isinstance(params, tuple):
            params = (params,)
        return cls._class_getitem_inner(cls, *params)

    @_tp_cache(typed=True)
    def _class_getitem_inner(cls, *params):
        """"""
        origin = _type_check(params[0], "SortedList[t, ...]: t must be a type.", allow_special_forms=True)

        metadata = tuple(params[1:])
        sort_key = cls._get_sort_key(metadata)
        is_dict = is_typeddict(origin) or origin in [dict, Dict]
        
        if _is_unpacked_typevartuple(params[0]):
            raise TypeError("SortedList[...] should not be used with an unpacked TypeVarTuple")
        if not is_dict and sort_key:
            raise TypeError("SortedList[...], `SortKey` metadata only used with `[dict|Dict|TypedDict]` types.")
        if is_dict and not sort_key:
            raise TypeError("SortedList[...] with `dict` or `TypedDict` type must have a `SortKey`.")
        elif not is_dict and sort_key:
            raise TypeError("SortedList[...] without `dict` or `TypedDict` type should not have `SortKey`.")

        return SortedListAlias(origin, metadata)

    def __init_subclass__(cls):
        raise TypeError("Cannot subclass {}.SortedList".format(cls.__module__))
