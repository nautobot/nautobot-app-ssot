from django.test import TestCase, TransactionTestCase

from nautobot.dcim.models import LocationType, Location
from nautobot_ssot.contrib.dataclasses.attributes import (
    StandardAttribute,
    ForeignKeyAttribute,
)
from diffsync import DiffSyncModel
from typing_extensions import Optional, get_type_hints
from nautobot.extras.models import Status



class LocationModel(DiffSyncModel):
    """"""

    _model = Location
    _modelname = "location"
    _identifiers = (
        "name",
        "parent__name",
        "parent__location_type__name",
    )
    _attributes = ("description", "latitude",)

    name: str
    parent__name: str
    parent__location_type__name: str
    description: Optional[str] = ""
    latitude: Optional[int] = ""


class BaseTestCase(TestCase):
    """"""

    def _load_location_types(self):
        self.location_type_1 = LocationType(
            name="Test Location Type",
        )
        self.location_type_1.save()

    def _load_locations(self):
        status = Status.objects.get(name="Active")
        self.location_1 = Location(
            name="Location 1",
            location_type=self.location_type_1,
            status=status,
        )
        self.location_1.save()

        status = Status.objects.get(name="Active")
        self.location_2 = Location(
            name="Location 2",
            location_type=self.location_type_1,
            parent=self.location_1,
            status=status,
        )
        self.location_2.save()

    def setUp(self):
        """Setup the test cases."""
        self._load_location_types()
        self._load_locations()
        self.model_type_hints = get_type_hints(LocationModel, include_extras=True)


class TestStandardAttribute(BaseTestCase):
    """Test cases for standard attributes."""

    def setUp(self):
        """"""
        super().setUp()
        self.name = StandardAttribute(
            name="name",
            model_class=Location,
            type_hints=self.model_type_hints["name"],
        )
        self.description = StandardAttribute(
            name="description",
            model_class=Location,
            type_hints=self.model_type_hints["description"],
        )
        self.latitude = StandardAttribute(
            name="latitude",
            model_class=Location,
            type_hints=self.model_type_hints["latitude"],
        )

    def test_get_standard_attribute(self):
        """Test loading a standard attribute."""
        result = self.name.load(self.location_1)
        self.assertEqual("Location 1", result)

    def test_optional_blank_not_none_attribute(self):
        """Test loading an optional string attribute without a value, but not None in database.
        
        Django validated save for `blank=True` and `null=False` means a validated save will allow an
        empty string or None value, but the database will not except a null value.
        """
        result = self.description.load(self.location_1)
        self.assertIsNotNone(result)
        self.assertEqual(result, "")

    def test_optional_value(self):
        """Test for loading an optional value that can be a null value."""
        result = self.latitude.load(self.location_1)
        self.assertIsNone(result)


class TestForeignKeyAttribute(BaseTestCase):
    """Test getting values for foreign key attributes."""

    def setUp(self):
        """"""
        super().setUp()
        self.parent_name = ForeignKeyAttribute(
            "parent__name",
            model_class=Location,
            type_hints=self.model_type_hints["parent__name"],
        )
        self.parent_location_type_name = ForeignKeyAttribute(
            "parent__location_type__name",
            model_class=Location,
            type_hints=self.model_type_hints["parent__location_type__name"],
        )

    def test_instantiate(self):
        """Test to ensure class is properly instantiated."""
        self.assertEqual(len(self.parent_name.lookups), 1)
        self.assertEqual(self.parent_name.related_attr_name, "name")

    def test_invalid_attribute_name(self):
        """"""
        with self.assertRaises(ValueError):
            ForeignKeyAttribute(
                "parent",
                model_class=Location,
                type_hints=self.model_type_hints["parent__name"]
            )
    
    def test_empty_foreign_key(self):
        """Test an unset foreign key."""
        self.assertIsNone(self.parent_name.load(self.location_1))

    def test_nested_instantiate(self):
        """Test to make sure a nested foreign key attribute is properly instantiated."""
        self.assertAlmostEqual(len(self.parent_location_type_name.lookups), 2)
        self.assertEqual(self.parent_location_type_name.related_attr_name, "name")

    def test_load_valid_foreign_key(self):
        """"""
        result = self.parent_name.load(self.location_2)
        self.assertEqual(result, "Location 1")

    def test_nested_load_valid_foreign_key(self):
        """Test getting value from nested relationship name."""
        result = self.parent_location_type_name.load(self.location_2)
        self.assertEqual(result, "Test Location Type")
