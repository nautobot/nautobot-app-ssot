"""Test Sync."""

from nautobot.apps.testing import ModelTestCases

from nautobot_ssot import models
from nautobot_ssot.tests import fixtures


class TestSync(ModelTestCases.BaseModelTestCase):
    """Test Sync."""

    model = models.Sync

    @classmethod
    def setUpTestData(cls):
        """Create test data for Sync Model."""
        super().setUpTestData()
        # Create 3 objects for the model test cases.
        fixtures.create_sync()

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
