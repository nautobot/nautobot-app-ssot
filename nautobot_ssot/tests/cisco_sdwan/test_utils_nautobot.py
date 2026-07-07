"""Tests for the Cisco SD-WAN Nautobot utility functions."""

from unittest.mock import MagicMock

from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import Status
from nautobot.ipam.models import VRF, IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.cisco_sdwan.utils.nautobot import (
    get_or_create_ip_address,
    get_or_create_prefix,
    get_or_create_vrf,
)


class TestGetOrCreatePrefix(TransactionTestCase):
    """Test the get_or_create_prefix function."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Prepare a mocked adapter with a Job holding the target Namespace."""
        super().setUp()
        self.namespace = Namespace.objects.get_or_create(name="Global")[0]
        self.adapter = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.namespace = self.namespace

    def test_create_prefix(self):
        """Validate a parent Prefix is created for the given address."""
        prefix = get_or_create_prefix(self.adapter, "192.0.2.10/24")
        self.assertIsNotNone(prefix)
        self.assertEqual(str(prefix.prefix), "192.0.2.0/24")
        self.assertEqual(prefix.namespace, self.namespace)

    def test_get_existing_prefix(self):
        """Validate an existing Prefix is returned instead of creating a duplicate."""
        existing = Prefix.objects.create(
            network="192.0.2.0",
            prefix_length=24,
            namespace=self.namespace,
            status=Status.objects.get(name="Active"),
        )
        prefix = get_or_create_prefix(self.adapter, "192.0.2.10/24")
        self.assertEqual(prefix.id, existing.id)
        self.assertEqual(Prefix.objects.filter(network="192.0.2.0", prefix_length=24).count(), 1)

    def test_create_prefix_in_custom_namespace(self):
        """Validate the Prefix is created in the Namespace selected on the Job."""
        custom_namespace = Namespace.objects.create(name="SDWAN")
        self.adapter.job.namespace = custom_namespace
        prefix = get_or_create_prefix(self.adapter, "192.0.2.10/24")
        self.assertEqual(prefix.namespace, custom_namespace)

    def test_invalid_address(self):
        """Validate None is returned and an error logged for an invalid address."""
        prefix = get_or_create_prefix(self.adapter, "not-an-address/24")
        self.assertIsNone(prefix)
        self.adapter.job.logger.error.assert_called_once()


class TestGetOrCreateIPAddress(TransactionTestCase):
    """Test the get_or_create_ip_address function."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Prepare a mocked adapter and the Status used for created IP Addresses."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        self.adapter = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.ignore_address_mask = True
        self.adapter.job.namespace = Namespace.objects.get_or_create(name="Global")[0]

    def test_create_ip_address_and_parent_prefix(self):
        """Validate the IPAddress and its parent Prefix are created."""
        addr, created_type = get_or_create_ip_address(self.adapter, "192.0.2.10/24", self.status_active)
        self.assertEqual(created_type, "ip_address")
        self.assertEqual(addr.host, "192.0.2.10")
        self.assertEqual(addr.mask_length, 24)
        self.assertTrue(Prefix.objects.filter(network="192.0.2.0", prefix_length=24).exists())

    def test_get_existing_ip_address(self):
        """Validate an existing IPAddress with the same mask is returned unchanged."""
        existing, _ = get_or_create_ip_address(self.adapter, "192.0.2.10/24", self.status_active)
        addr, _ = get_or_create_ip_address(self.adapter, "192.0.2.10/24", self.status_active)
        self.assertEqual(addr.id, existing.id)
        self.assertEqual(IPAddress.objects.filter(host="192.0.2.10").count(), 1)

    def test_mask_mismatch_ignored(self):
        """Validate a mask mismatch is skipped with a warning when ignore_address_mask is set."""
        get_or_create_ip_address(self.adapter, "192.0.2.10/24", self.status_active)
        addr, created_type = get_or_create_ip_address(self.adapter, "192.0.2.10/25", self.status_active)
        self.assertIsNone(addr)
        self.assertIsNone(created_type)
        self.adapter.job.logger.warning.assert_called_once()
        self.assertEqual(IPAddress.objects.get(host="192.0.2.10").mask_length, 24)

    def test_mask_mismatch_updated(self):
        """Validate the existing IPAddress mask is updated when ignore_address_mask is disabled."""
        self.adapter.job.ignore_address_mask = False
        get_or_create_ip_address(self.adapter, "192.0.2.10/24", self.status_active)
        addr, _ = get_or_create_ip_address(self.adapter, "192.0.2.10/25", self.status_active)
        self.assertEqual(addr.mask_length, 25)
        self.assertTrue(Prefix.objects.filter(network="192.0.2.0", prefix_length=25).exists())

    def test_invalid_address(self):
        """Validate (None, None) is returned for an address whose Prefix cannot be created."""
        addr, created_type = get_or_create_ip_address(self.adapter, "not-an-address/24", self.status_active)
        self.assertIsNone(addr)
        self.assertIsNone(created_type)


class TestGetOrCreateVRF(TransactionTestCase):
    """Test the get_or_create_vrf function."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Prepare a mocked adapter."""
        super().setUp()
        self.adapter = MagicMock()
        self.adapter.job.debug = False

    def test_create_vrf(self):
        """Validate the VRF is created when it does not exist."""
        vrf = get_or_create_vrf(self.adapter, "10")
        self.assertEqual(vrf.name, "10")
        self.assertTrue(VRF.objects.filter(name="10").exists())

    def test_get_existing_vrf(self):
        """Validate an existing VRF is returned instead of creating a duplicate."""
        existing = VRF.objects.create(name="10")
        vrf = get_or_create_vrf(self.adapter, "10")
        self.assertEqual(vrf.id, existing.id)
        self.assertEqual(VRF.objects.filter(name="10").count(), 1)
