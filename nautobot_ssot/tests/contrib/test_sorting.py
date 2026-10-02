"""Unit tests for contrib sorting."""

import sys
from typing import Annotated, List, Optional
from unittest.mock import MagicMock, patch

from nautobot.apps.testing import TestCase
from nautobot.extras.models import Tag
from nautobot.tenancy.models import Tenant
from typing_extensions import TypedDict, get_type_hints

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.contrib.sorting import (
    _is_sortable_field,
    _sort_dict_attr,
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


class NautobotTenantUnsortableTags(NautobotModel):
    """Tenant model whose list attribute has no SortKey, so it is not sortable."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[BasicTagDict] = []


class NoSortFieldsAdapter(NautobotAdapter):
    """Adapter whose top-level model exposes no sortable fields."""

    top_level = ("tag",)
    tag = BasicNautobotTag


class SortingEdgeCaseTests(TestCase):
    """Cover the remaining edge branches in contrib.sorting."""

    def test_is_sortable_field_non_typing_returns_false(self):
        """A hint without a name attribute is not sortable (hits the AttributeError guard)."""
        self.assertFalse(_is_sortable_field(object()))

    def test_is_sortable_field_python_3_9_branch(self):
        """Force the Python <= 3.9 code path that reads `_name`."""
        with patch.object(sys, "version_info", (3, 9, 0, "final", 0)):
            self.assertFalse(_is_sortable_field(object()))

    def test_sortable_field_without_sort_key_is_skipped(self):
        """A list field whose TypedDict has no SortKey is not treated as sortable."""
        self.assertEqual(get_sortable_fields_from_model(NautobotTenantUnsortableTags), {})

    def test_sort_dict_attr_without_key_sorts_plainly(self):
        """`_sort_dict_attr` with no key sorts the raw values."""

        class _Holder:
            values = ["b", "a", "c"]

        holder = _Holder()
        result = _sort_dict_attr(holder, "values", None)
        self.assertEqual(result.values, ["a", "b", "c"])

    def test_sort_relationships_noop_without_adapters(self):
        """`sort_relationships` returns early when either adapter is missing."""
        self.assertIsNone(sort_relationships(None, MagicMock()))

    def test_sort_relationships_model_without_sortable_fields(self):
        """A top-level model with no sortable fields is skipped without error."""
        source = NoSortFieldsAdapter(job=MagicMock())
        target = NoSortFieldsAdapter(job=MagicMock())
        # Adapters must be non-empty, otherwise sort_relationships returns early.
        for adapter in (source, target):
            adapter.add(BasicNautobotTag(name="tag1"))
        sort_relationships(source, target)  # exercises the "no sortable fields" continue

    def test_sort_relationships_skips_falsy_model(self):
        """A top-level attribute resolving to a falsy model is skipped.

        diffsync forbids a falsy model at class-definition time, so simulate it by
        overriding the resolved attribute on the instance.
        """
        source = NoSortFieldsAdapter(job=MagicMock())
        target = NoSortFieldsAdapter(job=MagicMock())
        for adapter in (source, target):
            adapter.add(BasicNautobotTag(name="tag1"))
        target.tag = None
        sort_relationships(source, target)  # getattr(target, "tag") is None -> continue
