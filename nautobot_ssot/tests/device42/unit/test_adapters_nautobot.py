"""Unit tests for the Device42 Nautobot DiffSync adapter."""

from unittest.mock import MagicMock

from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Manufacturer

from nautobot_ssot.integrations.device42.diffsync.adapters.nautobot import NautobotAdapter


class TestNautobotAdapterState(TestCase):
    """Test that each Nautobot adapter starts a sync with its own, empty lookup maps."""

    def test_new_adapter_starts_with_empty_maps(self):
        """Maps filled by one sync are not seen by the next adapter, including IDs of since-deleted objects."""
        manufacturer = Manufacturer.objects.create(name="Acme")
        first = NautobotAdapter(job=MagicMock())
        first.load_manufacturers()
        self.assertEqual(first.vendor_map[manufacturer.name], manufacturer.id)
        manufacturer.delete()

        second = NautobotAdapter(job=MagicMock())
        map_names = [name for name in vars(second) if name.endswith("_map")]
        self.assertEqual(len(map_names), 22)
        for name in map_names:
            with self.subTest(map=name):
                self.assertEqual(getattr(second, name), {})
                self.assertIsNot(getattr(second, name), getattr(first, name))

        second.load_manufacturers()
        self.assertNotIn("Acme", second.vendor_map)
