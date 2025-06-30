"""Unittests for typing utility functions."""

from nautobot.core.testing import TestCase
from typing_extensions import List

from nautobot_ssot.utils.typing import get_inner_type


class TestGetInnerType(TestCase):
    """Unit tests for `get_inner_type` function."""

    class ExampleClass:
        """Example class with type hints."""

        a: str
        b: List[str]

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
