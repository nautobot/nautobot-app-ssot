"""Tests for contrib.NautobotModel."""

from nautobot.core.testing import TestCase

from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.enums import AttributeType
from nautobot.dcim.models import Device
from typing import TypedDict, List, Annotated, Optional

from nautobot.extras.models import (
    Relationship,
    RelationshipAssociation,
    CustomField,
    CustomFieldModel,
    CustomFieldChoice,
)
from nautobot_ssot.contrib.types import (
    CustomAnnotation,
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
)
from django.contrib.contenttypes.models import ContentType
from nautobot_ssot.contrib.enums import RelationshipSideEnum

from django.core.exceptions import FieldDoesNotExist


class SoftwareImageFileDict(TypedDict):
    """Example software image file dict."""

    image_file_name: str


class TagDict(TypedDict):
    """Exampe tag Dict."""

    name: str

class DeviceDict(TypedDict):
    """Example device dict."""




class TestGetAttrEnum(TestCase):
    """"""

    class DeviceModel(NautobotModel):
        """"""

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
        parent__name: Annotated[str, CustomRelationshipAnnotation(name="device_parent", side=RelationshipSideEnum.SOURCE)]

        # Custom N to Many Relationships
        children: Annotated[List[DeviceDict], CustomRelationshipAnnotation(name="device_children", side=RelationshipSideEnum.DESTINATION)]

        # Invalid Fields
        invalid_field: str

    # Standard Attributes
    # ===================
    def test_get_string_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("name"), AttributeType.STANDARD)

    def test_get_optional_integer_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("vc_position"), AttributeType.STANDARD)

    def test_get_bool_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("vc_priority"), AttributeType.STANDARD)

    # Foreign Keys
    # ============
    def test_get_foreign_key_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("status__name"), AttributeType.FOREIGN_KEY)

    def test_get_optional_foreign_key_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("tenant__name"), AttributeType.FOREIGN_KEY)

    # N to Many Relationships
    # =======================
    def test_get_n_to_many_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("tags"), AttributeType.N_TO_MANY_RELATIONSHIP)

    def test_get_optional_n_to_many_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("software_image_files"), AttributeType.N_TO_MANY_RELATIONSHIP)


    # Custom Fields
    # =============
    def test_get_custom_string(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("custom_str"), AttributeType.CUSTOM_FIELD)

    def test_get_custom_int(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("custom_int"), AttributeType.CUSTOM_FIELD)

    def test_get_custom_bool(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("custom_bool"), AttributeType.CUSTOM_FIELD)

    # Custom Foreign Keys
    # ===================
    def test_get_custom_foreign_key_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("parent__name"), AttributeType.CUSTOM_FOREIGN_KEY)

    # Custom N to Many Relationships
    # ==============================
    def test_get_custom_n_to_many_attribute(self):
        self.assertEqual(self.DeviceModel.get_attr_enum("children"), AttributeType.CUSTOM_N_TO_MANY_RELATIONSHIP)

    # Invalid attributes
    # ==================
    def test_non_existant_attribute(self):
        with self.assertRaises(FieldDoesNotExist):
            self.DeviceModel.get_attr_enum("invalid_field")

    def test_undefined_attribute(self):
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
