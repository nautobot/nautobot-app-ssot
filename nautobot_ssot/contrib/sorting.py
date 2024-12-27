""""""

from typing import Annotated
#from typing_extensions import get_type_hints
#from dataclasses import dataclass
from pprint import pprint
from typing import List, Optional, TypedDict
import typing
from enum import Enum
from typing_extensions import get_type_hints
from nautobot_ssot.contrib.types import FieldType
from diffsync import Adapter, DiffSyncModel


def _is_sortable_field(attribute_type_hints):
    """Checks type hints to verify if field labled as sortable or not."""
    if attribute_type_hints.__name__ != "Annotated" or \
            not hasattr(attribute_type_hints, "__metadata__"):
        return False
    for metadata in attribute_type_hints.__metadata__:
        if metadata == FieldType.SORTED_FIELD:
            return True
    return False


def _get_sortable_obj_type(attribute_type_hints):
    """"""
    attr_type = attribute_type_hints.__args__[0]
    attr_type_args = getattr(attr_type, "__args__")
    if attr_type_args:
        return attr_type_args[0]
    return None


def _get_sortable_obj_sort_key(sortable_obj_type):
    """"""
    content_obj_type_hints = get_type_hints(sortable_obj_type, include_extras=True)
    for key, value in content_obj_type_hints.items():
        if not value.__name__ == "Annotated":
            continue
        for metadata in getattr(value, "__metadata__", ()):
            if metadata == FieldType.SORT_BY:
                return key
    return None


def _get_sortable_fields_from_model(model):
    """"""
    sortable_fields = []
    model_type_hints = get_type_hints(model, include_extras=True)

    for attribute_name in model._attributes:
        attribute_type_hints = model_type_hints.get(attribute_name)
        if not _is_sortable_field(attribute_type_hints):
            continue
        
        sortable_obj_type = _get_sortable_obj_type(attribute_type_hints)
        sort_key = _get_sortable_obj_sort_key(sortable_obj_type)

        sortable_fields.append({
            "attribute": attribute_name,
            "sort_key": sort_key,
        })
    return sortable_fields
        

def sort_relationships(source: Adapter, target: Adapter):
    """Sort relationships based on the metadata defined in the DiffSync model."""
    if not isinstance(source, Adapter) or not isinstance(target, Adapter):
        raise TypeError("Parameters for `sort_relationships()` must be of type DiffSync.")

    # Loop through Top Level entries
    for level in target.top_level:
        # Get the DiffSync Model
        model = getattr(target, level)
        if not model:
            continue

        # Get sortable fields from model
        sortable_fields = _get_sortable_fields_from_model(target)
        if not sortable_fields:
            continue

        for sortable in sortable_fields:
            attribute = sortable["attribute"]
            key = sortable["sort_key"]

            #source_items = source.get_all(attribute)
            #target_items = target.get_all(attribute)
            
            for adapter in (source, target):
                for obj in adapter.get_all(attribute):
                    if key:
                        sorted_data = sorted(
                            getattr(obj, attribute),
                            key=lambda x: x[key],
                        )
                    else:
                        sorted_data = sorted(
                            getattr(obj, attribute)
                        )
                    setattr(obj, attribute, sorted_data)
                    adapter.update(obj)
        # end for


        
        