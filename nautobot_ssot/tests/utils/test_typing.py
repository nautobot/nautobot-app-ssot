"""Unittests for typing utility functions."""

from typing_extensions import List
from nautobot_ssot.utils.typing import get_inner_type
from nautobot.core.testing import TestCase


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
