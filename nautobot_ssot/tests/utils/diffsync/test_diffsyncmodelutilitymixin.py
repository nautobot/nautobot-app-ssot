"""Comprehensive unit tests for DiffSyncModelUtilityMixin."""

import unittest
from typing import Annotated, ClassVar
from nautobot_ssot.utils.diffsync import DiffSyncModelUtilityMixin
from nautobot_ssot.contrib.types import CustomFieldAnnotation, CustomRelationshipAnnotation, RelationshipSideEnum


class DummyModel(DiffSyncModelUtilityMixin):
    """A dummy model for testing DiffSyncModelUtilityMixin with identifiers, attributes, and type annotations."""
    _identifiers: ClassVar[tuple] = ("id1",)
    _attributes: ClassVar[tuple] = ("attr1", "attr2")
    id1: str
    attr1: Annotated[str, CustomFieldAnnotation("cf1")]
    attr2: Annotated[str, CustomRelationshipAnnotation("rel1", side=RelationshipSideEnum.SOURCE)]
    plain: int


class EmptyModel(DiffSyncModelUtilityMixin):
    """A dummy model for testing with no identifiers or attributes."""
    _identifiers: ClassVar[tuple] = ()
    _attributes: ClassVar[tuple] = ()


class TestDiffSyncModelUtilityMixin(unittest.TestCase):
    """Unit tests for the DiffSyncModelUtilityMixin class covering all utility methods and edge cases."""

    def test_get_synced_attributes(self):
        """Test that get_synced_attributes returns the correct list of identifiers and attributes."""
        self.assertEqual(DummyModel.get_synced_attributes(), ["id1", "attr1", "attr2"])
        self.assertEqual(EmptyModel.get_synced_attributes(), [])

    def test_get_type_hints(self):
        """Test that get_type_hints returns all annotated fields and their types."""
        hints = DummyModel.get_type_hints()
        self.assertIn("id1", hints)
        self.assertIn("attr1", hints)
        self.assertIn("attr2", hints)
        self.assertIn("plain", hints)
        self.assertIs(hints["plain"], int)

    def test_get_attr_annotation_field(self):
        """Test that get_attr_annotation returns the correct CustomFieldAnnotation for an annotated field."""
        ann = DummyModel.get_attr_annotation("attr1")
        self.assertIsInstance(ann, CustomFieldAnnotation)
        self.assertEqual(ann.key, "cf1")

    def test_get_attr_annotation_relationship(self):
        """Test that get_attr_annotation returns the correct CustomRelationshipAnnotation for an annotated field."""
        ann = DummyModel.get_attr_annotation("attr2")
        self.assertIsInstance(ann, CustomRelationshipAnnotation)
        self.assertEqual(ann.name, "rel1")
        self.assertEqual(ann.side, RelationshipSideEnum.SOURCE)

    def test_get_attr_annotation_none(self):
        """Test that get_attr_annotation returns None for unannotated or missing fields."""
        self.assertIsNone(DummyModel.get_attr_annotation("plain"))
        self.assertIsNone(DummyModel.get_attr_annotation("id1"))
        self.assertIsNone(DummyModel.get_attr_annotation("not_a_field"))

    def test_get_attr_type(self):
        """Test that get_attr_type returns the correct type for annotated and plain fields."""
        self.assertIs(DummyModel.get_attr_type("attr1"), str)
        self.assertIs(DummyModel.get_attr_type("attr2"), str)
        self.assertIs(DummyModel.get_attr_type("plain"), int)

    def test_get_attr_type_invalid(self):
        """Test that get_attr_type returns None for missing fields."""
        self.assertIsNone(DummyModel.get_attr_type("not_a_field"))

    def test_class_vars_unchanged(self):
        """Test that get_synced_attributes does not modify the original class variables."""
        DummyModel.get_synced_attributes()
        self.assertEqual(DummyModel._identifiers, ("id1",))
        self.assertEqual(DummyModel._attributes, ("attr1", "attr2"))
