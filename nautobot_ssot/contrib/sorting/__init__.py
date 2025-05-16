"""Functions for sorting DiffSync model lists ensuring they are sorted to prevent false actions."""

import sys

from diffsync import Adapter, DiffSyncModel
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.typeddicts import SortKey
from nautobot_ssot.contrib.types import SortType


def _is_sortable_field(attribute_type_hints) -> bool:
    """Check if a DiffSync attribute is a sortable field."""
    minor_ver = sys.version_info[1]
    try:
        # For Python 3.9 and older
        if minor_ver <= 9:
            attr_name = attribute_type_hints._name  # pylint: disable=protected-access
        else:
            attr_name = attribute_type_hints.__name__
    except AttributeError:
        return False

    return str(attr_name) in [
        "list",
        "List",
    ]


def get_sort_key_from_typed_dict(sortable_content_type) -> str:
    """Get the dictionary key from a TypedDict if found."""
    try:
        annotations: dict = sortable_content_type.__annotations__
    except AttributeError:
        # If no annotations, no sort key set
        return None

    for key, value in annotations.items():
        if not hasattr(value, "__metadata__"):
            continue
        for entry in value.__metadata__:
            if entry == SortKey:
                return key
    return None


def get_sortable_fields_from_model(model: DiffSyncModel) -> dict:
    """Get a list of sortable fields and their sort key from a DiffSync model."""
    sortable_fields = {}
    model_type_hints = get_type_hints(model, include_extras=True)

    for model_attribute_name in model._attributes:  # pylint: disable=protected-access
        attribute_type_hints = model_type_hints.get(model_attribute_name)

        if not _is_sortable_field(attribute_type_hints):
            continue

        sortable_content_type = attribute_type_hints.__args__[0]

        if issubclass(sortable_content_type, dict):
            sort_key = get_sort_key_from_typed_dict(sortable_content_type)
            if not sort_key:
                continue
            sortable_fields[model_attribute_name] = {
                "sort_type": SortType.DICT,
                "sort_key": sort_key,
            }
        # Add additional items here

    return sortable_fields


def _sort_dict_attr(obj, attribute, key):
    """Update the sortable attribute in a DiffSync object."""
    sorted_data = None
    if key:
        sorted_data = sorted(
            getattr(obj, attribute),
            key=lambda x: x[key],
        )
    else:
        sorted_data = sorted(getattr(obj, attribute))

    if sorted_data:
        setattr(obj, attribute, sorted_data)
    return obj


def sort_relationships(source: Adapter, target: Adapter):
    """Sort relationships based on the metadata defined in the DiffSync model."""
    if not source or not target:
        return

    models_to_sort = {}
    # Loop through target's top_level attribute to determine models with sortable attributes
    for model_name in getattr(target, "top_level", []):
        # Get the DiffSync Model
        diffsync_model = getattr(target, model_name)
        if not diffsync_model:
            continue

        # Get sortable fields current model
        model_sortable_fields = get_sortable_fields_from_model(diffsync_model)
        if not model_sortable_fields:
            continue
        models_to_sort[model_name] = model_sortable_fields

    # Loop through adapaters to sort models
    for adapter in (source, target):
        for model_name, attrs_to_sort in models_to_sort.items():
            for diffsync_obj in adapter.get_all(model_name):
                for attr_name, sort_data in attrs_to_sort.items():
                    sort_type = sort_data["sort_type"]
                    # Sort the data based on its sort type
                    if sort_type == SortType.DICT:
                        diffsync_obj = _sort_dict_attr(diffsync_obj, attr_name, sort_data["sort_key"])
                adapter.update(diffsync_obj)
