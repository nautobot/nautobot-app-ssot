#from nautobot.core.testing import TestCase
from unittest import TestCase
from nautobot.dcim.models import Device
from typing_extensions import get_type_hints, Annotated
from nautobot_ssot.contrib.dataclasses.attributes import ForeignKeyAttribute
from nautobot.dcim.models import LocationType


class BasicModel:
    """Simple class used for getting annotation data to the test cases."""

    name: str
    parent__name: str
    parent__parent__name: str


class TestLoadCustomFieldAttribute(TestCase):

    def setUp(self):
        self.annotations = get_type_hints(BasicModel)
        self.location_type_1 = LocationType(
            name="Location Type 1",
            parent=None,
        )

        self.location_type_2 = LocationType(
            name="location Type 2",
            parent=self.location_type_1,
        )

        self.location_type_3 = LocationType(
            name="location Type 3",
            parent=self.location_type_2,
        )

        self.parent_name = ForeignKeyAttribute(
            name="parent__name",
            annotation=self.annotations["parent__name"]
        )

        self.parent_parent_name = ForeignKeyAttribute(
            name="parent__parent__name",
            annotation=self.annotations["parent__parent__name"]
        )

    def test_invalid_foreign_key_reference(self):
        with self.assertRaises(ValueError):
            ForeignKeyAttribute(
                name="name",
                annotation=self.annotations["name"],
            )

    def test_get_foreign_key_nonetype(self):
        result = self.parent_name.load(self.location_type_1)
        self.assertIsNone(result)

    def test_get_foreign_key_single_level(self):
        result = self.parent_name.load(self.location_type_2)
        self.assertEqual(result, "Location Type 1")

    def test_get_foreign_key_multi_level(self):
        result = self.parent_parent_name.load(self.location_type_3)
        self.assertEqual(result, "Location Type 1")
