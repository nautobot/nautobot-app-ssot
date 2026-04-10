"""Unit tests for the pysnow module."""

import warnings
from unittest.mock import MagicMock, mock_open, patch

from nautobot.core.testing import TestCase

from nautobot_ssot.integrations.servicenow.third_party.pysnow.attachment import Attachment


class TestAttachmentUploadContentType(TestCase):
    """Test that the upload method sets Content-Type based on HAS_MAGIC."""

    def setUp(self):
        """Set up a minimal Attachment instance with a mocked resource."""
        self.resource = MagicMock()
        self.attachment = Attachment(resource=self.resource, table_name="incident")

    @patch("nautobot_ssot.integrations.servicenow.third_party.pysnow.attachment.HAS_MAGIC", True)
    @patch("nautobot_ssot.integrations.servicenow.third_party.pysnow.attachment.magic", create=True)
    @patch("builtins.open", mock_open(read_data=b"file content"))
    def test_upload_uses_magic_when_available(self, mock_magic):
        """When python-magic is available, Content-Type should be determined by magic."""
        file_path = "/tmp/test.pdf"
        mock_magic.from_file.return_value = "application/pdf"

        self.attachment.upload(sys_id="abc123", file_path=file_path)

        mock_magic.from_file.assert_called_once_with(file_path, mime=True)
        call_kwargs = self.resource.request.call_args[1]
        self.assertEqual(call_kwargs["headers"]["Content-Type"], "application/pdf")

    @patch("nautobot_ssot.integrations.servicenow.third_party.pysnow.attachment.HAS_MAGIC", False)
    @patch("builtins.open", mock_open(read_data=b"file content"))
    def test_upload_falls_back_to_text_plain_without_magic(self):
        """When python-magic is missing, Content-Type should fall back to text/plain with a warning."""
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            self.attachment.upload(sys_id="abc123", file_path="/tmp/test.txt")

        self.assertEqual(len(caught_warnings), 1)
        self.assertIn("python-magic", str(caught_warnings[0].message))

        call_kwargs = self.resource.request.call_args[1]
        self.assertEqual(call_kwargs["headers"]["Content-Type"], "text/plain")
