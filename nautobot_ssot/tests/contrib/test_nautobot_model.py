"""Tests for contrib.NautobotModel."""

from typing import Annotated, List, Optional, TypedDict

from django.core.exceptions import FieldDoesNotExist
from nautobot.core.testing import TestCase
from nautobot.dcim.models import Device

from nautobot_ssot.contrib.enums import AttributeType, RelationshipSideEnum
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
)


class SoftwareImageFileDict(TypedDict):
    """Example software image file dict."""

    image_file_name: str


class TagDict(TypedDict):
    """Exampe tag Dict."""

    name: str


class DeviceDict(TypedDict):
    """Example device dict."""


class TestGetAttrEnum(TestCase):
    """Unittests for the `get_attr_enum` class method."""

    class DeviceModel(NautobotModel):
        """Example model for unittests.

        NOTE: We only need the typehints for this set of unittests.
        """

        _modelname = "device"
        _model = Device

        # Standard Attributes
        name: str
        vc_position: Optional[int]
        # NOTE: `vc_priority` field is not actually bool, but is an integer.
        #       `bool` is used here for testing purposes only since the method tested requires standard fields to be
        #       actual fields in the ORM model while checking for the `AttributeType` enum.
        #       This may change in the future as tests further expand.
        vc_priority: bool

        # Foreign Keys
        status__name: str
        tenant__name: Optional[str]

        # N to many Relationships
        tags: List[TagDict] = []
        software_image_files: Optional[List[SoftwareImageFileDict]]

        # Custom Fields
        custom_str: Annotated[str, CustomFieldAnnotation(name="custom_str")]
        custom_int: Annotated[int, CustomFieldAnnotation(name="custom_int")]
        custom_bool: Optional[Annotated[bool, CustomFieldAnnotation(name="custom_bool")]]

        # Custom Foreign Keys
        parent__name: Annotated[
            str, CustomRelationshipAnnotation(name="device_parent", side=RelationshipSideEnum.SOURCE)
        ]

        # Custom N to Many Relationships
        children: Annotated[
            List[DeviceDict],
            CustomRelationshipAnnotation(name="device_children", side=RelationshipSideEnum.DESTINATION),
        ]

        # Invalid Fields
        invalid_field: str

    # Standard Attributes
    # ===================
    def test_get_string_attribute(self):
        """Test that 'name' is detected as a standard attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("name"), AttributeType.STANDARD)

    def test_get_optional_integer_attribute(self):
        """Test that 'vc_position' is detected as a standard attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("vc_position"), AttributeType.STANDARD)

    def test_get_bool_attribute(self):
        """Test that 'vc_priority' is detected as a standard attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("vc_priority"), AttributeType.STANDARD)

    # Foreign Keys
    # ============
    def test_get_foreign_key_attribute(self):
        """Test that 'status__name' is detected as a foreign key attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("status__name"), AttributeType.FOREIGN_KEY)

    def test_get_optional_foreign_key_attribute(self):
        """Test that 'tenant__name' is detected as a foreign key attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("tenant__name"), AttributeType.FOREIGN_KEY)

    # N to Many Relationships
    # =======================
    def test_get_n_to_many_attribute(self):
        """Test that 'tags' is detected as a N-to-many relationship attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("tags"), AttributeType.N_TO_MANY_RELATIONSHIP)

    def test_get_optional_n_to_many_attribute(self):
        """Test that 'software_image_files' is detected as a N-to-many relationship attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("software_image_files"), AttributeType.N_TO_MANY_RELATIONSHIP)

    # Custom Fields
    # =============
    def test_get_custom_string(self):
        """Test that 'custom_str' is detected as a custom field attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("custom_str"), AttributeType.CUSTOM_FIELD)

    def test_get_custom_int(self):
        """Test that 'custom_int' is detected as a custom field attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("custom_int"), AttributeType.CUSTOM_FIELD)

    def test_get_custom_bool(self):
        """Test that 'custom_bool' is detected as a custom field attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("custom_bool"), AttributeType.CUSTOM_FIELD)

    # Custom Foreign Keys
    # ===================
    def test_get_custom_foreign_key_attribute(self):
        """Test that 'parent__name' is detected as a custom foreign key attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("parent__name"), AttributeType.CUSTOM_FOREIGN_KEY)

    # Custom N to Many Relationships
    # ==============================
    def test_get_custom_n_to_many_attribute(self):
        """Test that 'children' is detected as a custom N-to-many relationship attribute."""
        self.assertEqual(self.DeviceModel.get_attr_enum("children"), AttributeType.CUSTOM_N_TO_MANY_RELATIONSHIP)

    # Invalid attributes
    # ==================
    def test_non_existant_attribute(self):
        """Test that an invalid field raises FieldDoesNotExist."""
        with self.assertRaises(FieldDoesNotExist):
            self.DeviceModel.get_attr_enum("invalid_field")

    def test_undefined_attribute(self):
        """Test that an undefined attribute raises KeyError."""
        with self.assertRaises(KeyError):
            self.DeviceModel.get_attr_enum("undefined_attr")


class TestMethodGetSyncedParameters(TestCase):
    """Tests for manipulating custom relationships through the shared base model code."""

    def test_single_identifer(self):
        """Test a single identifier."""

        class LocalModel(NautobotModel):
            _identifiers = ("name",)
            _attributes = ()

            name: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 1)
        self.assertIn("name", result)

    def test_multiple_identifiers(self):
        """Test multiple identifiers, including a related field."""

        class LocalModel(NautobotModel):
            _identifiers = (
                "name",
                "parent__name",
            )
            _attributes = ()

            name: str
            parent__name: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 2)
        self.assertIn("name", result)
        self.assertIn("parent__name", result)

    def test_only_attributes(self):
        """Test only attributes."""

        class LocalModel(NautobotModel):
            _identifiers = ()
            _attributes = ("description", "status")

            description: str
            status: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 2)
        self.assertIn("description", result)
        self.assertIn("status", result)

    def test_identifiers_and_attributes(self):
        """Test both identifiers and attributes."""

        class LocalModel(NautobotModel):
            _identifiers = ("name",)
            _attributes = ("description", "status")

            name: str
            description: str
            status: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 3)
        self.assertIn("name", result)
        self.assertIn("description", result)
        self.assertIn("status", result)

    def test_empty_identifiers_and_attributes(self):
        """Test empty identifiers and attributes."""

        class LocalModel(NautobotModel):
            _identifiers = ()
            _attributes = ()

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 0)
        self.assertEqual(LocalModel.get_synced_attributes(), [])
