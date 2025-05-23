"""Unit tests for contrib sorting."""

from django.test import TestCase
from unittest import skip
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.sorting.parameters import (
    SortListTypeWithDict,
    sorting_attribute_factory,
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

    def test_sorting_list_of_strings(self):
        """Test sorting when passing a list of strings."""
        with self.assertRaises(TypeError):
            self.sorter(["str1", "str2", "str3"])

    def test_sorting_list_of_integers(self):
        """Test sorting when passing a list of integers."""
        with self.assertRaises(TypeError):
            self.sorter([1, 2, 3, 4])

    def test_sorting_string(self):
        """Test sorting when passing a string."""
        with self.assertRaises(TypeError):
            self.sorter("Invalid String.")

    def test_sorting_integer(self):
        """Test sorting when passing an integer."""
        with self.assertRaises(TypeError):
            self.sorter(42)


class TestSortAttributeFactoryInvalidInputs(TestCase):
    """Test the sorting attribute factory with invalid inputs."""

    def setUp(self):
        """Setup the test class."""
        self.model = NautobotTenant
        self.type_hints = get_type_hints(self.model, include_extras=True)

    def test_invalid_string(self):
        """Test to ensure"""
        with self.assertRaises(ValueError):
            sorting_attribute_factory("parameter name", {})

    def test_integer_name(self):
        """Test to ensure"""
        with self.assertRaises(TypeError):
            sorting_attribute_factory(54, {})

    @skip("Validation not properly set yet.")
    def test_string_type_hints(self):
        """Test to ensure invalid type_hints are not accepted."""
        with self.assertRaises(TypeError):
            sorting_attribute_factory("name", "invalid type hint")

    @skip("Validation not properly set yet.")
    def test_mismatched_dict(self):
        """Test for if """
        result = sorting_attribute_factory("name", [])


class TestSortAttributeFactoryFactory(TestCase):
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
        result = sorting_attribute_factory(
            "tags",
            self.type_hints["tags"],
        )
        self.assertTrue(isinstance(result, SortListTypeWithDict))

    def test_model_with_typed_dict_no_sort_key(self):
        """Test getting sorting class with model with TypedDict and sort key."""
        result = sorting_attribute_factory(
            "tags",
            self.basic_type_hints["tags"],
        )
        self.assertIsNone(result)

    def test_model_with_standard_dict(self):
        """Test getting sorting class with model with TypedDict and sort key."""
        result = sorting_attribute_factory(
            "tags",
            self.simple_type_hints["tags"],
        )
        self.assertIsNone(result)
