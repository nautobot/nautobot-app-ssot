"""Caching classes for use in SSoT processes."""

from collections.abc import Hashable
from typing import Type
from nautobot_ssot.config import SSOT_CONFIG

from django.db.models import Model
from functools import lru_cache


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
ParameterSet = frozenset[tuple[str, Hashable]]


class ORMCache:
    """Wrapper class for caching responses from Django ORM when using a Nautobot-based DiffSync Adapter.

    The wrapper class is used instead of a standard `@lru_cache` decorator on a function for several reasons:

        1. SSoT operations requires the cache to be cleared and non-assuming each time an SSoT job is ran.
           Using the cache as an object instead of a decorated function ensures it is cleared every time.

        2. Caching a dictionary input on a decorated function is not feasible since a dictioanry is not, by
           default, hashable and is required to be passed as a `frozenset`. Instead of requiring a `frozenset`
           be passed, the dictionary can be directly passed into the public method, which handles the any
           additional processing to make the dictionary hashable.
    """

    def __init__(self):
        """Initialize the class."""
        self.cache_clear()

    @lru_cache(maxsize=SSOT_CONFIG.get("orm_cache_max_size", None))
    def _get(self, model_class: Type[Model], parameter_set: ParameterSet):
        """Cached method for retreiving data from the database."""
        return model_class.objects.get(**dict(parameter_set))

    def get(self, model_class: Type[Model], parameters: dict):
        """Public method for retreiving cached data from the database."""
        return self._get(model_class, frozenset(parameters))

    def cache_clear(self):
        """Clear the cache."""
        return self._get.cache_clear()

    def cache_info(self):
        """Get cache information and stats."""
        return self._get.cache_info

    def cache_parameters(self):
        """Get cache parameters."""
        return self._get.cache_parameters()

    def __repr__(self):
        """Representation of the class."""
        return f"ORMCache({self.cache_info()})"
