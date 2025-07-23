#from nautobot.core.testing import TestCase
from unittest import TestCase
from nautobot.dcim.models import Device
from typing_extensions import get_type_hints, Annotated
from nautobot_ssot.contrib.dataclasses.attributes import CustomFieldAttribute
from nautobot.dcim.models import Interface
from nautobot_ssot.contrib.types import CustomFieldAnnotation
from nautobot.dcim.models import LocationType
from nautobot.extras.models import CustomField


class BasicModel:
    """Simple class used for getting annotation data to the test cases."""

    alt_name: Annotated[str, CustomFieldAnnotation(key="alt_name")]




class TestLoadCustomFieldAttribute(TestCase):

    def setUp(self):
        self.annotations = get_type_hints(BasicModel)
        self.location_type_1 = LocationType(
            name="Location Type 1",
        )
        self.location_type_2 = LocationType(
            name="Location Type 2",
        )
        self.location_type_2._custom_field_data["alt_name"] = "Alt Name 2"

        self.alt_name = CustomFieldAttribute(
            name="alt_name",
            annotation=self.annotations["alt_name"],
            custom_annotation=CustomFieldAnnotation(key="alt_name")
        )

    def test_no_cf_attribute(self):
        interface = CustomFieldAttribute(
            name="alt_name",
            annotation=self.annotations["alt_name"],
            custom_annotation=CustomFieldAnnotation(key="alt_name")
        )
        result = interface.load(self.location_type_1)
        self.assertIsNone(result)

    def test_get_custom_field_string(self):
        result = self.alt_name.load(self.location_type_2)
        self.assertEqual(result, "Alt Name 2")
