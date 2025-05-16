"""Unit tests for contrib sorting."""

from typing import List, Optional
from unittest.mock import MagicMock

from django.test import TestCase
from nautobot.extras.models import Tag
from nautobot.tenancy.models import Tenant
from typing_extensions import Annotated, TypedDict, get_type_hints

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.contrib.sorting import (
    _is_sortable_field,
    get_sort_key_from_typed_dict,
    get_sortable_fields_from_model,
    sort_relationships,
)
from nautobot_ssot.contrib.typeddicts import SortKey


class BasicTagDict(TypedDict):
    """Basic TypedDict without sort key."""

    name: str
    description: Optional[str]


class TagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: Annotated[str, SortKey]
    description: Optional[str] = ""


class BasicNautobotTag(NautobotModel):
    """A tag model for use in testing."""

    _model = Tag
    _modelname = "tag"
    _identifiers = ("name",)
    _attributes = ("description",)

    name: str
    description: Optional[str] = None


class NautobotTenant(NautobotModel):
    """A basic tenant model for testing the `NautobotModel` base class."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[TagDict] = []


class TestAdapter(NautobotAdapter):
    """An adapter for testing the `BaseAdapter` base class."""

    top_level = ("tenant",)
    tenant = NautobotTenant


##############
# UNIT TESTS #
##############


class TestCaseIsSortableFieldFunction(TestCase):
    """Tests for `_is_sortable_field` function."""

    @classmethod
    def setUpTestData(cls):
        cls.model = NautobotTenant
        cls.type_hints = get_type_hints(NautobotTenant, include_extras=True)

    def test_sortable_field(self):
        test = _is_sortable_field(self.type_hints["tags"])
        self.assertTrue(test)

    def test_non_sortable_field(self):
        test = _is_sortable_field(self.type_hints["name"])
        self.assertFalse(test)


class TestCaseGetSortedAttributesFromModel(TestCase):
    """Tests for `get_sortable_fields_from_model` function."""

    def test_one_sortable_attribute(self):
        result = get_sortable_fields_from_model(NautobotTenant)
        self.assertTrue(len(result) == 1)

    def test_no_sortable_attributes(self):
        result = get_sortable_fields_from_model(BasicNautobotTag)
        self.assertTrue(len(result) == 0)


class TestCaseSortRelationships(TestCase):
    """Tests for `sort_relationships` function."""

    @classmethod
    def setUpTestData(cls):
        cls.source = TestAdapter(
            job=MagicMock(),
        )
        cls.target = TestAdapter(
            job=MagicMock(),
        )

        cls.source.add(
            NautobotTenant(
                name="tenant1",
                tags=[
                    TagDict(name="B Tag", description="Test Tag"),
                    TagDict(name="A Tag", description="Test Tag"),
                    TagDict(name="C Tag", description="Test Tag"),
                    TagDict(name="E Tag", description="Test Tag"),
                    TagDict(name="D Tag", description="Test Tag"),
                ],
            )
        )
        cls.target.add(
            NautobotTenant(
                name="tenant1",
                tags=[
                    TagDict(name="B Tag", description="Test Tag"),
                    TagDict(name="A Tag", description="Test Tag"),
                    TagDict(name="C Tag", description="Test Tag"),
                    TagDict(name="E Tag", description="Test Tag"),
                    TagDict(name="D Tag", description="Test Tag"),
                ],
            )
        )

    def test_sort_relationships(self):
        # Verify order of entries prior to sorting
        self.assertTrue(self.source.get_all("tenant")[0].tags[0]["name"] == "B Tag")
        self.assertTrue(self.target.get_all("tenant")[0].tags[0]["name"] == "B Tag")
        sort_relationships(self.source, self.target)
        self.assertTrue(self.source.get_all("tenant")[0].tags[0]["name"] == "A Tag")
        self.assertTrue(self.target.get_all("tenant")[0].tags[0]["name"] == "A Tag")


class TestGetSortKeyFromTypedDict(TestCase):
    """Unit tests for `get_sort_key_from_typed_dict` function."""

    def test_valid_typed_dict(self):
        """Test valid TypedDict returns correct sort key."""
        self.assertEqual(get_sort_key_from_typed_dict(TagDict), "name")

    def test_invalid_dict(self):
        """Test an invalid dictionary returning None.

        A standard Dictionary without annotations will raise an AttributeError when
        getting `__annotations__`. This should return `None`.
        """
        self.assertIsNone(get_sort_key_from_typed_dict({"name": "TestName"}))

    def test_typed_dict_without_sort_key(self):
        """Test a typed dict without sort key specified."""
        self.assertIsNone(get_sort_key_from_typed_dict(BasicTagDict))
