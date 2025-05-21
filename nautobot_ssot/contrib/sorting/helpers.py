"""Helper functions for SSoT sorting."""

from nautobot_ssot.contrib.typeddicts import SortKey
from inspect import get_annotations
from typing_extensions import Annotated, get_origin, get_args

def get_dict_sort_key(dict_type: type):
    """Get sort key, if any, from specified dictionary type.
    
    Sort keys are identified by annotating the field in TypedDict objects.
    """
    if not issubclass(dict_type, dict):
        raise TypeError(f"`dict_type` parameter must be subclass of `dict`, got `{dict_type}`.")
    for key_name, key_annotation in get_annotations(dict_type).items():
        if get_origin(key_annotation) != Annotated:
            # We only care about annotated fields
            continue
        if SortKey in get_args(key_annotation):
            return key_name
    return None




