"""Unit tests for Meraki utility functions."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import meraki

from nautobot_ssot.integrations.meraki.utils.meraki import DashboardClient
from nautobot_ssot.tests.meraki.fixtures import fixtures as fix


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
