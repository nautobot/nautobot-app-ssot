# pylint: disable=W0212,R0904
"""Test Forward Enterprise API client functionality."""

from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from nautobot_ssot.integrations.forward_enterprise.exceptions import (
    ForwardEnterpriseAPIError,
    ForwardEnterpriseAuthenticationError,
    ForwardEnterpriseConnectionError,
    ForwardEnterpriseQueryError,
    ForwardEnterpriseValidationError,
)
from nautobot_ssot.integrations.forward_enterprise.utils.forward_enterprise_client import ForwardEnterpriseClient

from .fixtures import MOCK_NQE_DEVICE_QUERY_RESULT, DummyJob
from .mocks import MockForwardEnterpriseClient


class TestForwardEnterpriseClient(TestCase):
    """Test Forward Enterprise API client."""

    def setUp(self):
        """Set up test client."""
        self.api_url = "https://test.example.com"
        self.api_token = "test_token"
        self.job = DummyJob()
        self.job.credentials.remote_url = self.api_url
        self.job.credentials.verify_ssl = True
        self.job.credentials.secrets_group = Mock()
        self.job.credentials.secrets_group.get_secret_value.return_value = self.api_token

    def test_client_initialization(self):
        """Test client initialization."""
        client = ForwardEnterpriseClient(job=self.job)
        self.assertEqual(client.api_url, self.api_url)
        self.assertEqual(client.api_token, self.api_token)
        self.assertTrue(client.verify_ssl)

    def test_client_strips_trailing_slash(self):
        """Test that client strips trailing slashes from URL."""
        # Create a special job with trailing slash in URL
        job_with_slash = Mock()
        job_with_slash.credentials = Mock()
        job_with_slash.credentials.remote_url = self.api_url + "/"
        job_with_slash.credentials.verify_ssl = True
        job_with_slash.credentials.secrets_group = Mock()
        job_with_slash.credentials.secrets_group.get_secret_value.return_value = self.api_token

        client = ForwardEnterpriseClient(job=job_with_slash)
        self.assertEqual(client.api_url, self.api_url)

    def test_is_query_id_detection(self):
        """Test query ID detection."""
        client = ForwardEnterpriseClient(
            job=self.job,
        )

        # Valid query IDs
        self.assertTrue(client._is_query_id("Q_devices_basic"))
        self.assertTrue(client._is_query_id("Q_interfaces_all"))
        self.assertTrue(client._is_query_id("Q_123_test"))

        # Invalid query IDs
        self.assertFalse(client._is_query_id("devices | select hostname"))
        self.assertFalse(client._is_query_id("q_lowercase"))
        self.assertFalse(client._is_query_id("Q_"))
        self.assertFalse(client._is_query_id(""))
        # Test with empty string instead of None to avoid type error

    def test_validate_query_parameters_success(self):
        """Test successful query parameter validation."""
        client = ForwardEnterpriseClient(
            job=self.job,
        )

        # Should not raise for valid combinations
        client.validate_query_parameters(query="devices | select hostname")
        client.validate_query_parameters(query_id="Q_devices_basic")

    def test_validate_query_parameters_failure(self):
        """Test query parameter validation failures."""
        client = ForwardEnterpriseClient(
            job=self.job,
        )

        # Should raise for no parameters
        with self.assertRaises(ForwardEnterpriseValidationError):
            client.validate_query_parameters()

        # Should raise for both parameters
        with self.assertRaises(ForwardEnterpriseValidationError):
            client.validate_query_parameters(query="test", query_id="Q_test")

    def test_clean_query(self):
        """Test query cleaning functionality."""
        client = ForwardEnterpriseClient(
            job=self.job,
        )

        # Test comment removal
        query_with_comments = """
        devices // Get all devices
        | select hostname, ip // Select specific fields
        """
        cleaned = client._clean_query(query_with_comments)
        self.assertNotIn("//", cleaned)
        self.assertIn("devices", cleaned)
        self.assertIn("select hostname, ip", cleaned)

        # Test whitespace normalization
        query_with_whitespace = "devices   |   select   hostname"
        cleaned = client._clean_query(query_with_whitespace)
        self.assertEqual(cleaned, "devices | select hostname")

    def test_mock_client_functionality(self):
        """Test the mock client provides expected functionality."""
        mock_client = MockForwardEnterpriseClient(
            base_url="https://test.example.com", username="test_user", password="test_token", verify_ssl=True
        )

        # Test that mock client has expected methods
        self.assertTrue(hasattr(mock_client, "get_device_query_from_config"))
        self.assertTrue(hasattr(mock_client, "get_interface_query_from_config"))
        self.assertTrue(hasattr(mock_client, "get_ipam_query_from_config"))
        self.assertTrue(hasattr(mock_client, "execute_nqe_query"))

        # Test that execute_nqe_query returns appropriate mock data
        device_result = mock_client.execute_nqe_query(query="devices | select hostname, ip")
        self.assertGreater(len(device_result), 0)
        self.assertIn("name", device_result[0])

        interface_result = mock_client.execute_nqe_query(query="interfaces | select device, name")
        self.assertGreater(len(interface_result), 0)
        self.assertIn("device", interface_result[0])

        ipam_result = mock_client.execute_nqe_query(query="ipam | select ip, vrf")
        self.assertGreater(len(ipam_result), 0)
        self.assertIn("ip", ipam_result[0])

    @patch("requests.post")
    def test_execute_nqe_query_success(self, mock_post):
        """Test successful NQE query execution."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_NQE_DEVICE_QUERY_RESULT
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        result = client.execute_nqe_query(query="devices | select hostname")
        self.assertEqual(result, MOCK_NQE_DEVICE_QUERY_RESULT["items"])

    @patch("requests.post")
    def test_execute_nqe_query_with_query_id(self, mock_post):
        """Test NQE query execution with query ID."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"hostname": "test-device"}]
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        result = client.execute_nqe_query(query_id="Q_devices_basic")
        self.assertEqual(result, [{"hostname": "test-device"}])

        # Verify request payload
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertIn("queryId", payload)
        self.assertEqual(payload["queryId"], "Q_devices_basic")

    @patch("requests.post")
    def test_execute_nqe_query_authentication_error(self, mock_post):
        """Test NQE query execution with authentication error."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseAuthenticationError):
            client.execute_nqe_query(query="devices | select hostname")

    @patch("requests.post")
    def test_execute_nqe_query_forbidden_error(self, mock_post):
        """Test NQE query execution with forbidden error."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseAuthenticationError):
            client.execute_nqe_query(query="devices | select hostname")

    @patch("requests.post")
    def test_execute_nqe_query_bad_request(self, mock_post):
        """Test NQE query execution with bad request."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid query syntax"}
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseQueryError) as context:
            client.execute_nqe_query(query="invalid query")

        self.assertIn("Invalid query syntax", str(context.exception))

    @patch("requests.post")
    def test_execute_nqe_query_connection_error(self, mock_post):
        """Test NQE query execution with connection error."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseConnectionError):
            client.execute_nqe_query(query="devices | select hostname")

    @patch("requests.post")
    def test_execute_nqe_query_timeout(self, mock_post):
        """Test NQE query execution with timeout."""
        mock_post.side_effect = requests.exceptions.Timeout("Request timeout")

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseConnectionError):
            client.execute_nqe_query(query="devices | select hostname")

    @patch("requests.post")
    def test_execute_nqe_query_api_error_response(self, mock_post):
        """Test NQE query execution with API error in response."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": {"message": "Query execution failed"}}
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseQueryError) as context:
            client.execute_nqe_query(query="devices | select hostname")

        self.assertIn("Query execution failed", str(context.exception))

    @patch("requests.post")
    def test_execute_nqe_query_invalid_json(self, mock_post):
        """Test NQE query execution with invalid JSON response."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Invalid response"
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseAPIError) as context:
            client.execute_nqe_query(query="devices | select hostname")

        self.assertIn("Invalid JSON response", str(context.exception))

    # Removed test_test_connection_success and test_test_connection_failure
    # as the test_connection method was removed from the client (unused)

    @patch("requests.post")
    def test_execute_nqe_query_with_parameters(self, mock_post):
        """Test NQE query execution with parameters."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"hostname": "test-device"}]
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        parameters = {"site": "Site-A", "vendor": "Cisco"}
        result = client.execute_nqe_query(query="devices | select hostname", parameters=parameters)

        self.assertEqual(result, [{"hostname": "test-device"}])

        # Verify parameters are included in request
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertEqual(payload["parameters"], parameters)

    @patch("requests.post")
    def test_execute_nqe_query_with_network_id(self, mock_post):
        """Test NQE query execution with network ID."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"hostname": "test-device"}]
        mock_post.return_value = mock_response

        client = ForwardEnterpriseClient(
            job=self.job,
        )

        result = client.execute_nqe_query(query="devices | select hostname", network_id="2126")

        self.assertEqual(result, [{"hostname": "test-device"}])

        # Verify network ID is included in query parameters
        call_args = mock_post.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["networkId"], "2126")
