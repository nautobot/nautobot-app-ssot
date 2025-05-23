"""Sorting class for handling sorting in DiffSync models during SSoT."""

from dataclasses import dataclass, field

from diffsync import DiffSyncModel
from typing_extensions import Dict, List, get_type_hints

from nautobot_ssot.contrib.sorting.parameters import SortAttributeInterface, sorting_attribute_factory


@dataclass
class SortModelInterface:
    """Sorting class for sorting attributes within source and target adapters."""

    model_class: DiffSyncModel
    type_hints: Dict = field(init=False, repr=False)
    sortable_parameters: List[SortAttributeInterface] = field(init=False)

    def __post_init__(self):
        """Initialize the class."""
        if not issubclass(self.model_class, DiffSyncModel):
            raise TypeError("`model_class` attribute must be subclass type of `DiffSyncModel`.")

        self.type_hints = get_type_hints(self.model_class, include_extras=True)
        self.sortable_parameters = []
        self.load_parameters()

    @property
    def name(self):
        """Return name of model class."""
        return self.model_class.__name__

    @property
    def has_sortable_parameters(self):
        """Check if there are any sortable parameters."""
        # if len(self.sortable_parameters.keys()) > 0:
        if self.sortable_parameters.count() > 0:
            return True
        return False

    def load_parameters(self):
        """Load sortable parameters to class."""
        for attribute in self.model_class._attributes:  # pylint: disable=protected-access
            parameter_sorter = sorting_attribute_factory(
                attribute,
                self.type_hints[attribute]
            )
            if not parameter_sorter:
                continue
            self.sortable_parameters.append(parameter_sorter)
