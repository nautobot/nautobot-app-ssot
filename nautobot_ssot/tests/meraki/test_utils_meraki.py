"""Unit tests for Meraki utility functions."""

import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

import meraki

from nautobot_ssot.integrations.meraki.utils.meraki import (
    MERAKI_API_CALLER,
    DashboardClient,
    SessionInputError,
    format_sdk_error,
)
from nautobot_ssot.tests.meraki.fixtures import fixtures as fix


class FakeJob:
    """Stand-in for a Nautobot Job passed as the DashboardClient logger.

    Nautobot's Job exposes `logger` and has no `log` attribute, so a MagicMock cannot catch code
    that reaches for the wrong one.
    """

    def __init__(self):
        self.logger = MagicMock()


class TestDashboardClient(TestCase):
    """Unit tests for the DashboardClient class."""

    @patch("meraki.DashboardAPI")
    def test_successful_connection(self, mock_api):
        """Test successful connection to Meraki dashboard with valid API key and base URL."""
        logger = MagicMock()
        org_id = "12345"
        token = "valid_token"  # noqa: S105
        dashboard_client = DashboardClient(logger, org_id, token)

        mock_api.assert_called_once_with(
            api_key=token,
            base_url="https://api.meraki.com/api/v1/",
            output_log=False,
            print_console=False,
            maximum_retries=100,
            wait_on_rate_limit=True,
            caller=MERAKI_API_CALLER,
        )

        self.assertIsNotNone(dashboard_client.conn)
        self.assertEqual(dashboard_client.logger, logger)
        self.assertEqual(dashboard_client.org_id, org_id)
        self.assertEqual(dashboard_client.token, token)

    @patch("meraki.DashboardAPI")
    def test_invalid_api_key(self, mock_api):
        """Test that an Raises an exception of type 'meraki.APIError' if API key is invalid or missing."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.reason = "Invalid API key"
        mock_api.side_effect = meraki.APIError(
            metadata={"operation": "GET", "tags": ["Failed"]}, response=mock_response
        )

        logger = MagicMock()
        org_id = "12345"
        token = "invalid_token"  # noqa: S105

        with self.assertRaises(meraki.APIError):
            DashboardClient(logger, org_id, token)

    @patch("meraki.DashboardAPI")
    def test_connection_failure_logs_through_job_logger(self, mock_api):
        """Test a failed connection is logged via Job.logger rather than the non-existent Job.log."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.reason = "Invalid API key"
        mock_api.side_effect = meraki.APIError(
            metadata={"operation": "GET", "tags": ["Failed"]}, response=mock_response
        )
        job = FakeJob()

        with self.assertRaises(meraki.APIError):
            DashboardClient(job, "12345", "invalid_token")  # noqa: S106

        job.logger.error.assert_called_once()
        self.assertIn("Unable to connect to Meraki dashboard", job.logger.error.call_args[0][0])

    def test_caller_accepted_by_sdk_user_agent_validation(self):
        """Test the configured caller passes the user agent validation added in meraki 2.0."""
        client = DashboardClient(MagicMock(), "12345", "your_api_token")  # noqa: S106

        self.assertIsNotNone(client.conn)

    @patch.dict(os.environ, {"BE_GEO_ID": "some_partner_id"})
    def test_connection_succeeds_with_be_geo_id_set(self):
        """Test client construction succeeds when the deprecated BE_GEO_ID env var is set.

        meraki >= 2.0 validates be_geo_id and raises SessionInputError from DashboardAPI() unless a
        valid caller takes precedence. SessionInputError is not an APIError, so without the caller
        this escapes connect_dashboard() as an unhandled traceback on job start.
        """
        client = DashboardClient(MagicMock(), "12345", "your_api_token")  # noqa: S106

        self.assertIsNotNone(client.conn)

    def test_session_input_error_is_handled(self):
        """Test a SessionInputError from the SDK is logged and does not escape the client."""
        job = FakeJob()
        client = DashboardClient(job, "123456789", "your_api_token")  # noqa: S106
        client.conn.organizations.getOrganizationNetworks = MagicMock(
            side_effect=SessionInputError(
                "total_pages", "bogus", "total_pages must be either an integer or 'all'", "https://example.test"
            )
        )

        self.assertEqual(client.get_org_networks(), [])
        job.logger.warning.assert_called_once()

    def test_validate_organization_exists_success_response(self):
        """Test the validate_organization_exists() response is true if org ID found."""
        logger = MagicMock()
        org_id = "123456789"
        token = "your_api_token"  # noqa: S105
        dashboard_client = DashboardClient(logger, org_id, token)
        dashboard_client.conn.organizations.getOrganizations = MagicMock()
        dashboard_client.conn.organizations.getOrganizations.return_value = [{"id": "123456789"}, {"id": "987654321"}]

        organization_exists = dashboard_client.validate_organization_exists()

        self.assertTrue(organization_exists)

    def test_validate_organization_exists_failure_response(self):
        """Test the validate_organization_exists() response is false if wrong org ID."""
        logger = MagicMock()
        org_id = "123456789"
        token = "your_api_token"  # noqa: S105
        dashboard_client = DashboardClient(logger, org_id, token)
        dashboard_client.conn.organizations.getOrganizations = MagicMock()
        dashboard_client.conn.organizations.getOrganizations.return_value = [{"id": "987654321"}]

        organization_exists = dashboard_client.validate_organization_exists()

        self.assertFalse(organization_exists)

    def test_get_org_networks(self):
        """Test the get_org_networks() response is as expected."""
        logger = MagicMock()
        org_id = "123456789"
        token = "your_api_token"  # noqa: S105
        client = DashboardClient(logger, org_id, token)
        client.conn.organizations.getOrganizationNetworks = MagicMock()
        client.conn.organizations.getOrganizationNetworks.return_value = fix.GET_ORG_NETWORKS_SENT_FIXTURE

        actual = client.get_org_networks()
        expected = fix.GET_ORG_NETWORKS_SENT_FIXTURE
        self.assertEqual(actual, expected)
        self.assertEqual(client.network_map, fix.GET_ORG_NETWORKS_RECV_FIXTURE)

    def test_get_org_devices(self):
        """Test the get_org_devices() response is as expected."""
        logger = MagicMock()
        org_id = "123456789"
        token = "your_api_token"  # noqa: S105
        client = DashboardClient(logger, org_id, token)
        client.conn.organizations.getOrganizationDevices = MagicMock()
        client.conn.organizations.getOrganizationDevices.return_value = fix.GET_ORG_DEVICES_FIXTURE

        actual = client.get_org_devices()
        expected = fix.GET_ORG_DEVICES_FIXTURE
        self.assertEqual(actual, expected)

    def test_get_org_switchports(self):
        """Test the get_org_switchports() response is as expected."""
        logger = MagicMock()
        org_id = "123456789"
        token = "your_api_token"  # noqa: S105
        client = DashboardClient(logger, org_id, token)
        client.conn.switch.getOrganizationSwitchPortsBySwitch = MagicMock()
        client.conn.switch.getOrganizationSwitchPortsBySwitch.return_value = fix.GET_ORG_SWITCHPORTS_SENT_FIXTURE

        actual = client.get_org_switchports()
        expected = fix.GET_ORG_SWITCHPORTS_RECV_FIXTURE
        self.assertEqual(actual, expected)

    def test_get_org_device_statuses(self):
        """Test the get_org_device_statuses() response is as expected."""
        logger = MagicMock()
        org_id = "123456789"
        token = "your_api_token"  # noqa: S105
        client = DashboardClient(logger, org_id, token)
        client.conn.organizations.getOrganizationDevicesStatuses = MagicMock()
        client.conn.organizations.getOrganizationDevicesStatuses.return_value = fix.GET_ORG_DEVICE_STATUSES_SENT_FIXTURE

        actual = client.get_org_device_statuses()
        expected = fix.GET_ORG_DEVICE_STATUSES_RECV_FIXTURE
        self.assertEqual(actual, expected)

    def test_get_uplink_settings_pppoe(self):
        """Test the get_uplink_settings() response is as expected."""
        logger = MagicMock()
        org_id = "123456789"
        token = "your_api_token"  # noqa: S105
        client = DashboardClient(logger, org_id, token)
        client.conn.appliance.getDeviceApplianceUplinksSettings = MagicMock()
        client.conn.appliance.getDeviceApplianceUplinksSettings.return_value = (
            fix.GET_UPLINK_SETTINGS_PPPOE_SENT_FIXTURE
        )
        actual = client.get_uplink_settings(serial="V4GD-ABDP-YVCK")
        expected = fix.GET_UPLINK_SETTINGS_PPPOE_RECV_FIXTURE
        self.assertEqual(actual, expected)


class TestFormatSdkError(TestCase):
    """Unit tests for the format_sdk_error helper."""

    def test_api_error_includes_status_reason_and_message(self):
        """Test an APIError is reported with all of its detail attributes."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_response.json.return_value = {"errors": ["No such organization"]}
        err = meraki.APIError(metadata={"operation": "GET", "tags": ["Failed"]}, response=mock_response)

        actual = format_sdk_error(err)

        self.assertIn("status code = 404", actual)
        self.assertIn("reason = Not Found", actual)
        self.assertIn("No such organization", actual)

    def test_session_input_error_omits_missing_attributes(self):
        """Test a SessionInputError is reported without raising on the attributes it lacks."""
        err = SessionInputError("total_pages", "bogus", "total_pages must be an integer", "https://example.test")

        actual = format_sdk_error(err)

        self.assertIn("total_pages must be an integer", actual)
        self.assertNotIn("status code", actual)
        self.assertNotIn("reason =", actual)
