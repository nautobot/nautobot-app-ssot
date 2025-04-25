"""Test Sync Filter."""

from nautobot.apps.testing import FilterTestCases

from nautobot_ssot import filters, models
from nautobot_ssot.tests import fixtures


class SyncFilterTestCase(FilterTestCases.FilterTestCase):
    """Sync Filter Test Case."""

    queryset = models.Sync.objects.all()
    filterset = filters.SyncFilterSet
    generic_filter_tests = (
        ("id",),
        ("created",),
        ("last_updated",),
        ("name",),
    )

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
