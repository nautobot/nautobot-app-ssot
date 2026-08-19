"""Unittests for typing utility functions."""

from nautobot.apps.testing import TestCase
from nautobot_ssot.contrib.types import CustomRelationshipAnnotation
from nautobot_ssot.contrib.enums import RelationshipSideEnum
from typing import Annotated

from nautobot_ssot.utils.typing import (
    get_inner_type,
    SortedList,
    SortedListAlias,
    SortKey,
)

from typing import (
    Dict,
    TypedDict,
)

class TestGetInnerType(TestCase):
    """Unit tests for `get_inner_type` function."""

    class ExampleClass:
        """Example class with type hints."""

        a: str
        b: list[str]

    def test_get_attribute_with_inner_type(self):
        """Get a valid attribute with inner type."""
        result = get_inner_type(self.ExampleClass, "b")
        self.assertEqual(result, str)

    def test_get_attribute_without_inner_type(self):
        """Attempt to get inner type from attribute without inner type defined."""
        with self.assertRaises(TypeError):
            get_inner_type(self.ExampleClass, "a")

    def test_get_invalid_attribute(self):
        """Attempt to get inner type for non-existant attribute."""
        with self.assertRaises(AttributeError):
            get_inner_type(self.ExampleClass, "non_existant_attribute")

from typing import get_origin, get_type_hints

class TestSortedListTypeAnnotations(TestCase):
    """"""
    '''
    '''
    class TagTypedDict(TypedDict):
        """Test Class Please Ignore."""

        name: str

    def test_subclass_raise_error(self):
        with self.assertRaises(TypeError):
            class TestSorted(SortedList):
                """Test Class Please Ignore."""

    def test_instantiate_raises_error(self):
        with self.assertRaises(TypeError):
            SortedList()

    def test_dict_type_no_sortkey(self):
        with self.assertRaises(TypeError):
            class TestClass:
                """Test Class Please Ignore."""

                sorted_list: SortedList[dict]

    def test_dict_type_with_sortkey(self):
        class TestClass:
            """Test Class Please Ignore."""

            sorted_list: SortedList[dict, SortKey("name")]

    def test_typing_dict_type_no_sortkey(self):
        with self.assertRaises(TypeError):
            class TestClass:
                """Test Class Please Ignore."""

                sorted_list: SortedList[Dict]

    def test_typing_dict_type_with_sortkey(self):
        class TestClass:
            """Test Class Please Ignore."""

            sorted_list: SortedList[Dict, SortKey("name")]

    def test_typeddict_type_no_sortkey(self):
        with self.assertRaises(TypeError):
            class TestClass:
                """Test Class Please Ignore."""

                sorted_list: SortedList[self.TagTypedDict]

    def test_typeddict_type_with_sortkey(self):
        class TestClass:
            """Test Class Please Ignore."""

            sorted_list: SortedList[self.TagTypedDict, SortKey("name")]

    def test_type_with_no_key(self):
        class TestClass:
            """Test Class Please Ignore."""

            sorted_list: SortedList[str]

    def test_type_with_sort_key(self):
        with self.assertRaises(TypeError):
            class TestClass:
                """Test Class Please Ignore."""

                sorted_list: SortedList[str, SortKey("name")]

    def test_sortkey_with_custom_annotation_first(self):
        class TestClass:
            """Test Class Please Ignore."""

            sorted_list: SortedList[
                self.TagTypedDict,
                CustomRelationshipAnnotation(name="my_relationship", side=RelationshipSideEnum.DESTINATION),
                SortKey("name"),
            ]

    def test_sortkey_with_custom_annotation_second(self):
        class TestClass:
            """Test Class Please Ignore."""

            sorted_list: SortedList[
                self.TagTypedDict,
                SortKey("name"),
                CustomRelationshipAnnotation(name="my_relationship", side=RelationshipSideEnum.DESTINATION),
            ]

    def test_invalid_str_type(self):
        class TestClass:
            """Test Class Please Ignore."""

            sorted_list: SortedList["thisisastring"]

        with self.assertRaises(NameError):
            get_type_hints(TestClass, include_extras=True)
