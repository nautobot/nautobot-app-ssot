"""Tests for contrib.NautobotAdapter."""

from typing import Annotated, List, Optional
from unittest import skip
from unittest.mock import MagicMock

from diffsync import ObjectNotFound
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nautobot.apps.choices import RelationshipTypeChoices
from nautobot.apps.testing import TestCase
from nautobot.circuits import models as circuits_models
from nautobot.dcim import models as dcim_models
from nautobot.extras import models as extras_models
from nautobot.ipam import models as ipam_models
from nautobot.tenancy import models as tenancy_models
from typing_extensions import TypedDict

from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotAdapter, NautobotModel

from nautobot_ssot.contrib.adapter import NautobotAdapter
from nautobot.dcim.models import LocationType, Location
from unittest.mock import MagicMock

from nautobot.extras.models import Status

# STATUS_ACTIVE = Status.objects.get(name="Active")

from typing import Optional, TypedDict


class LocationTypedDict(TypedDict):
    """"""

    name: str


class NautobotLocationType(NautobotModel):
    """"""

    _model = LocationType
    _modelname = "location_type"

    _identifiers = ("name", "locations", "ranking",)

    name: str
    locations: list[LocationTypedDict] = []
    ranking: Annotated[str, CustomFieldAnnotation("ranking")]

class NautobotLocation(NautobotModel):

    _model = Location
    _modelname = "location"

    _identifiers = ("name", "parent__name",)
    _attributes = (
       "location_type__name",
    )

    name: str
    parent__name: Optional[str] = None

    location_type__name: str

class SourceNautobotAdapter(NautobotAdapter):
    top_level = [
        "location_type", 
        "location",
    ]

    location_type = NautobotLocationType
    location = NautobotLocation

class TestNautobotAdapterLoadSingleObject(TestCase):
    """"""

    def setUp(self):
        status_active = Status.objects.get(name="Active")
        self.adapter = SourceNautobotAdapter(job=MagicMock())
        self.location_type_1 = LocationType(name="Test Location Type")
        self.location_type_1.validated_save()

        self.location_1 = Location(name="Test1", location_type=self.location_type_1, status=status_active, description="",)
        self.location_1.validated_save()
        self.location_2 = Location(name="Test2", location_type=self.location_type_1, status=status_active, description="",)
        self.location_2.validated_save()

    def test_get_standard_attribute(self):
        result = self.adapter.load_single_object(NautobotLocationType, LocationType(name="test"))
        self.assertEqual(result.name, "test")

    def test_get_foreign_key(self):
        result = self.adapter.load_single_object(NautobotLocation, Location(
            name="Location1",
            location_type=self.location_type_1,
        ))
        self.assertEqual(result.location_type__name, self.location_type_1.name)

    def test_get_n_to_many(self):
        result = self.adapter.load_single_object(
            NautobotLocationType,
            self.location_type_1,
        )
        self.assertEqual(len(result.locations), 2)

    def test_get_custom_field(self):
        """"""

    def test_get_custom_foreign_key(self):
        """"""

    def test_get_custom_n_to_many(self):
        """"""
