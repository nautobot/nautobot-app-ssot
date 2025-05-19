"""Sorting class for handling sorting in DiffSync models during SSoT."""

from dataclasses import dataclass, field
from diffsync import DiffSyncModel
from inspect import get_annotations
from typing_extensions import TypedDict, Annotated, get_args, get_origin, Tuple, get_type_hints, List
# from nautobot_ssot.contrib.sorting.parameters import parameter_factory, ParameterInterface
from temp import parameter_factory, BaseParameter as ParameterInterface, MyDiff



@dataclass
class ModelSortingInterface:
    """Sorting class for sorting attributes within source and target adapters.
    
    Step 1: Determine sortable attributes in __post_init__
    Step 2: 
    """

    model_class: DiffSyncModel
    type_hints: dict = field(init=False, repr=False)
    sortable_parameters: dict[str, ParameterInterface] = field(init=False)

    def __post_init__(self):
        """"""
        self.type_hints = get_type_hints(self.model_class, include_extras=True)
        self.sortable_parameters = {}
        self.load_parameters()

    def load_parameters(self):
        """Load """
        for attribute in self.model_class._attributes:
            parameter_sorter = parameter_factory(
                attribute,
                self.type_hints[attribute]
            )
            if not parameter_sorter:
                continue
            self.sortable_parameters[attribute] = parameter_sorter
