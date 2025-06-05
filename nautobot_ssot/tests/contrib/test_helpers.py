"""Unittests for contrib helper functions."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, Status
from nautobot.ipam.models import VLAN, Prefix
from typing_extensions import TypedDict

from nautobot_ssot.contrib.helpers import (
    get_nested_related_attribute_value,
    get_relationship_parameters,
    load_typed_dict,
)
from nautobot_ssot.contrib.types import RelationshipSideEnum
from nautobot_ssot.tests.contrib.dataclasses.test_attributes import BaseTestCase


class LocationDict(TypedDict):
    """Test location dict."""

    name: str
    location_type__name: str
    parent__name: str
    parent__location_type__name: str
    status__name: str


class TestGetNestedRelatedAttributeValue(BaseTestCase):
    """Unit tests for `get_nested_related_attribute_value` function."""

    def test_single_lookup(self):
        """"""
        result = get_nested_related_attribute_value("parent__name", self.location_2)
        self.assertEqual(result, "Location 1")

    def test_multi_lookup(self):
        """"""
        result = get_nested_related_attribute_value("parent__location_type__name", self.location_2)
        self.assertEqual(result, "Test Location Type")

    def test_invalid_attr_name(self):
        """Test for raised ValueError with invalid attribute name."""
        with self.assertRaises(ValueError):
            get_nested_related_attribute_value("invalid_name", self.location_2)


class TestLoadTypedDict(BaseTestCase):
    """Unit tests for `load_typed_dict` function."""

    def test_load_full_dict(self):
        """Test loading a TypedDict object with full foreign key values."""
        result = load_typed_dict(LocationDict, self.location_2)
        self.assertEqual(result["name"], "Location 2")
        self.assertEqual(result["parent__name"], "Location 1")
        self.assertEqual(result["parent__location_type__name"], "Test Location Type")

    def test_load_with_none(self):
        """Test loading TypedDict object with foreign key as None."""
        result = load_typed_dict(LocationDict, self.location_1)
        self.assertIsNone(result["parent__name"])
        self.assertIsNone(result["parent__location_type__name"])


class TestGetRelationshipParameters(TestCase):
    """Unittests for `get_relationship_parameters` function."""

    def setUp(self):
        """Set up the test cases."""
        status = Status.objects.get(name="Active")

        self.prefix_type = ContentType.objects.get_for_model(Prefix)
        self.vlan_type = ContentType.objects.get_for_model(VLAN)

        self.prefix1 = Prefix.objects.create(
            prefix="10.0.0.0/24",
            status=status,
            type="Network",
        )
        self.vlan1 = VLAN.objects.create(
            vid=101,
            name="TEST_VLAN",
            status=status,
        )
        self.relationship1 = Relationship.objects.create(
            label="Test Relationship",
            type=RelationshipTypeChoices.TYPE_ONE_TO_ONE,
            source_type=self.prefix_type,
            destination_type=self.vlan_type,
        )

    def test_get_standard_relationship(self):
        """Test loading valid relationship."""
        result = get_relationship_parameters(
            obj=self.prefix1, relationship=self.relationship1, relationship_side=RelationshipSideEnum.SOURCE
        )
        self.assertEqual(result["relationship"], self.relationship1)
        self.assertEqual(result["source_type"], self.prefix_type)
        self.assertEqual(result["destination_type"], self.vlan_type)
        self.assertEqual(result["source_id"], self.prefix1.id)
