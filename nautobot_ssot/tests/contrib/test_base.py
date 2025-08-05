"""Unit tests for contrib base classes."""

#from nautobot.core.testing import TestCase
#from django.test import TestCase
from unittest import TestCase

from typing import List, Optional
from unittest import skip
from unittest.mock import MagicMock

from nautobot.dcim.models import Location
from typing_extensions import Optional, Annotated, TypedDict, get_type_hints

from nautobot_ssot.contrib.base import BaseNautobotModel


class NautobotModel(BaseNautobotModel):
    """Nautobot Model class with required abstract methods and attributes for unit testing."""

    _model = Location
    _modelname = "location"
    _identifiers = ("name",)
    _attributes = ("location__name", "description",)

    name: str
    location__name: Optional[str] = ""
    description: Optional[str] = ""

    @classmethod
    def get_queryset(cls):
        """Blank method to satisfy abstract method requirement."""


class TestBasicMethods(TestCase):
    """Basic test cases for methods not requiring many test cases."""

    def test_get_model(self):
        """Test to ensure model class type is returned."""
        self.assertEqual(NautobotModel.get_model(), Location)


class TestGetSyncedAttributesMethod(TestCase):
    """Test cases for `get_synced_attributes` method."""

    def setUp(self):
        """Set up the test case."""
        self.result = NautobotModel.get_synced_attributes()

    def test_assert_result_length(self):
        self.assertEqual(len(self.result), 3)

    def test_assert_entry_name(self):
        self.assertTrue("name" in self.result)

    def test_assert_entry_location_name(self):
        self.assertTrue("location__name" in self.result)

    def test_assert_entry_description(self):
        self.assertTrue("description" in self.result)
