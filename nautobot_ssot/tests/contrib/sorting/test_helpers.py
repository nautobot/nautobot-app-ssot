from typing_extensions import Annotated, TypedDict
from nautobot_ssot.contrib.typeddicts import SortKey
from unittest import TestCase
from nautobot_ssot.contrib.sorting.helpers import get_dict_sort_key


class ValidTypedDictSortKey(TypedDict):
    """Valid Typed Dict for testing."""

    non_sort_key_1: str
    non_sort_key_2: str
    non_sort_key_3: str
    name: Annotated[str, SortKey]

class ValidTypedDictBasic(TypedDict):
    """Valid Typed Dict for testing."""

    non_sort_key_1: str
    non_sort_key_2: str
    non_sort_key_3: str


class TestGetDictSortKey(TestCase):
    """Unittests for `get_dict_sort_key` helper function."""

    def test_valid_sort_key(self):
        """Test valid typed dict type passed with sort key."""
        result = get_dict_sort_key(ValidTypedDictSortKey)
        self.assertEqual(result, "name")
        
    def test_valid_typeddict_type_without_sort_key(self):
        """Test valid typed dict type passed with sort key."""
        self.assertIsNone(get_dict_sort_key(ValidTypedDictBasic))

    def test_string_type(self):
        """Test function by passing string type."""
        with self.assertRaises(TypeError):
            get_dict_sort_key(str)

    def test_integer_type(self):
        """Test function by passing string type."""
        with self.assertRaises(TypeError):
            get_dict_sort_key(int)

    def test_none_type(self):
        """Test function by passing None object."""
        with self.assertRaises(TypeError):
            get_dict_sort_key(None)

    def test_dict_instance(self):
        """Test function by passing dictionary instance."""
        with self.assertRaises(TypeError):
            get_dict_sort_key({"name": "TEST-001"})

    def test_typeddict_instance(self):
        """Test function by passing dictionary instance."""
        with self.assertRaises(TypeError):
            get_dict_sort_key(ValidTypedDictSortKey(
                non_sort_key_1="",
                non_sort_key_2="",
                non_sort_key_3="",
                name="My Name",
            ))

    def test_string_instance(self):
        """Test function by passing dictionary instance."""
        with self.assertRaises(TypeError):
            get_dict_sort_key("My String")

    def test_integer_instance(self):
        """Test function by passing dictionary instance."""
        with self.assertRaises(TypeError):
            get_dict_sort_key(42)