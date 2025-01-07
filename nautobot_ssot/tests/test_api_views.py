"""Unit tests for nautobot_ssot."""

from nautobot.apps.testing import APIViewTestCases

from nautobot_ssot import models
from nautobot_ssot.tests import fixtures


class SyncAPIViewTest(APIViewTestCases.APIViewTestCase):
    # pylint: disable=too-many-ancestors
    """Test the API viewsets for Sync."""

    model = models.Sync
    create_data = [
        {
            "name": "Test Model 1",
            "description": "test description",
        },
        {
            "name": "Test Model 2",
        },
    ]
    bulk_update_data = {"description": "Test Bulk Update"}

    @classmethod
    def setUpTestData(cls):
        fixtures.create_sync()
