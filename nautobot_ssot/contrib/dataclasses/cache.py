"""Caching classes for use in SSoT processes."""

from collections import defaultdict
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from typing_extensions import DefaultDict, Dict, FrozenSet, Hashable, Tuple, Type

# This type describes a set of parameters to use as a dictionary key for the cache. As such, its needs to be hashable
# and therefore a frozenset rather than a normal set or a list.
#
# The following is an example of a parameter set that describes a tenant based on its name and group:
# frozenset(
#  [
#   ("name", "ABC Inc."),
#   ("group__name", "Customers"),
#  ]
# )
ParameterSet = FrozenSet[Tuple[str, Hashable]]


@dataclass
class ORMCache:
    """Caching class for use in `NautobotAdapter` when interacting with the database."""

    cache: DefaultDict[str, Dict[ParameterSet, Model]] = field(init=False, repr=False)
    cache_hits: DefaultDict[str, int] = field(init=False)

    def __post_init__(self):
        """Post initialization of the class."""
        self.invalidate_cache()

    def invalidate_cache(self, zero_out_hits=True):
        """Invalidates all the objects in the ORM cache."""
        self.cache = defaultdict(dict)
        if zero_out_hits:
            self.cache_hits = defaultdict(int)

    def get_from_orm_cache(self, parameters: Dict, model_class: Type[Model]):
        """Retrieve an object from the ORM or the cache."""
        parameter_set = frozenset(parameters.items())
        content_type = ContentType.objects.get_for_model(model_class)
        model_cache_key = f"{content_type.app_label}.{content_type.model}"
        if cached_object := self.cache[model_cache_key].get(parameter_set):
            self.cache_hits[model_cache_key] += 1
            return cached_object

        # As we are using `get` here, this will error if there is not exactly one object that corresponds to the
        # parameter set. We intentionally pass these errors through.
        self.cache[model_cache_key][parameter_set] = model_class.objects.get(**dict(parameter_set))
        return self.cache[model_cache_key][parameter_set]
