"""Unit tests for contrib sorting."""

from typing import Annotated, List, Optional
from unittest import skip
from unittest.mock import MagicMock

from nautobot.dcim.models import Device
from django.test import TestCase
from nautobot.extras.models import Tag
from nautobot.tenancy.models import Tenant
from typing_extensions import TypedDict, get_type_hints

from nautobot_ssot.contrib import NautobotModel

from nautobot_ssot.contrib.types import CustomFieldAnnotation, CustomRelationshipAnnotation, RelationshipSideEnum

from nautobot_ssot.contrib.enums import AttributeType
from nautobot_ssot.contrib.mixins import ModelAttributeMethods



class SoftwareImageFileDict(TypedDict):
    """Basic typed dict for many to many field reference."""

    image_file_name: str


class TenantDict(TypedDict):
    """Basic TypedDict for custom many to many field reference."""

class NautobotDevice(ModelAttributeMethods):
    """A basic device model implementation for testing the `ModelAttributeMethods` mixin class."""

    _model = Device

    # NOTE: Fields listed here may not match fields in specified model, this does not impact unit tests
    #       except for N-to-Many relationship fields.
    name: str
    vc_position: int
    bool_field: bool
    tenant__name: str
    software_image_files: List[SoftwareImageFileDict]

    # Custom Fields
    custom_field_attr: Annotated[
        str,
        CustomFieldAnnotation(name="Test Custom Field")
    ]
    custom_foreign_key__name: Annotated[
        str,
        CustomRelationshipAnnotation(name="Custom Foreign Key", side=RelationshipSideEnum.SOURCE)
    ]
    custom_foreign_many_to_many: Annotated[
        List[TenantDict],
        CustomRelationshipAnnotation(name="Custom Many to Many", side=RelationshipSideEnum.SOURCE)
    ]


##############
# UNIT TESTS #
##############

class TestGetAttributeAnnotation(TestCase):

    def test_no_annotation(self):
        self.assertIsNone(NautobotDevice.get_annotation("name"))

    def test_custom_field_annotation(self):
        result: CustomFieldAnnotation = NautobotDevice.get_annotation("custom_field_attr")
        self.assertIsInstance(result, CustomFieldAnnotation)
        self.assertEqual(result.name, "Test Custom Field")


class TestGetAttributeType(TestCase):

    def test_invalid_attribute(self):
        with self.assertRaises(KeyError):
            NautobotDevice.get_attr_type("invalid_name")

    def test_get_standard_char_field(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("name"),
            AttributeType.STANDARD,
        )

    def test_get_standard_int_field(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("vc_position"),
            AttributeType.STANDARD,
        )

    def test_get_foreign_key_type(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("tenant__name"),
            AttributeType.FOREIGN_KEY,
        )

    def test_get_many_to_many_field_type(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("software_image_files"),
            AttributeType.N_TO_MANY_RELATIONSHIP,
        )

    def test_get_custom_field_type(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("custom_field_attr"),
            AttributeType.CUSTOM_FIELD,
        )

    def test_get_custom_foreign_key_type(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("custom_foreign_key__name"),
            AttributeType.CUSTOM_FOREIGN_KEY,
        )

    def test_get_custom_many_to_many_relationship(self):
        self.assertEqual(
            NautobotDevice.get_attr_type("custom_foreign_many_to_many"),
            AttributeType.CUSTOM_N_TO_MANY_RELATIONSHIP,
        )


