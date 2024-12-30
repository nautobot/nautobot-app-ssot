
from typing import List, Optional

from nautobot_ssot.contrib.types import FieldType
import nautobot.tenancy.models as tenancy_models
from django.test import TestCase as TestCase
from typing_extensions import Annotated, TypedDict
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.sorting import (
    _get_sortable_fields_from_model,
    _is_sortable_field,
    _get_sortable_obj_type,
    _get_sortable_obj_sort_key,
    sort_relationships,
    _sort_diffsync_object,
)

from nautobot_ssot.contrib import NautobotModel


class BasicTagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    id: int
    name: str


class TagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    id: int
    name: Annotated[str, FieldType.SORT_BY]
    description: Optional[str] = ""


class BasicNautobotTenant(NautobotModel):
    """A tenant model for testing the `NautobotModel` base class."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group__name", "tags")

    name: str
    description: Optional[str] = None
    tenant_group__name: Optional[str] = None
    tags: List[BasicTagDict] = []


class NautobotTenant(NautobotModel):
    """A tenant model for testing the `NautobotModel` base class."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group__name", "tags")

    name: str
    description: Optional[str] = None
    tenant_group__name: Optional[str] = None
    tags: Annotated[List[TagDict], FieldType.SORTED_FIELD] = []


class TestCaseIsSortableFieldFunction(TestCase):
    """"""

    @classmethod
    def setUpTestData(cls):
        cls.type_hints = get_type_hints(NautobotTenant, include_extras=True)

    def test_non_sortable_field(self):
        test = _is_sortable_field(self.type_hints["name"])
        self.assertFalse(test)

    def test_sortable_field(self):
        test = _is_sortable_field(self.type_hints["tags"])
        self.assertTrue(test)


class TestGetSortKeyFunction(TestCase):
    """"""

    def test_get_sort_key(self):
        test = _get_sortable_obj_sort_key(TagDict)
        self.assertEqual(test, "name")

    def test_no_sort_key(self):
        """"""
        class TestClass(TypedDict):
            id: str
            name:str

        test = _get_sortable_obj_sort_key(TestClass)
        self.assertIsNone(test)


class TestCaseGetSortableFieldsFromModelFunction(TestCase):
    """Tests for `_get_sortable_fields_from_model` function."""

    def test_with_sortable_fields(self):
        """Test get sortable fields with one sortable field identified."""
        test = _get_sortable_fields_from_model(NautobotTenant)
        self.assertEqual(len(test), 1)

    def test_without_sortable_fields(self):
        """Test get sortable fields with no sortable fields identified."""
        test = _get_sortable_fields_from_model(BasicNautobotTenant)
        self.assertEqual(len(test), 0)


class TestSortDiffSyncObjectFunction(TestCase):
    """"""

    @classmethod
    def setUpTestData(cls):
        """"""
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
            ]
        )

    def test_with_sortable_field(self):
        """Test to make sure `_sort_diffsync_object` sorts attribute."""
        self.assertEqual(
            self.obj_1.tags[0]["name"],
            "b",
            msg="List of `TagDict` entries must start with `name='b'` to verify proper sorting."
        )
        test = _sort_diffsync_object(self.obj_1, "tags", "name")
        self.assertEqual(test.tags[0]["name"], "a")


class TestGetSortableObjectTypeFunction(TestCase):
    """Tests for `_get_sortable_object_type` function."""

    def test_get_sortable_object_type(self):
        """Test to validate `_get_sortable_obj_type` function returns correct object type."""
        type_hints = get_type_hints(NautobotTenant, include_extras=True)
        test = _get_sortable_obj_type(type_hints.get("tags"))
        self.assertTrue(test == TagDict)

    def test_get_sortable_object_type(self):
        """Test to validate `_get_sortable_obj_type` function returns None."""
        type_hints = get_type_hints(BasicNautobotTenant, include_extras=True)
        test = _get_sortable_obj_type(type_hints["tags"])
        self.assertIsNone(test)


class TestSortRelationships(TestCase):
    """"""
