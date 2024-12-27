
from typing import List, Optional
from unittest import skip
from unittest.mock import MagicMock

from nautobot_ssot.contrib.types import FieldType
import nautobot.circuits.models as circuits_models
import nautobot.dcim.models as dcim_models
import nautobot.extras.models as extras_models
import nautobot.ipam.models as ipam_models
import nautobot.tenancy.models as tenancy_models
from diffsync.exceptions import ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated
from django.contrib.contenttypes.models import ContentType
#from nautobot.core.testing import TestCase
from django.test import TestCase as TestCase
from nautobot.dcim.choices import InterfaceTypeChoices
from typing_extensions import Annotated, TypedDict
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.sorting import (
    _find_list_sort_key,
    _get_sortable_list_type_from_annotations,
    _sort_top_level_model_attributes,
    _get_sortable_fields_from_model,
    _is_sortable_field,
    _get_sortable_obj_type,
    _get_sortable_obj_sort_key,
    sort_relationships,
)

from nautobot_ssot.contrib import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    NautobotAdapter,
    NautobotModel,
    RelationshipSideEnum,
)

class BasicTagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    id: int
    name: str


class TagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    id: int
    name: Annotated[str, FieldType.SORT_BY]
    description: Optional[str]


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


class TestCaseIsSortableField(TestCase):
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


class TestGetSortKey(TestCase):
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




class TestCaseGetSortableFieldsFromModel(TestCase):
    """"""















'''


class TestCaseGetSortableEntriesFunction(TestCase):
    """"""

    def test_nonsortable_entry(self):
        """"""
        test = _get_sortable_list_type_from_annotations(BasicNautobotTenant, "description")
        self.assertIsNone(test)

    def test_sortable_entry_without_annotation(self):
        """"""
        test = _get_sortable_list_type_from_annotations(BasicNautobotTenant, "tags")
        self.assertEqual(test, BasicTagDict)

    def test_sortable_entry_with_annotation(self):
        """"""
        test = _get_sortable_list_type_from_annotations(NautobotTenant, "tags")
        self.assertEqual(test, TagDict)


class TestCaseGetSortKeyFunction(TestCase):
    """"""

    def test_without_sort_key_annotation(self):
        """"""
        test = _find_list_sort_key(BasicTagDict)
        self.assertIsNone(test)

    def test_with_sort_key_annotation(self):
        """"""
        test = _find_list_sort_key(TagDict)
        self.assertEqual(test, "name")

'''
