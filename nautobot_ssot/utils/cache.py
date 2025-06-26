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
    """Basic caching class for use in `NautobotAdapter` and other tools when interacting with the database."""

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

    def hits(self, cache_key: str):
        """Get number of hits for specified cache key."""
        return self.cache_hits.get(cache_key, None)

    def get_from_orm(self, model_class: Type[Model], parameters: Dict):
        """Retrieve an object from the ORM or the cache."""
        parameter_set = frozenset(parameters.items())
        content_type = ContentType.objects.get_for_model(model_class)
        model_cache_key = f"{content_type.app_label}.{content_type.model}"

        # Check for keys in dictionaries directly to avoid false results of searching in cache.
        if model_cache_key in self.cache.keys():
            if parameter_set in self.cache[model_cache_key].keys():
                self.cache_hits[model_cache_key] += 1
                return self.cache[model_cache_key][parameter_set]

        # As we are using `get` here, this will error if there is not exactly one object that corresponds to the
        # parameter set. We intentionally pass these errors through.
        self.cache[model_cache_key][parameter_set] = model_class.objects.get(**dict(parameter_set))
        self.cache_hits[model_cache_key] = 0

        return self.cache[model_cache_key][parameter_set]
