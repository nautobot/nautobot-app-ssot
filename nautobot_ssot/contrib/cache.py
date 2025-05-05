"""Cache class for SSoT jobs."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from abc import abstractmethod, ABCMeta
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Union, Hashable, Callable

from nautobot_ssot.contrib.exceptions import CachedObjectAlreadyExists, CachedObjectNotFound
from dataclasses import dataclass, field


class CacheInterface(metaclass=ABCMeta):
    """Interface definition for Adapter Caches."""

    _cache: Union[
        DefaultDict[object, object],
        DefaultDict[str, Dict[Hashable, object]],
    ]
    _cache_hits: DefaultDict[str, int]

    def __init__(self, *args, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        self._cache = kwargs.get("_cache", defaultdict())
        self._cache_hits = kwargs.get("_cache_hits", defaultdict(int))

    @abstractmethod
    def total_hits(self, object_type_key):
        """Get total cache hits for an object type."""

    @abstractmethod
    def get(self, object_type_key, object_key):
        """Get object from cache."""

    @abstractmethod
    def add(self, object_type_key: str, object_key: Hashable, default: Any):
        """Add object to the cache."""

    @abstractmethod
    def get_or_add(self, object_type_key: str, object_key: Hashable, callback: Callable):
        """Basic implementation to get from objects from cache.
        
        NOTE: Callbacks are used here instead of seeding a "default" value to ensure the code
            for getting the value to add is only ran if there is no existing object in the cache.
        """

    
class BasicCache(CacheInterface):
    """Basic, reusable caching class for adapters."""

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
