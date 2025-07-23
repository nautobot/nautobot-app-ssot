from nautobot.core.testing import TestCase
#from unittest import TestCase
from nautobot.dcim.models import Device
from typing_extensions import get_type_hints, TypedDict, List
from nautobot_ssot.contrib.dataclasses.attributes import ManyRelationshipAttribute
from nautobot.dcim.models import LocationType
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device, Module


class ContentTypeDict(TypedDict):
    """"""

    app_label: str
    model: str


class BasicModel:
    """Simple class used for getting annotation data to the test cases."""

    name: str
    content_types: List[ContentTypeDict]


class TestLoadCustomFieldAttribute(TestCase):

    def setUp(self):
        self.annotations = get_type_hints(BasicModel)
        self.location_type_1 = LocationType(
            name="Location Type 1",
        )
        self.location_type_1.validated_save()
        self.location_type_1.content_types.add(ContentType.objects.get_for_model(Device))

        self.location_type_2 = LocationType(
            name="Location Type 2",
        )
        self.location_type_2.validated_save()

        self.content_types = ManyRelationshipAttribute(
            name="content_types",
            annotation=self.annotations["content_types"]
        )

    def test_invalid_attribute_type(self):
        with self.assertRaises(AttributeError):
            ManyRelationshipAttribute(
                name="name",
                annotation=self.annotations["name"],
            )

    def test_get_empty(self):
        result = self.content_types.load(self.location_type_2)
        self.assertEqual(len(result), 0)

    def test_get_single_count(self):
        result = self.content_types.load(self.location_type_1)
        self.assertEqual(len(result), 1)

    def test_get_multiple_count(self):
        self.location_type_1.content_types.add(ContentType.objects.get_for_model(Module))
        result = self.content_types.load(self.location_type_1)
        self.assertEqual(len(result), 2)
