"""Unittests for ORM utility functions."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.circuits.models import Provider
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, RelationshipAssociation, Status
from typing_extensions import Optional, TypedDict

from nautobot_ssot.contrib.types import RelationshipSideEnum
from nautobot_ssot.utils.orm import (
    get_custom_relationship_association_parameters,
    get_orm_attribute,
    load_typed_dict,
    orm_attribute_lookup,
)


class BaseTestCase(TestCase):
    """Base class with common setup for test cases."""

    def setUp(self):
        """Set up the unittests."""
        status = Status.objects.get(name="Active")
        self.location_type_1 = LocationType.objects.create(
            name="Location Type 1",
        )
        self.location_type_2 = LocationType.objects.create(
            name="Location Type 2", description="Test Location", parent=self.location_type_1
        )
        self.location_1 = Location.objects.create(
            name="Location 1",
            location_type=self.location_type_1,
            status=status,
        )
        self.location_2 = Location.objects.create(
            name="Location 2",
            location_type=self.location_type_2,
            parent=self.location_1,
            status=status,
        )


class TestGetORMAttribute(BaseTestCase):
    """Unit tests for `get_orm_attribute` function."""

    #################################################
    # ERROR RAISING
    #################################################

    def test_invalid_attribute(self):
        """Test with attribute name that doesn't exist in the ORM object."""
        with self.assertRaises(AttributeError):
            get_orm_attribute(self.location_2, "invalid_attribute")

    def test_invalid_db_obj_type(self):
        """Test function with `db_obj` input type other than ORM object."""
        with self.assertRaises(AttributeError):
            get_orm_attribute("string", "name")
            get_orm_attribute({"mydict": "value"}, "name")
            get_orm_attribute(42, "name")

    def test_foreign_key_lookup(self):
        """Test with foreign key lookup."""
        with self.assertRaises(AttributeError):
            get_orm_attribute(self.location_1, "parent__name")

    #################################################
    # ORM Attributes
    #################################################

    def test_get_basic_attribute(self):
        """Test getting a basic attribute."""
        result = get_orm_attribute(self.location_1, "name")
        self.assertEqual(result, "Location 1")

    def test_get_null_attribute(self):
        """Test getting a null attribute."""
        result = get_orm_attribute(self.location_1, "latitude")
        self.assertIsNone(result)


class TestORMAttributeLookup(BaseTestCase):
    """Unit tests for `orm_attribute_lookup` function."""

    #################################################
    # ERROR RAISING
    #################################################

    # `db_obj` variations

    def test_invalid_foreign_key(self):
        """Test with attribute name that doesn't exist in the ORM object."""
        with self.assertRaises(AttributeError):
            orm_attribute_lookup(self.location_2, "parent__invalid_attribute")

    def test_db_obj_input_type_str(self):
        """Test function with `db_obj` input type `str`."""
        with self.assertRaises(TypeError):
            orm_attribute_lookup("string", "parent__name")

    def test_db_obj_input_type_int(self):
        """Test function with `db_obj` input type `int`."""
        with self.assertRaises(TypeError):
            orm_attribute_lookup(42, "parent__name")

    def test_db_obj_input_type_dict(self):
        """Test function with `db_obj` input type `dict`."""
        with self.assertRaises(TypeError):
            orm_attribute_lookup({"name": "Invalid", "parent__name": "Invalid Parent Name"}, "parent__name")

    # `attr_name` input variations

    def test_attr_name_input_type_int(self):
        """Test function with `attr_name` input type `int`."""
        with self.assertRaises(TypeError):
            orm_attribute_lookup(self.location_1, 42)

    def test_attr_name_input_type_orm_obj(self):
        """Test function with `attr_name` input type `Model`."""
        with self.assertRaises(TypeError):
            orm_attribute_lookup(self.location_1, self.location_1)

    def test_attr_name_input_type_bool(self):
        """Test function with `attr_name` input type `bool`."""
        with self.assertRaises(TypeError):
            orm_attribute_lookup(self.location_1, True)

    def test_attr_name_input_type_none(self):
        """Test function with `attr_name` input type `None`."""
        with self.assertRaises(TypeError):
            orm_attribute_lookup(self.location_1, None)

    #################################################
    # ORM Attributes
    #################################################

    def test_get_basic_attribute(self):
        """"""
        result = orm_attribute_lookup(self.location_1, "name")
        self.assertTrue(result, "Location 1")

    def test_get_null_attribute(self):
        """"""
        result = orm_attribute_lookup(self.location_1, "latitude")
        self.assertIsNone(result)

    #################################################
    # SINGLE LEVEL LOOKUPS
    #################################################

    def test_single_level_lookup(self):
        """Test a single-level string lookup."""
        result = orm_attribute_lookup(self.location_1, "location_type__name")
        self.assertEqual(result, "Location Type 1")

    def test_single_level_none_result(self):
        """Test single level lookup with None result."""
        result = orm_attribute_lookup(self.location_1, "parent__name")
        self.assertIsNone(result)

    def test_single_level_blank_str_result(self):
        """Test single level lookup with blank string result."""
        result = orm_attribute_lookup(self.location_1, "location_type__description")
        self.assertEqual(result, "")

    def test_single_level_orm_object_return(self):
        """Test looking up single attribute when return type is ORM object."""
        result = orm_attribute_lookup(self.location_2, "parent__location_type")
        self.assertIsInstance(result, LocationType)

    #################################################
    # MULTI LEVEL LOOKUPS
    #################################################

    def test_multi_level_lookup(self):
        """Test a multi-level lookup."""
        result = orm_attribute_lookup(self.location_2, "parent__location_type__name")
        self.assertEqual(result, "Location Type 1")

    def test_multi_level_intermediate_none_result(self):
        """Test multi level lookup with None result."""
        result = orm_attribute_lookup(self.location_2, "parent__parent__location_type__name")
        self.assertIsNone(result)

    def test_multi_level_blank_str_result(self):
        """Test multi level lookup with blank string result."""
        result = orm_attribute_lookup(self.location_2, "parent__location_type__description")
        self.assertEqual(result, "")

    def test_multi_level_with_none_object(self):
        """Test multi level lookup with first related object as None."""
        result = orm_attribute_lookup(self.location_1, "parent__location_type__description")
        self.assertIsNone(result)

    def test_multi_level_with_empty_string_final_result(self):
        """Test multi level lookup where final attribute is None."""
        result = orm_attribute_lookup(self.location_2, "parent__location_type__description")
        self.assertEqual(result, "")


