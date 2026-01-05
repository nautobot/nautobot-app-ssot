"""Unit tests for contrib sorting."""

from typing import Annotated, List, Optional
from unittest import skip
from unittest.mock import MagicMock

from nautobot.dcim.models import Device
from django.test import TestCase
from nautobot.extras.models import Tag
from nautobot.tenancy.models import Tenant
from typing_extensions import TypedDict, get_type_hints

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.contrib.sorting import (
    _is_sortable_field,
    get_sort_key_from_typed_dict,
    get_sortable_fields_from_model,
    sort_relationships,
)
from nautobot_ssot.contrib.typeddicts import SortKey

from nautobot_ssot.contrib.types import CustomFieldAnnotation, CustomRelationshipAnnotation, RelationshipSideEnum

from nautobot_ssot.contrib.enums import AttributeType




class NautobotDevice(NautobotModel):
    """A basic tenant model for testing the `NautobotModel` base class."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("tenant__name", "custom_1",)

    name: str
    tenant__name: str
    custom_1: Annotated[str, CustomFieldAnnotation(name="Test Custom Field")]
    custom_relationship__name: Annotated[str, CustomRelationshipAnnotation(name="Custom Foreign Key", side=RelationshipSideEnum.SOURCE)]


##############
# UNIT TESTS #
##############

class TestGetAttributeAnnotation(TestCase):

    def test_no_annotation(self):
        self.assertIsNone(NautobotDevice.get_annotation("name"))

    def test_custom_field_annotation(self):
        result: CustomFieldAnnotation = NautobotDevice.get_annotation("custom_1")
        self.assertIsInstance(result, CustomFieldAnnotation)
        self.assertEqual(result.name, "Test Custom Field")


class TestGetAttributeType(TestCase):

    def test_get_foreign_key(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("tenant__name"),
            AttributeType.FOREIGN_KEY,
        )

    def test_get_custom_field(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("custom_1"),
            AttributeType.CUSTOM_FIELD,
        )

    


