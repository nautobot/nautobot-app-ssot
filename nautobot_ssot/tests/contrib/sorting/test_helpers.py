"""Unit tests for helper functions"""

from typing_extensions import Annotated, TypedDict, get_type_hints, List
from nautobot_ssot.contrib.typeddicts import SortKey
from nautobot_ssot.contrib.types import CustomFieldAnnotation
from unittest import TestCase
from nautobot_ssot.contrib.sorting.helpers import get_attribute_origin_and_args, get_dict_sort_key
from diffsync import DiffSyncModel

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


class TestGetAttributeOriginAndArgs(TestCase):
    """Test cases for `get_attribute_origin_and_args` function."""

    class MyTypedDict(TypedDict):
        """Sample typed dict for use in test cases for function."""

        sort_key_list: Annotated[List[str], SortKey]
        custom_field_str: Annotated[str, CustomFieldAnnotation]
        list_type: List[str]
        str_type: str
        int_type: str

    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        cls.type_hints = get_type_hints(cls.MyTypedDict, include_extras=True)

    def test_annotated_with_list_type(self):
        """Test annotated type with `List[str]` type and `SortKey` argument."""
        origin, args = get_attribute_origin_and_args(self.type_hints["sort_key_list"])
        self.assertEqual(origin, list)
        self.assertEqual(args, [SortKey])

    def test_annotated_with_string_type(self):
        """Test annotated type with `str` type  and `CustomFieldAnnotation` argument."""
        origin, args = get_attribute_origin_and_args(self.type_hints["custom_field_str"])
        self.assertIsNone(origin)
        self.assertEqual(args, [CustomFieldAnnotation])

    def test_list_type_with_string(self):
        """Test with list type of strings."""
        origin, args = get_attribute_origin_and_args(self.type_hints["list_type"])
        self.assertEqual(origin, list)
        self.assertEqual(args, [str])

    def test_string_type(self):
        origin, args = get_attribute_origin_and_args(self.type_hints["str_type"])
        self.assertIsNone(origin)
        self.assertEqual(args, [])

    def test_integer_type(self):
        origin, args = get_attribute_origin_and_args(self.type_hints["int_type"])
        self.assertIsNone(origin)
        self.assertEqual(args, [])

    def test_list_instance(self):
        origin, args = get_attribute_origin_and_args(["str1", "str2", "str3"])
        self.assertIsNone(origin)
        self.assertEqual(args, [])

    def test_typed_dict_instance(self):
        origin, args = get_attribute_origin_and_args([
            self.MyTypedDict(
                sort_key_list=["A"],
                custom_field_str="B",
                list_type=["C"],
                str_type="D",
                int_type=1,
            )
        ])
        self.assertIsNone(origin)
        self.assertEqual(args, [])

    def test_string_instance(self):
        origin, args = get_attribute_origin_and_args("str1")
        self.assertIsNone(origin)
        self.assertEqual(args, [])

    def test_integer_instance(self):
        origin, args = get_attribute_origin_and_args(42)
        self.assertIsNone(origin)
        self.assertEqual(args, [])
