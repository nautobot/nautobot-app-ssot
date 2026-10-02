"""Tests for the `humanize_bytes` template filter."""

import unittest

from nautobot_ssot.templatetags.humanize_bytes import humanize_bytes


class TestHumanizeBytes(unittest.TestCase):
    """Test the humanize_bytes template filter."""

    def test_non_numeric_returns_no_data(self):
        """Non-numeric input returns the `no data` placeholder."""
        self.assertEqual(humanize_bytes(None), "no data")
        self.assertEqual(humanize_bytes("not a number"), "no data")

    def test_whole_number_bytes(self):
        """A small whole number of bytes renders without decimals."""
        self.assertEqual(humanize_bytes(1).strip(), "1 B")

    def test_whole_kibibytes(self):
        """Exactly one KiB renders without decimals and the KiB unit."""
        self.assertEqual(humanize_bytes(1024).strip(), "1 KiB")

    def test_fractional_kibibytes(self):
        """A fractional size keeps two decimal places."""
        self.assertEqual(humanize_bytes(1536).strip(), "1.50 KiB")

    def test_overflow_uses_yobibytes(self):
        """A size larger than the defined units falls through to the YiB suffix."""
        self.assertEqual(humanize_bytes(1024**9).strip(), "1024.0 YiB")