class TestLoadTypedDict(BaseTestCase):
    """Unittests for `load_typed_dict` function."""

    class LocationTypeDict(TypedDict):
        """Test LocationType Typed Dict."""

        name: str
        description: Optional[str]
        parent__name: Optional[str]

    class LocationDict(TypedDict):
        """Test location TypedDict."""

        name: str
        location_type__name: str
        parent__name: Optional[str]
        description: Optional[str]
        parent__location_type__name: Optional[str]
        status__name: str

    #################################################
    # ERROR RAISING
    #################################################

    def test_typed_dict_instance(self):
        """Test raising error on passing instance of typed dict."""
        with self.assertRaises(TypeError):
            load_typed_dict(
                self.LocationTypeDict(name="Test Location Type"),
                self.location_type_1,
            )

    def test_invalid_string_type(self):
        """Test raising error on passing instance of typed dict."""
        with self.assertRaises(TypeError):
            load_typed_dict(
                self.LocationTypeDict,
                "Test String",
            )

    #################################################
    # LOADING TESTS
    #################################################

    def test_load_basic_location_type(self):
        """Load a basic TypedDict with location type."""
        result = load_typed_dict(
            self.LocationTypeDict,
            self.location_type_1,
        )
        self.assertEqual(result["name"], "Location Type 1")
        self.assertEqual(result["description"], "")
        self.assertEqual(result["parent__name"], None)

    def test_load_basic_location(self):
        """Load a basic typed dict with location."""
        result = load_typed_dict(
            self.LocationDict,
            self.location_1,
        )
        self.assertEqual(result["name"], "Location 1")
        self.assertEqual(result["description"], "")
        self.assertEqual(result["parent__name"], None)
        self.assertEqual(result["status__name"], "Active")

    def test_load_with_foreign_key(self):
        """Load typed dict with location type and foreign keys."""
        result = load_typed_dict(
            self.LocationTypeDict,
            self.location_type_2,
        )
        self.assertEqual(result["name"], "Location Type 2")
        self.assertEqual(result["description"], "Test Location")
        self.assertEqual(result["parent__name"], "Location Type 1")


class TestGetCustomRelationshipAssociationParameters(BaseTestCase):
    """Tests for `get_custom_relationship_assocation_parameters` function."""

    def setUp(self):
        super().setUp()

        self.location_type = ContentType.objects.get_for_model(Location)
        self.provider_type = ContentType.objects.get_for_model(Provider)
        self.relationship_1 = Relationship.objects.create(
            label="Test Relationship 1",
            type=RelationshipTypeChoices.TYPE_ONE_TO_ONE,
            source_type=self.provider_type,
            destination_type=self.location_type,
        )

        self.provider_1 = Provider.objects.create(
            name="Provider 1",
        )

        RelationshipAssociation.objects.create(
            relationship=self.relationship_1,
            source=self.provider_1,
            destination=self.location_1,
        )

    #################################################
    # ERROR RAISING
    #################################################

    def test_invalid_relationship_type_string(self):
        """Test with relationship type as a string."""
        with self.assertRaises(AttributeError):
            get_custom_relationship_association_parameters(
                "Invalid String",
                self.provider_1.id,
                RelationshipSideEnum.SOURCE,
            )

    def test_invalid_relationship_type_integer(self):
        """Test with relationship type as an integer."""
        with self.assertRaises(AttributeError):
            get_custom_relationship_association_parameters(
                42,
                self.provider_1.id,
                RelationshipSideEnum.SOURCE,
            )

    def test_invalid_relationship_type_dict(self):
        """Test with relationship type as a dict."""
        with self.assertRaises(AttributeError):
            get_custom_relationship_association_parameters(
                self.relationship_1.__dict__,
                self.provider_1.id,
                RelationshipSideEnum.SOURCE,
            )

    #################################################
    # BASIC TESTS
    #################################################

    def test_get_one_to_one_from_source(self):
        """Test getting one to one parameters from source."""
        result = get_custom_relationship_association_parameters(
            self.relationship_1,
            self.provider_1.id,
            RelationshipSideEnum.SOURCE,
        )
        self.assertEqual(result["relationship"], self.relationship_1)
        self.assertEqual(result["source_type"], self.provider_type)
        self.assertEqual(result["destination_type"], self.location_type)
        self.assertEqual(result["source_id"], self.provider_1.id)
        self.assertTrue("destination_id" not in result.keys())

    def test_get_one_to_one_from_destination(self):
        """Test getting one to one parameters from source."""
        result = get_custom_relationship_association_parameters(
            self.relationship_1,
            self.location_1.id,
            RelationshipSideEnum.DESTINATION,
        )
        self.assertEqual(result["relationship"], self.relationship_1)
        self.assertEqual(result["source_type"], self.provider_type)
        self.assertEqual(result["destination_type"], self.location_type)
        self.assertEqual(result["destination_id"], self.location_1.id)
        self.assertTrue("source_id" not in result.keys())
