"""Tests for contrib.NautobotModel."""

from typing import TypedDict

from django.core.exceptions import FieldDoesNotExist
from nautobot.core.testing import TestCase

from nautobot_ssot.contrib.enums import AttributeType
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.tests.contrib.models import DeviceModel, LocationTypeModel


class SoftwareImageFileDict(TypedDict):
    """Example software image file dict."""

    image_file_name: str


class TagDict(TypedDict):
    """Exampe tag Dict."""

    name: str


class DeviceDict(TypedDict):
    """Example device dict."""

    name: str


class TestGetAttrEnum(TestCase):
    """Unittests for the `get_attr_enum` class method."""

    # Standard Attributes
    # ===================
    def test_get_string_attribute(self):
        """Test that 'DeviceModel.name' is detected as a standard attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("name"), AttributeType.STANDARD)

    def test_get_optional_integer_attribute(self):
        """Test that 'DeviceModel.vc_position' is detected as a standard attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("vc_position"), AttributeType.STANDARD)

    def test_get_bool_attribute(self):
        """Test that 'LocationType.nestable' is detected as a standard attribute."""
        self.assertEqual(LocationTypeModel.get_attr_enum("nestable"), AttributeType.STANDARD)

    # Foreign Keys
    # ============
    def test_get_foreign_key_attribute(self):
        """Test that 'DeviceModel.status__name' is detected as a foreign key attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("status__name"), AttributeType.FOREIGN_KEY)

    def test_get_optional_foreign_key_attribute(self):
        """Test that 'DeviceModel.tenant__name' is detected as a foreign key attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("tenant__name"), AttributeType.FOREIGN_KEY)

    # N to Many Relationships
    # =======================
    def test_get_n_to_many_attribute(self):
        """Test that 'DeviceModel.tags' is detected as a N-to-many relationship attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("tags"), AttributeType.N_TO_MANY_RELATIONSHIP)

    def test_get_optional_n_to_many_attribute(self):
        """Test that 'DeviceModel.software_image_files' is detected as a N-to-many relationship attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("software_image_files"), AttributeType.N_TO_MANY_RELATIONSHIP)

    # Custom Fields
    # =============
    def test_get_custom_string(self):
        """Test that 'DeviceModel.custom_str' is detected as a custom field attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("custom_str"), AttributeType.CUSTOM_FIELD)

    def test_get_custom_int(self):
        """Test that 'DeviceModel.custom_int' is detected as a custom field attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("custom_int"), AttributeType.CUSTOM_FIELD)

    def test_get_custom_bool(self):
        """Test that 'DeviceModel.custom_bool' is detected as a custom field attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("custom_bool"), AttributeType.CUSTOM_FIELD)

    # Custom Foreign Keys
    # ===================
    def test_get_custom_foreign_key_attribute(self):
        """Test that 'DeviceModel.parent__name' is detected as a custom foreign key attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("parent__name"), AttributeType.CUSTOM_FOREIGN_KEY)

    # Custom N to Many Relationships
    # ==============================
    def test_get_custom_n_to_many_attribute(self):
        """Test that 'DeviceModel.children' is detected as a custom N-to-many relationship attribute."""
        self.assertEqual(DeviceModel.get_attr_enum("children"), AttributeType.CUSTOM_N_TO_MANY_RELATIONSHIP)

    # Invalid attributes
    # ==================
    def test_non_existant_attribute(self):
        """Test that an invalid field raises FieldDoesNotExist."""
        with self.assertRaises(FieldDoesNotExist):
            DeviceModel.get_attr_enum("invalid_field")

    def test_undefined_attribute(self):
        """Test that an undefined attribute raises KeyError."""
        with self.assertRaises(KeyError):
            DeviceModel.get_attr_enum("undefined_attr")


class TestMethodGetSyncedParameters(TestCase):
    """Tests for manipulating custom relationships through the shared base model code."""

    def test_single_identifer(self):
        """Test a single identifier."""

        class LocalModel(NautobotModel):
            """Example class for testing."""

            _identifiers = ("name",)
            _attributes = ()

            name: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 1)
        self.assertIn("name", result)

    def test_multiple_identifiers(self):
        """Test multiple identifiers, including a related field."""

        class LocalModel(NautobotModel):
            """Example class for testing."""

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
            """Example class for testing."""

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
            """Example class for testing."""

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
            """Example class for testing."""

            _identifiers = ()
            _attributes = ()

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 0)
        self.assertEqual(LocalModel.get_synced_attributes(), [])
