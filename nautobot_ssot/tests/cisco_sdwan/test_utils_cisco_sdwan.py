"""Tests for Cisco SD-WAN utility functions."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from nautobot_ssot.integrations.cisco_sdwan.utils.cisco_sdwan import (
    CiscoSdwanManager,
    normalize_device_model,
    normalize_software_version,
)
from nautobot_ssot.tests.cisco_sdwan.fixtures import CONTROLLERS_FIXTURE, VEDGES_FIXTURE


class TestNormalizeDeviceModel(TestCase):
    """Test the normalize_device_model function."""

    def test_normalize_with_prefix_pattern(self):
        """Validate removal of a prefix pattern."""
        self.assertEqual(normalize_device_model("vedge-C8000V", pattern="^vedge-"), "C8000V")

    def test_normalize_without_pattern(self):
        """Validate the model is returned unchanged without a pattern."""
        self.assertEqual(normalize_device_model("vedge-C8000V"), "vedge-C8000V")
        self.assertEqual(normalize_device_model("vedge-C8000V", pattern=None), "vedge-C8000V")

    def test_normalize_no_match(self):
        """Validate the model is returned unchanged when the pattern does not match."""
        self.assertEqual(normalize_device_model("vmanage", pattern="^vedge-"), "vmanage")

    def test_normalize_strips_whitespace(self):
        """Validate whitespace is stripped after pattern removal."""
        self.assertEqual(normalize_device_model("Cisco C8300", pattern="Cisco"), "C8300")


class TestNormalizeSoftwareVersion(TestCase):
    """Test the normalize_software_version function."""

    def test_strip_build_numbers(self):
        """Validate internal build numbers are stripped."""
        self.assertEqual(normalize_software_version("17.06.03a.0.6476"), "17.06.03a")

    def test_zero_padding(self):
        """Validate minor and patch numbers are zero-padded."""
        self.assertEqual(normalize_software_version("17.9.4"), "17.09.04")
        self.assertEqual(normalize_software_version("20.6.3"), "20.06.03")

    def test_empty_version(self):
        """Validate None is returned for empty input."""
        self.assertIsNone(normalize_software_version(""))
        self.assertIsNone(normalize_software_version(None))

    def test_unparsable_version(self):
        """Validate unparsable versions are returned stripped."""
        self.assertEqual(normalize_software_version(" custom-build "), "custom-build")


class TestCiscoSdwanManager(TestCase):
    """Test the CiscoSdwanManager API wrapper."""

    def setUp(self):
        """Initialize a manager with a mocked job."""
        self.job = MagicMock()
        self.job.debug = False
        self.manager = CiscoSdwanManager(
            job=self.job,
            base_url="https://vmanage.example.com",
            username="user",
            password="pass",  # noqa: S106
            verify=True,
        )

    def _mock_send_request(self, method, endpoint, api=None, payload=None):  # pylint: disable=unused-argument
        """Return device fixtures based on the requested endpoint."""
        if endpoint == "/system/device/vedges":
            return {"data": list(VEDGES_FIXTURE["data"])}
        if endpoint == "/system/device/controllers":
            return {"data": list(CONTROLLERS_FIXTURE["data"])}
        return {"data": []}

    def test_get_devices_merges_and_filters_unnamed(self):
        """Validate WAN Edges and controllers are merged and unnamed devices are dropped."""
        with patch.object(self.manager, "send_request", side_effect=self._mock_send_request):
            devices = self.manager.get_devices()
        self.assertEqual(
            {device["host-name"] for device in devices},
            {"sdwan-edge-01", "sdwan-edge-02", "vmanage-01"},
        )

    def test_get_devices_with_device_filter(self):
        """Validate the device filter limits results by hostname."""
        nb_device = MagicMock()
        nb_device.name = "sdwan-edge-01"
        with patch.object(self.manager, "send_request", side_effect=self._mock_send_request):
            devices = self.manager.get_devices(device_filter=[nb_device])
        self.assertEqual([device["host-name"] for device in devices], ["sdwan-edge-01"])

    def test_send_request_invalid_method(self):
        """Validate unsupported HTTP methods raise a ValueError."""
        with self.assertRaises(ValueError):
            self.manager.send_request(method="patch", endpoint="/device")
