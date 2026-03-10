"""Unit tests validating zoneinfo usage in the Bootstrap integration.

These tests verify that the migration from pytz to the stdlib zoneinfo
module works correctly for timezone handling in Bootstrap models.
"""

from unittest import TestCase
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .test_bootstrap_setup import is_valid_timezone


class TestIsValidTimezone(TestCase):
    """Test the is_valid_timezone helper function."""

    def test_valid_timezone_us_eastern(self):
        """Test that US/Eastern is recognized as a valid timezone."""
        self.assertTrue(is_valid_timezone("US/Eastern"))

    def test_valid_timezone_utc(self):
        """Test that UTC is recognized as a valid timezone."""
        self.assertTrue(is_valid_timezone("UTC"))

    def test_valid_timezone_america_new_york(self):
        """Test that America/New_York is recognized as a valid timezone."""
        self.assertTrue(is_valid_timezone("America/New_York"))

    def test_valid_timezone_asia_tokyo(self):
        """Test that Asia/Tokyo is recognized as a valid timezone."""
        self.assertTrue(is_valid_timezone("Asia/Tokyo"))

    def test_invalid_timezone_returns_false(self):
        """Test that an invalid timezone string returns False."""
        self.assertFalse(is_valid_timezone("Invalid/Timezone"))

    def test_empty_string_timezone(self):
        """Test that an empty string is handled as an invalid timezone."""
        self.assertFalse(is_valid_timezone(""))

    def test_none_timezone(self):
        """Test that None is handled as an invalid timezone."""
        self.assertFalse(is_valid_timezone(None))


class TestZoneInfoBehavior(TestCase):
    """Test ZoneInfo behavior matches the patterns used in Bootstrap models.

    The Bootstrap integration creates ZoneInfo objects from timezone strings
    stored in YAML configuration. These tests verify the expected behavior
    of ZoneInfo for the patterns used in the codebase.
    """

    def test_zoneinfo_valid_timezone(self):
        """Test ZoneInfo creation with a valid timezone string."""
        tz = ZoneInfo("US/Eastern")
        self.assertIsNotNone(tz)
        self.assertEqual(str(tz), "US/Eastern")

    def test_zoneinfo_utc(self):
        """Test ZoneInfo creation with UTC."""
        tz = ZoneInfo("UTC")
        self.assertIsNotNone(tz)
        self.assertEqual(str(tz), "UTC")

    def test_zoneinfo_invalid_raises_not_found(self):
        """Test that ZoneInfo raises appropriate errors for invalid timezone strings."""
        with self.assertRaises(ZoneInfoNotFoundError):
            ZoneInfo("Not/A/Real/Timezone")

    def test_zoneinfo_empty_string_raises_error(self):
        """Test that ZoneInfo raises an error for an empty string.

        The Bootstrap model code guards against empty strings before calling
        ZoneInfo, but this test documents the expected behavior if the guard
        were bypassed. Note: ZoneInfo("") raises ValueError (not
        ZoneInfoNotFoundError) because empty string is not a valid key format.
        """
        with self.assertRaises((ZoneInfoNotFoundError, ValueError)):
            ZoneInfo("")

    def test_zoneinfo_guard_pattern(self):
        """Test the guard pattern used in Bootstrap NautobotLocation create/update.

        The codebase uses this pattern:
            if attrs["time_zone"] and attrs["time_zone"] != "":
                _timezone = ZoneInfo(attrs["time_zone"])

        This test verifies the guard correctly prevents ZoneInfo calls
        for empty/falsy values.
        """
        test_cases = [
            {"time_zone": "US/Eastern", "should_create": True},
            {"time_zone": "America/Chicago", "should_create": True},
            {"time_zone": "", "should_create": False},
            {"time_zone": None, "should_create": False},
        ]

        for case in test_cases:
            tz_value = case["time_zone"]
            _timezone = None
            if tz_value and tz_value != "":
                _timezone = ZoneInfo(tz_value)

            if case["should_create"]:
                self.assertIsNotNone(_timezone, f"Expected ZoneInfo for '{tz_value}' but got None")
                self.assertEqual(str(_timezone), tz_value)
            else:
                self.assertIsNone(_timezone, f"Expected None for '{tz_value!r}' but got {_timezone}")

    def test_exception_handling_pattern(self):
        """Test the exception handling pattern used in Bootstrap models.

        The codebase catches (ZoneInfoNotFoundError, ValueError) to handle
        invalid timezone strings. ZoneInfoNotFoundError is a subclass of
        KeyError, so explicitly catching KeyError is unnecessary and could
        mask unrelated dict-access errors.
        """
        invalid_timezones = ["Invalid/Timezone", "Fake", "123"]
        for tz_name in invalid_timezones:
            caught = False
            try:
                ZoneInfo(tz_name)
            except (ZoneInfoNotFoundError, ValueError):
                caught = True
            self.assertTrue(caught, f"Expected exception for invalid timezone '{tz_name}'")
