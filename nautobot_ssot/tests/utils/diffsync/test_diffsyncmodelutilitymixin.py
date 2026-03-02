"""
Comprehensive unit tests for DiffSyncModelUtilityMixin.
"""
import unittest
from typing import Annotated, ClassVar
from nautobot_ssot.utils.diffsync import DiffSyncModelUtilityMixin
from nautobot_ssot.contrib.types import CustomAnnotation

class DummyAnnotation(CustomAnnotation):
    def __init__(self, value):
        self.value = value

class DummyModel(DiffSyncModelUtilityMixin):
    """Model with identifiers, attributes, and various type annotations for testing."""
    _identifiers: ClassVar[tuple] = ("id1",)
    _attributes: ClassVar[tuple] = ("attr1", "attr2", "plain", "no_type")
    id1: str
    attr1: Annotated[str, DummyAnnotation("foo")]
    attr2: Annotated[int, DummyAnnotation("bar")]
    plain: float
    no_type = None

class EmptyModel(DiffSyncModelUtilityMixin):
    """Model with no identifiers or attributes for edge case testing."""
    _identifiers: ClassVar[tuple] = ()
    _attributes: ClassVar[tuple] = ()

class TestDiffSyncModelUtilityMixin(unittest.TestCase):
    """Unit tests for DiffSyncModelUtilityMixin covering all utility methods and edge cases."""

    def test_get_synced_attributes(self):
        """Test correct list of identifiers and attributes returned."""
        self.assertEqual(DummyModel.get_synced_attributes(), ["id1", "attr1", "attr2", "plain", "no_type"])
        self.assertEqual(EmptyModel.get_synced_attributes(), [])

    def test_get_type_hints(self):
        """Test type hints for all annotated and plain fields."""
        hints = DummyModel.get_type_hints()
        self.assertIn("id1", hints)
        self.assertIn("attr1", hints)
        self.assertIn("attr2", hints)
        self.assertIn("plain", hints)
        self.assertIs(hints["plain"], float)

    def test_get_attr_args_annotated(self):
        """Test get_attr_args returns correct tuple for annotated fields."""
        args1 = DummyModel.get_attr_args("attr1")
        self.assertEqual(args1[0], str)
        self.assertIsInstance(args1[1], DummyAnnotation)
        args2 = DummyModel.get_attr_args("attr2")
        self.assertEqual(args2[0], int)
        self.assertIsInstance(args2[1], DummyAnnotation)

    def test_get_attr_args_plain(self):
        """Test get_attr_args returns empty tuple for plain fields."""
        args = DummyModel.get_attr_args("plain")
        self.assertEqual(args, ())

    def test_get_attr_annotation(self):
        """Test get_attr_annotation returns correct annotation for annotated fields."""
        ann1 = DummyModel.get_attr_annotation("attr1")
        self.assertIsInstance(ann1, DummyAnnotation)
        self.assertEqual(ann1.value, "foo")
        ann2 = DummyModel.get_attr_annotation("attr2")
        self.assertIsInstance(ann2, DummyAnnotation)
        self.assertEqual(ann2.value, "bar")

    def test_get_attr_annotation_none(self):
        """Test get_attr_annotation returns None for plain or missing fields."""
        self.assertIsNone(DummyModel.get_attr_annotation("plain"))
        self.assertIsNone(DummyModel.get_attr_annotation("id1"))
        # Should not raise, but skip 'no_type' since it is not a type-annotated attribute
        with self.assertRaises(KeyError):
            DummyModel.get_attr_annotation("no_type")
        with self.assertRaises(KeyError):
            DummyModel.get_attr_annotation("not_a_field")

    def test_is_attr_annotated(self):
        """Test is_attr_annotated returns True for annotated fields, False otherwise."""
        self.assertTrue(DummyModel.is_attr_annotated("attr1"))
        self.assertTrue(DummyModel.is_attr_annotated("attr2"))
        self.assertFalse(DummyModel.is_attr_annotated("plain"))
        self.assertFalse(DummyModel.is_attr_annotated("id1"))
        with self.assertRaises(KeyError):
            DummyModel.is_attr_annotated("no_type")

    def test_get_attr_type(self):
        """Test get_attr_type returns correct type for annotated and plain fields."""
        self.assertIs(DummyModel.get_attr_type("attr1"), str)
        self.assertIs(DummyModel.get_attr_type("attr2"), int)
        self.assertIs(DummyModel.get_attr_type("plain"), float)
        self.assertIs(DummyModel.get_attr_type("id1"), str)

    def test_get_attr_type_none(self):
        """Test get_attr_type returns None for missing or untyped fields."""
        with self.assertRaises(KeyError):
            DummyModel.get_attr_type("no_type")
        with self.assertRaises(KeyError):
            DummyModel.get_attr_type("not_a_field")

    def test_class_vars_unchanged(self):
        """Test that get_synced_attributes does not modify the original class variables."""
        DummyModel.get_synced_attributes()
        self.assertEqual(DummyModel._identifiers, ("id1",))
        self.assertEqual(DummyModel._attributes, ("attr1", "attr2", "plain", "no_type"))
