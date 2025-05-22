"""Unit tests for contrib sorting."""

from django.test import TestCase
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.sorting.parameters import (
    SortListTypeWithDict,
    sort_attribute_factory,
)
from nautobot_ssot.tests.contrib.sorting.objects import (
    BasicNautobotTenant,
    NautobotTenant,
    SimpleNautobotTenant,
)


class TestSortListTypeWithDict(TestCase):
    """Unittests for sorting lists of dictionaries."""

    def setUp(self):
        """Set up the test class."""
        self.sorter = SortListTypeWithDict(name="tags", sort_key="name")

    def test_sorting_basic_dictionaries(self):
        """Test basic dictionary."""
        list_1 = [{"name": "X"}, {"name": "C"}, {"name": "M"}]
        sorted_list = self.sorter(list_1)
        self.assertEqual(sorted_list[0]["name"], "C", sorted_list)
        self.assertEqual(sorted_list[1]["name"], "M", sorted_list)
        self.assertEqual(sorted_list[2]["name"], "X", sorted_list)


class TestParameterFactory(TestCase):
    """Test cases for the parameter factory."""

    def setUp(self):
        """Setup the test class."""
        self.model = NautobotTenant
        self.type_hints = get_type_hints(self.model, include_extras=True)

        self.basic_model = BasicNautobotTenant
        self.basic_type_hints = get_type_hints(self.basic_model, include_extras=True)

        self.simple_model = SimpleNautobotTenant
        self.simple_type_hints = get_type_hints(self.simple_model, include_extras=True)

    def test_model_with_typed_dict_and_sort_key(self):
        """Test getting sorting class with model with TypedDict and sort key."""
        result = sort_attribute_factory(
            "tags",
            self.type_hints["tags"],
        )
        self.assertTrue(isinstance(result, SortListTypeWithDict))

    def test_model_with_typed_dict_no_sort_key(self):
        """Test getting sorting class with model with TypedDict and sort key."""
        result = sort_attribute_factory(
            "tags",
            self.basic_type_hints["tags"],
        )
        self.assertIsNone(result)

    def test_model_with_standard_dict(self):
        """Test getting sorting class with model with TypedDict and sort key."""
        result = sort_attribute_factory(
            "tags",
            self.simple_type_hints["tags"],
        )
        self.assertIsNone(result)
