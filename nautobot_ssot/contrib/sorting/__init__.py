"""Contrib sorting module."""

from diffsync import Adapter
from nautobot_ssot.contrib.sorting.models import ModelSortingInterface
from nautobot_ssot.contrib.sorting.parameters import ParameterInterface
from typing_extensions import List



def _sort_diffsync_instance(diffsync_obj, sortable_params: dict[str, ParameterInterface]):
    """Sort all parameters in DiffSync instance."""
    for parameter_name, parameter_sorter in sortable_params.items():
        setattr(
            diffsync_obj,
            parameter_name,
            parameter_sorter(getattr(diffsync_obj, parameter_name))
        )
    return diffsync_obj


def _sort_adapter(adapter: Adapter, models_to_sort: List[ModelSortingInterface]):
    """"""
    # Loop Through Models
    for model_sorting_class in models_to_sort:
        for diffsync_obj in adapter.get_all(model_sorting_class.model_class):
            sorted_obj = _sort_diffsync_instance(
                diffsync_obj,
                model_sorting_class.sortable_parameters,
            )
            adapter.update(sorted_obj)
    return adapter


def _get_sorting_class(adapter, model_name):
    """"""
    try:
        sorting_class = ModelSortingInterface(
            model_class=getattr(adapter, model_name)
        )
    except AttributeError:
        return None
    return sorting_class


def sort_relationships(source: Adapter, target: Adapter):
    """Sort relationships for given source and target adapters."""
    models_to_sort = []
    for model_name in target.top_level:
        if sorting_class := _get_sorting_class(target, model_name):
            models_to_sort.append(sorting_class)
            #models_to_sort[model_name] = sorting_class

    for diffsync_adapter in (source, target):
        _sort_adapter(diffsync_adapter, models_to_sort)
