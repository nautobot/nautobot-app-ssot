"""Tests of CloudVision utility methods."""

from django.test import override_settings
from nautobot.core.testing import TestCase
from nautobot.dcim.models import DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Role, Status, Tag

from nautobot_ssot.integrations.aristacv.utils import nautobot


class TestNautobotUtils(TestCase):
    """Test Nautobot utility methods."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Configure shared test vars."""
        self.arista_manu = Manufacturer.objects.get_or_create(name="Arista")[0]

    def test_verify_site_success(self):
        """Test the verify_site method for existing Site."""
        loc_type = LocationType.objects.get_or_create(name="Site")[0]
        test_site, _ = Location.objects.get_or_create(
            name="Test", location_type=loc_type, status=Status.objects.get(name="Active")
        )
        result = nautobot.verify_site(site_name="Test")
        self.assertEqual(result, test_site)

    def test_verify_site_fail(self):
        """Test the verify_site method for non-existing Site."""
        result = nautobot.verify_site(site_name="Test2")
        self.assertEqual(result.name, "Test2")
        self.assertTrue(isinstance(result, Location))

    def test_verify_device_type_object_success(self):
        """Test the verify_device_type_object for existing DeviceType."""
        new_dt, _ = DeviceType.objects.get_or_create(model="DCS-7150S-24", manufacturer=self.arista_manu)
        result = nautobot.verify_device_type_object(device_type="DCS-7150S-24")
        self.assertEqual(result, new_dt)

    def test_verify_device_type_object_fail(self):
        """Test the verify_device_type_object for non-existing DeviceType."""
        result = nautobot.verify_device_type_object(device_type="DCS-7150S-24")
        self.assertEqual(result.model, "DCS-7150S-24")
        self.assertTrue(isinstance(result, DeviceType))

    def test_verify_device_role_object_success(self):
        """Test the verify_device_role_object method for existing DeviceRole."""
        new_dr, _ = Role.objects.get_or_create(name="Edge Router")
        result = nautobot.verify_device_role_object(role_name="Edge Router", role_color="ff0000")
        self.assertEqual(result, new_dr)

    def test_verify_device_role_object_fail(self):
        """Test the verify_device_role_object method for non-existing Role."""
        result = nautobot.verify_device_role_object(role_name="Distro Switch", role_color="ff0000")
        self.assertEqual(result.name, "Distro Switch")
        self.assertEqual(result.color, "ff0000")

    def test_verify_import_tag_success(self):
        """Test the verify_import_tag method for existing Tag."""
        new_tag, _ = Tag.objects.get_or_create(name="cloudvision_imported")
        result = nautobot.verify_import_tag()
        self.assertEqual(result, new_tag)

    def test_verify_import_tag_fail(self):
        """Test the verify_import_tag method for non-existing Tag."""
        result = nautobot.verify_import_tag()
        self.assertEqual(result.name, "cloudvision_imported")

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_hostname_patterns": [r"(?P<site>\w{2,3}\d+)-(?P<role>\w+)-\d+"],
                "aristacv_site_mappings": {"ams01": "Amsterdam"},
                "aristacv_role_mappings": {"leaf": "leaf"},
            },
        },
    )
    def test_parse_hostname(self):
        """Test the parse_hostname method."""
        config = nautobot.get_config()
        host = "ams01-leaf-01"
        results = nautobot.parse_hostname(host, config.hostname_patterns)
        expected = ("ams01", "leaf")
        self.assertEqual(results, expected)

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_hostname_patterns": [r"(?P<site>\w{2,3}\d+)-.+-\d+"],
                "aristacv_site_mappings": {"ams01": "Amsterdam"},
                "aristacv_role_mappings": {},
            },
        },
    )
    def test_parse_hostname_only_site(self):
        """Test the parse_hostname method with only site specified."""
        config = nautobot.get_config()
        host = "ams01-leaf-01"
        results = nautobot.parse_hostname(host, config.hostname_patterns)
        expected = ("ams01", None)
        self.assertEqual(results, expected)

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_hostname_patterns": [r".+-(?P<role>\w+)-\d+"],
                "aristacv_site_mappings": {},
                "aristacv_role_mappings": {"leaf": "leaf"},
            },
        },
    )
    def test_parse_hostname_only_role(self):
        """Test the parse_hostname method with only role specified."""
        config = nautobot.get_config()
        host = "ams01-leaf-01"
        results = nautobot.parse_hostname(host, config.hostname_patterns)
        expected = (None, "leaf")
        self.assertEqual(results, expected)
