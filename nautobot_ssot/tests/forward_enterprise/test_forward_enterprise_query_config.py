"""Test Forward Enterprise query configuration functionality."""

import unittest
from unittest.mock import Mock

from nautobot_ssot.integrations.forward_enterprise.utils.forward_enterprise_client import ForwardEnterpriseClient


class TestForwardEnterpriseQueryConfig(unittest.TestCase):
    """Test Forward Enterprise query configuration patterns."""

    def setUp(self):
        """Set up test client."""
        self.job = Mock()
        self.job.credentials = Mock()
        self.job.credentials.verify_ssl = True

    def test_pattern_a_raw_queries(self):
        """Test Pattern A: Raw NQE Queries only."""
        self.job.credentials.extra_config = {
            "device_query": "devices | select name, manufacturer",
            "interface_query": "interfaces | select name, device",
            "ipam_query": "ipam | select ip, device",
        }

        client = ForwardEnterpriseClient(job=self.job)

        # Should get queries
        self.assertEqual(client.get_device_query_from_config(), "devices | select name, manufacturer")
        self.assertEqual(client.get_interface_query_from_config(), "interfaces | select name, device")
        self.assertEqual(client.get_ipam_query_from_config(), "ipam | select ip, device")

        # Should not get query IDs
        self.assertIsNone(client.get_device_query_id_from_config())
        self.assertIsNone(client.get_interface_query_id_from_config())
        self.assertIsNone(client.get_ipam_query_id_from_config())

    def test_pattern_b_query_ids(self):
        """Test Pattern B: Query IDs only."""
        self.job.credentials.extra_config = {
            "device_query_id": "Q_device_123",
            "interface_query_id": "Q_interface_456",
            "ipam_query_id": "Q_ipam_789",
        }

        client = ForwardEnterpriseClient(job=self.job)

        # Should get query IDs
        self.assertEqual(client.get_device_query_id_from_config(), "Q_device_123")
        self.assertEqual(client.get_interface_query_id_from_config(), "Q_interface_456")
        self.assertEqual(client.get_ipam_query_id_from_config(), "Q_ipam_789")

        # Should not get queries
        self.assertIsNone(client.get_device_query_from_config())
        self.assertIsNone(client.get_interface_query_from_config())
        self.assertIsNone(client.get_ipam_query_from_config())

    def test_pattern_c_mixed_configuration(self):
        """Test Pattern C: Mixed Configuration."""
        self.job.credentials.extra_config = {
            "device_query": "devices | select name, manufacturer",
            "interface_query_id": "Q_interface_456",
            "ipam_query_id": "Q_ipam_789",
        }

        client = ForwardEnterpriseClient(job=self.job)

        # Device should use query
        self.assertEqual(client.get_device_query_from_config(), "devices | select name, manufacturer")
        self.assertIsNone(client.get_device_query_id_from_config())

        # Interface should use query ID
        self.assertEqual(client.get_interface_query_id_from_config(), "Q_interface_456")
        self.assertIsNone(client.get_interface_query_from_config())

        # IPAM should use query ID
        self.assertEqual(client.get_ipam_query_id_from_config(), "Q_ipam_789")
        self.assertIsNone(client.get_ipam_query_from_config())

    def test_empty_configuration(self):
        """Test behavior with empty configuration."""
        self.job.credentials.extra_config = {}

        client = ForwardEnterpriseClient(job=self.job)

        # All should return None
        self.assertIsNone(client.get_device_query_from_config())
        self.assertIsNone(client.get_interface_query_from_config())
        self.assertIsNone(client.get_ipam_query_from_config())
        self.assertIsNone(client.get_device_query_id_from_config())
        self.assertIsNone(client.get_interface_query_id_from_config())
        self.assertIsNone(client.get_ipam_query_id_from_config())

    def test_missing_credentials(self):
        """Test behavior when job has no credentials."""
        # Pass None as job to trigger the validation error
        with self.assertRaises(Exception):
            ForwardEnterpriseClient(job=None)
