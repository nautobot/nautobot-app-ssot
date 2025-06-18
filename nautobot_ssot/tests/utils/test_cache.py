"""Unittests for caching classes."""

from nautobot.core.testing import TestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status

from nautobot_ssot.utils.cache import ORMCache


class TestORMCache(TestCase):
    """Unit tests for ORM caching class."""

    def setUp(self):
        """Setup the test cases."""
        status = Status.objects.get(name="Active")
        location_type_1 = LocationType.objects.create(name="Location Type 1")
        Location.objects.create(
            name="Location 1",
            location_type=location_type_1,
            status=status,
        )
        self.cache = ORMCache()

        # Preload an item into the cache
        self.cache.get_from_orm(LocationType, {"name": "Location Type 1"})

    def test_get_new_object(self):
        """Test getting an object not in the cached."""
        # Validate the key does not currently exist
        self.assertTrue("dcim.location" not in self.cache.cache_hits.keys())

        result = self.cache.get_from_orm(Location, {"name": "Location 1"})
        self.assertEqual(result.name, "Location 1")
        self.assertEqual(self.cache.hits("dcim.location"), 0)

    def test_get_cached_object(self):
        """Test cache hits from getting a stored object multiple times."""
        # Validate the entry for the cached object exists.
        self.assertTrue("dcim.locationtype" in self.cache.cache_hits.keys())

        result = self.cache.get_from_orm(LocationType, {"name": "Location Type 1"})
        self.assertEqual(result.name, "Location Type 1")
        self.assertEqual(self.cache.hits("dcim.locationtype"), 1)

        result = self.cache.get_from_orm(LocationType, {"name": "Location Type 1"})
        self.assertEqual(self.cache.hits("dcim.locationtype"), 2)
        result = self.cache.get_from_orm(LocationType, {"name": "Location Type 1"})
        self.assertEqual(self.cache.hits("dcim.locationtype"), 3)
