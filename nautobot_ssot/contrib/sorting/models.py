"""Sorting class for handling sorting in DiffSync models during SSoT."""

from dataclasses import dataclass, field

from diffsync import DiffSyncModel
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.sorting.parameters import ParameterInterface, parameter_factory


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
        """Load sortable parameters to class."""
        for attribute in self.model_class._attributes:  # pylint: disable=protected-access
            parameter_sorter = parameter_factory(attribute, self.type_hints[attribute])
            if not parameter_sorter:
                continue
            self.sortable_parameters[attribute] = parameter_sorter
