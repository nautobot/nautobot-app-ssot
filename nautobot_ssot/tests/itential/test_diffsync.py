"""Itential SSoT DiffSync tests."""

from nautobot_ssot.tests.itential.fixtures import base


class DiffSyncTestCases(base.ItentialSSoTBaseTestCase):
    """DiffSync test cases."""

    def test_diff_success(self):
        """Test diff exists."""
        diff = self.nautobot_adapter.diff_to(self.itential_adapter)
        self.assertTrue(diff.has_diffs())

    def test_sync_success(self):
        """Test successful sync."""
        self.nautobot_adapter.sync_to(self.itential_adapter)
        diff = self.nautobot_adapter.diff_to(self.itential_adapter)
        self.assertFalse(diff.has_diffs())
