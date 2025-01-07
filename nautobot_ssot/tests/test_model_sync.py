"""Test Sync."""

from django.test import TestCase

from nautobot_ssot import models


class TestSync(TestCase):
    """Test Sync."""

    def test_create_sync_only_required(self):
        """Create with only required fields, and validate null description and __str__."""
        sync = models.Sync.objects.create(name="Development")
        self.assertEqual(sync.name, "Development")
        self.assertEqual(sync.description, "")
        self.assertEqual(str(sync), "Development")

    def test_create_sync_all_fields_success(self):
        """Create Sync with all fields."""
        sync = models.Sync.objects.create(name="Development", description="Development Test")
        self.assertEqual(sync.name, "Development")
        self.assertEqual(sync.description, "Development Test")
