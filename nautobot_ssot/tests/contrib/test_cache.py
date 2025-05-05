"""Tests for contrib.NautobotAdapter."""

from nautobot.core.testing import TestCase

from nautobot_ssot.contrib.cache import BasicCache
from nautobot_ssot.contrib.exceptions import CachedObjectAlreadyExists, CachedObjectNotFound

class TestBasicCache(TestCase):
    """Test caching class for basic functionality."""

    def setUp(self):
        """Set up test case."""
        self.cache = BasicCache()
        self.cache.add("test1", "object1", "value1")
        self.cache.add("test2", "object2", "value2")

    def test_add_new_object(self):
        """Test adding a new object."""
        self.cache.add("test3", "object3", "value3")
        self.assertEqual("value3", self.cache._cache["test3"]["object3"])

    def test_add_existing_object(self):
        """Test adding an existing object."""
        with self.assertRaises(CachedObjectAlreadyExists):
            self.cache.add("test1", "object1", "value1"),

    def test_get_existing_object(self):
        """Test getting an existing object."""
        self.assertEqual("value1", self.cache._cache["test1"]["object1"])

    def test_get_missing_object(self):
        """Test getting an object that doesn't exist."""
        with self.assertRaises(CachedObjectNotFound):
            self.cache.get("test3", "object3")
