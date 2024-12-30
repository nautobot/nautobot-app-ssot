"""Unit tests for contrib sorting."""

from typing import List, Optional

from django.test import TestCase
from typing_extensions import Annotated, TypedDict, get_type_hints

from nautobot_ssot.contrib.sorting import (
    get_sortable_fields_from_model,
    get_sortable_obj_sort_key,
    get_sortable_obj_type,
    is_sortable_field,
    sort_diffsync_object,
)
from nautobot_ssot.contrib.types import FieldType
from nautobot_ssot.tests.contrib_base_classes import NautobotTenant as BasicNautobotTenant
from nautobot_ssot.tests.contrib_base_classes import TagDict as BasicTagDict


class TagDict(BasicTagDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    id: int
    name: Annotated[str, FieldType.SORT_BY]
    description: Optional[str] = ""


class NautobotTenant(BasicNautobotTenant):
    """A updated tenant model for testing the `NautobotModel` base class."""

    tags: Annotated[List[TagDict], FieldType.SORTED_FIELD] = []


class TestCaseIsSortableFieldFunction(TestCase):
    """Tests for `_is_sortable_field` function."""

    @classmethod
    def setUpTestData(cls):
        cls.type_hints = get_type_hints(NautobotTenant, include_extras=True)

    def test_non_sortable_field(self):
        test = is_sortable_field(self.type_hints["name"])
        self.assertFalse(test)

    def test_sortable_field(self):
        test = is_sortable_field(self.type_hints["tags"])
        self.assertTrue(test)


class TestGetSortKeyFunction(TestCase):
    """Tests for `_get_sortable_obj_key` function."""

    def test_get_sort_key(self):
        test = get_sortable_obj_sort_key(TagDict)
        self.assertEqual(test, "name")

    def test_no_sort_key(self):
        """Test function with no wort key."""

        class TestClass(TypedDict):  # pylint: disable=missing-class-docstring
            id: str
            name: str

        test = get_sortable_obj_sort_key(TestClass)
        self.assertIsNone(test)


class TestCaseGetSortableFieldsFromModelFunction(TestCase):
    """Tests for `_get_sortable_fields_from_model` function."""

    def test_with_sortable_fields(self):
        """Test get sortable fields with one sortable field identified."""
        test = get_sortable_fields_from_model(NautobotTenant)
        self.assertEqual(len(test), 1)

    def test_without_sortable_fields(self):
        """Test get sortable fields with no sortable fields identified."""
        test = get_sortable_fields_from_model(BasicNautobotTenant)
        self.assertEqual(len(test), 0)


class TestSortDiffSyncObjectFunction(TestCase):
    """Tests for `_sort_diffsync_object` function."""

    @classmethod
    def setUpTestData(cls):
        cls.obj_1 = NautobotTenant(
            name="",
            description="DiffSync object with a sortable field.",
            tags=[
                TagDict(
                    id=1,
                    name="b",
                    description="",
                ),
                TagDict(
                    id=2,
                    name="a",
                    description="",
                ),
            ],
        )

    def test_with_sortable_field(self):
        """Test to make sure `_sort_diffsync_object` sorts attribute."""
        self.assertEqual(
            self.obj_1.tags[0]["name"],
            "b",
            msg="List of `TagDict` entries must start with `name='b'` to verify proper sorting.",
        )
        test = sort_diffsync_object(self.obj_1, "tags", "name")
        self.assertEqual(test.tags[0]["name"], "a")


class TestGetSortableObjectTypeFunction(TestCase):
    """Tests for `_get_sortable_object_type` function."""

    def test_get_sortable_object_type(self):
        """Test to validate `_get_sortable_obj_type` function returns correct object type."""
        type_hints = get_type_hints(NautobotTenant, include_extras=True)
        test = get_sortable_obj_type(type_hints.get("tags"))
        self.assertTrue(test == TagDict)

    def test_get_nonsortable_object_type(self):
        """Test to validate `_get_sortable_obj_type` function returns None."""
        type_hints = get_type_hints(BasicNautobotTenant, include_extras=True)
        test = get_sortable_obj_type(type_hints["tags"])
        self.assertIsNone(test)


class TestSortRelationships(TestCase):
    """Tests for `sort_relationships` function."""
