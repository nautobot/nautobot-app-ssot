"""Tests for the custom SSoT exception classes."""

import unittest

from nautobot_ssot.exceptions import (
    AdapterLoadException,
    AuthFailure,
    ConfigurationError,
    InvalidUrlScheme,
    JobException,
    MissingConfigSetting,
    MissingSecretsGroupException,
    RequestConnectError,
    RequestHTTPError,
)


class TestSSoTExceptions(unittest.TestCase):
    """Test the custom exception classes used across SSoT integrations."""

    def test_auth_failure_stores_code_and_message(self):
        """AuthFailure exposes the error code as `expression` and the message as `message`."""
        error = AuthFailure(error_code="401", message="Unauthorized")
        self.assertEqual(error.expression, "401")
        self.assertEqual(error.message, "Unauthorized")
        self.assertEqual(str(error), "Unauthorized")

    def test_job_exception_stores_message(self):
        """JobException stores and renders its message."""
        error = JobException(message="Job failed to load")
        self.assertEqual(error.message, "Job failed to load")
        self.assertEqual(str(error), "Job failed to load")

    def test_invalid_url_scheme_builds_message(self):
        """InvalidUrlScheme builds a human-readable message from the offending scheme."""
        error = InvalidUrlScheme(scheme="ftp")
        self.assertEqual(error.message, "Invalid URL scheme 'ftp' found!")
        self.assertEqual(str(error), "Invalid URL scheme 'ftp' found!")

    def test_missing_config_setting_builds_message(self):
        """MissingConfigSetting stores the setting and builds a message."""
        error = MissingConfigSetting(setting="api_token")
        self.assertEqual(error.setting, "api_token")
        self.assertEqual(error.message, "Missing configuration setting - api_token!")
        self.assertEqual(str(error), "Missing configuration setting - api_token!")

    def test_plain_exceptions_are_raisable(self):
        """The marker exception classes carry no extra state and can be raised/caught."""
        for exc_class in (
            AdapterLoadException,
            ConfigurationError,
            MissingSecretsGroupException,
            RequestConnectError,
            RequestHTTPError,
        ):
            with self.assertRaises(exc_class):
                raise exc_class("boom")
