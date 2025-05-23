"""Unittests for `SortModelInterface` class and associated functions."""

from diffsync import DiffSyncModel
from unittest import TestCase
from typing_extensions import List, Annotated, TypedDict, Optional
from nautobot_ssot.contrib.typeddicts import SortKey
from nautobot_ssot.contrib.sorting.models import SortModelInterface

class TagDict(TypedDict):
    """Example typed dict for testing."""

    name: Annotated[str, SortKey]
    description: Optional[str]




class ExampleModel(DiffSyncModel):
    """"""

    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[TagDict] = []


class TestSortModelInterface(TestCase):
    """Test SortModelInterface class."""

    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        cls.sorting_class = SortModelInterface(model_class=ExampleModel)

    def test_instantiate_class(self):
        """Test basic instantiation of class."""
        self.assertTrue(isinstance(self.sorting_class.sortable_parameters, list))
        self.assertEqual(len(self.sorting_class.sortable_parameters), 1)

    def test_invalid_str_type(self):
        """Test passing an invalid string type."""
        with self.assertRaises(TypeError):
            SortModelInterface(str)

    def test_invalid_int_type(self):
        """Test passing an invalid integer type."""
        with self.assertRaises(TypeError):
            SortModelInterface(int)

    def test_invalid_str_instance(self):
        """Test passing an invalid string instance."""
        with self.assertRaises(TypeError):
            SortModelInterface("Invalid String")

    def test_invalid_int_instance(self):
        """Test passing an invalid integer instance."""
        with self.assertRaises(TypeError):
            SortModelInterface(42)
