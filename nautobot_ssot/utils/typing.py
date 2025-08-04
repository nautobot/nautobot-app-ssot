"""Utility functions related to `typing` and `typing_extensions` libraries."""

from typing import Type, get_args, get_type_hints


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
