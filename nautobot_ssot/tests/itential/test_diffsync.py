"""Itential SSoT DiffSync tests."""

from nautobot_ssot.tests.itential.fixtures import base


class DiffSyncTestCases(base.ItentialSSoTBaseTestCase):
    """DiffSync test cases."""

    def test_inventory_diff(self):
        """Test diff exists."""
        diff = self.nautobot_adapter.diff_to(self.itential_adapter)
        self.assertTrue(diff.has_diffs())
