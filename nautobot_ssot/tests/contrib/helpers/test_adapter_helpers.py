"""Tests for contrib.NautobotAdapter."""


from nautobot.core.testing import TestCase
from nautobot.dcim.models import (
    Location,
    LocationType,
)
from nautobot.extras.models import Status

from nautobot_ssot.contrib.helpers.adapter import (
    get_foreign_key_value,
)


class TestGetForeignKeyValue(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.status = Status.objects.get(name="Active")

        cls.location_type_name = "Test Parent Location Type"
        cls.location_type = LocationType.objects.create(
            name=cls.location_type_name,
            description="Test Location Type",
        )
        cls.location_1_name = "Location 1"
        cls.location_1 = Location.objects.create(
            name=cls.location_1_name,
            parent=None,
            location_type=cls.location_type,
            status=cls.status,
        )

        cls.location_type_2 = LocationType.objects.create(
            name="Location Type 2",
            parent=cls.location_type,
        )
        cls.location_2_name = "Location 2"
        cls.location_2 = Location.objects.create(
            name=cls.location_2_name,
            parent=cls.location_1,
            location_type=cls.location_type_2,
            status=cls.status,
        )

    def test_get_related_object(self):
        """Test getting single-level, related object."""
        response = get_foreign_key_value(
            self.location_1,
            "location_type__name",
        )
        self.assertEqual(response, self.location_type_name)

    def test_multi_level_lookup(self):
        """Test getting multi-level object."""
        response = get_foreign_key_value(
            self.location_2,
            "parent__location_type__name",
        )
        self.assertEqual(response, self.location_type_name)

    def test_invalid_parameter_name(self):
        """Test attempt to use invalid parameter name."""
        with self.assertRaises(ValueError):
            get_foreign_key_value(self.location_1, "invalid_name")
