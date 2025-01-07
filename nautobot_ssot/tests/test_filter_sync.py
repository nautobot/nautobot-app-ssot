"""Test Sync Filter."""

from django.test import TestCase

from nautobot_ssot import filters, models
from nautobot_ssot.tests import fixtures


class SyncFilterTestCase(TestCase):
    """Sync Filter Test Case."""

    queryset = models.Sync.objects.all()
    filterset = filters.SyncFilterSet

    @classmethod
    def setUpTestData(cls):
        """Setup test data for Sync Model."""
        fixtures.create_sync()

    def test_q_search_name(self):
        """Test using Q search with name of Sync."""
        params = {"q": "Test One"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 1)

    def test_q_invalid(self):
        """Test using invalid Q search for Sync."""
        params = {"q": "test-five"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 0)
