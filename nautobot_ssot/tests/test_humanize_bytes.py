"""Tests for the `humanize_bytes` template filter."""

import unittest

from nautobot_ssot.templatetags.humanize_bytes import humanize_bytes


class TestHumanizeBytes(unittest.TestCase):
    """Test that the filter renders byte counts at each appropriate IEC suffix."""

    def test_non_numeric_input_returns_no_data_sentinel(self):
        """Anything that isn't an int/float short-circuits to the literal 'no data' string."""
        self.assertEqual(humanize_bytes("not-a-number"), "no data")

    def test_value_below_one_kibibyte_uses_plain_bytes_suffix(self):
        """Values < 1024 are reported in bytes with no IEC prefix."""
        self.assertEqual(humanize_bytes(512), "512 B")

    def test_exact_power_of_two_omits_decimal_places(self):
        """When the converted value has no meaningful fraction it is rendered without decimals."""
        self.assertEqual(humanize_bytes(1024), "  1 KiB")
        self.assertEqual(humanize_bytes(1024 * 1024), "  1 MiB")

    def test_fractional_value_renders_two_decimal_places(self):
        """A non-integer result after conversion is rendered with two decimal places of precision."""
        self.assertEqual(humanize_bytes(1536), "1.50 KiB")

    def test_value_beyond_yobibyte_falls_through_to_final_branch(self):
        """A value large enough to exceed the loop exits to the final 'Yi' branch with one decimal."""
        huge = 1024**9
        result = humanize_bytes(huge)
        self.assertTrue(result.endswith("YiB"))
