from django.test.testcases import TestCase

from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status
from typing_extensions import TypedDict
from nautobot_ssot.contrib.helpers import load_typed_dict, get_nested_related_attribute_value
from nautobot_ssot.tests.contrib.dataclasses.test_attributes import BaseTestCase
class LocationDict(TypedDict):
    """Test location dict."""

    name: str
    location_type__name: str
    parent__name: str
    parent__location_type__name: str
    status__name: str

class TestGetNestedRelatedAttributeValue(BaseTestCase):
    """"""

    def test_single_lookup(self):
        """"""
        result = get_nested_related_attribute_value("parent__name", self.location_2)
        self.assertEqual(result, "Location 1")

    def test_multi_lookup(self):
        """"""
        result = get_nested_related_attribute_value(
            "parent__location_type__name", self.location_2
        )
        self.assertEqual(result, "Test Location Type")


class TestLoadTypedDict(BaseTestCase):
    """"""

    def test_load_full_dict(self):
        """"""
        result = load_typed_dict(LocationDict, self.location_2)
        self.assertEqual(result["name"], "Location 2")
        self.assertEqual(result["parent__name"], "Location 1")
        self.assertEqual(result["parent__location_type__name"], "Test Location Type")

    def test_load_with_none(self):
        """"""
        result = load_typed_dict(LocationDict, self.location_1)
        self.assertIsNone(result["parent__name"])
        self.assertIsNone(result["parent__location_type__name"])
    