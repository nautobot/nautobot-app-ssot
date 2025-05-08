"""Helper classes for caching in SSoT jobs."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, FrozenSet, Hashable, Tuple, Type

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from nautobot_ssot.contrib.exceptions import CachedObjectAlreadyExists, CachedObjectNotFound

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


class BasicCache:
    """Basic, reusable caching class for adapters."""

    _cache: DefaultDict[Hashable, Dict[Hashable, Any]]
    _cache_hits: DefaultDict[str, int] = defaultdict(int)

    def __init__(self, invalidate_on_init: bool = True, *args, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        if invalidate_on_init:
            self.invalidate_cache()

    def invalidate_cache(self, zero_out_hits=True):
        """Invalidates all the objects in the ORM cache."""
        self._cache = defaultdict(dict)
        if zero_out_hits:
            self._cache_hits = defaultdict(int)

    def total_hits(self, object_type_key):
        """Get total cache hits for an object type."""
        return self._cache_hits.get(object_type_key)

    def get(self, object_type_key, object_key):
        """Get object from cache."""
        if cached_object := self._cache[object_type_key].get(object_key):
            self._cache_hits[object_type_key] += 1
            return cached_object
        raise CachedObjectNotFound

    def add(self, object_type_key: str, object_key: Hashable, default: Any):
        """Add object to the cache."""
        # first check if object exists
        cached_object = self._cache.get(object_type_key, {}).get(object_key)
        if cached_object:
            raise CachedObjectAlreadyExists
        self._cache[object_type_key][object_key] = default
        return self._cache[object_type_key][object_key]

    def get_or_add(self, object_type_key: str, object_key: Hashable, callback: Callable):
        """Basic implementation to get from objects from cache.

        NOTE: Callbacks are used here instead of seeding a "default" value to ensure the code
            for getting the value to add is only ran if there is no existing object in the cache.
        """
        try:
            return self.get(object_type_key, object_key)
        except CachedObjectNotFound:
            return self.add(object_type_key, object_key, callback())


class NautobotCache(BasicCache):
    """Cache with additional functionaly for interacting with the Nautobot database."""

    # This dictionary acts as an ORM cache.
    _cache: DefaultDict[str, Dict[ParameterSet, Model]]

    def get_or_add_orm_object(self, parameters: Dict, model_class: Type[Model]):
        """Retrieve an object from the ORM or the cache."""
        parameter_set = frozenset(parameters.items())
        content_type = ContentType.objects.get_for_model(model_class)

        return self.get_or_add(
            object_type_key=f"{content_type.app_label}.{content_type.model}",
            object_key=parameter_set,
            # As we are using `get` here, this will error if there is not exactly one object that corresponds to the
            # parameter set. We intentionally pass these errors through.
            callback=lambda: model_class.objects.get(**dict(parameter_set)),
        )
