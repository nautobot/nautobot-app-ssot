"""Sorting class for handling sorting in DiffSync models during SSoT."""

from dataclasses import dataclass, field

from diffsync import DiffSyncModel
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.sorting.parameters import ParameterInterface, parameter_factory


@dataclass
class ModelSortingInterface:
    """Sorting class for sorting attributes within source and target adapters."""

    model_class: DiffSyncModel
    type_hints: dict = field(init=False, repr=False)
    sortable_parameters: dict[str, ParameterInterface] = field(init=False)

    def __post_init__(self):
        """Initialize the class."""
        self.type_hints = get_type_hints(self.model_class, include_extras=True)
        self.sortable_parameters = {}
        self.load_parameters()

    @property
    def name(self):
        """Return name of model class."""
        return self.model_class.__name__

    @property
    def has_sortable_parameters(self):
        """Check if there are any sortable parameters."""
        if len(self.sortable_parameters.keys()) > 0:
            return True
        return False

    def load_parameters(self):
        """Load sortable parameters to class."""
        for attribute in self.model_class._attributes:  # pylint: disable=protected-access
            parameter_sorter = parameter_factory(attribute, self.type_hints[attribute])
            if not parameter_sorter:
                continue
            self.sortable_parameters[attribute] = parameter_sorter



# deftemp = {
#     'model_class': <class 'nautobot_ssot.tests.contrib.sorting.objects.SimpleNautobotDevice'>, 
#     'type_hints': {
#         '_modelname': typing.ClassVar[str], 
#         '_identifiers': typing.ClassVar[typing.Tuple[str, ...]], 
#         '_shortname': typing.ClassVar[typing.Tuple[str, ...]], 
#         '_attributes': typing.ClassVar[typing.Tuple[str, ...]], 
#         '_children': typing.ClassVar[typing.Dict[str, str]], 
#         'model_flags': <flag 'DiffSyncModelFlags'>, 
#         'adapter': typing.Optional[diffsync.Adapter],
#         '_status': <enum 'DiffSyncStatus'>, 
#         '_status_message': <class 'str'>, 
#         '_model': typing.ClassVar[django.db.models.base.Model], 
#         'pk': typing.Optional[uuid.UUID], 'name': <class 'str'>, 
#         'interfaces': typing.List[nautobot_ssot.tests.contrib.sorting.objects.SortableInterfaceDict], 
#         'module_bays': typing.List[dict], 'description': typing.Optional[str]
#     }, 
#     'sortable_parameters': {
#         'interfaces': SortListTypeWithDict(name='interfaces', sort_key='name')
#     }
# }