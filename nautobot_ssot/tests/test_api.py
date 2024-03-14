"""Unit tests for nautobot_ssot."""
from unittest import skip
from django.contrib.auth import get_user_model
from django.urls import reverse
from nautobot.users.models import Token
from nautobot.core.testing import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from nautobot.users.models import Token
from nautobot.utilities.testing.api import APIViewTestCases

from nautobot_ssot import models

User = get_user_model()


class SyncAPITest(APIViewTestCases.APIViewTestCase):  # pylint: disable=too-many-ancestors
    """Test the Sync API."""

    model = models.Sync
    view_namespace = "plugins-api:nautobot_ssot"
    brief_fields = ["source", "target", "id", "dry_run"]

    @classmethod
    def setUpTestData(cls):
        models.Sync.objects.create(source="Nautobot", target="Nautobot", start_time=None, diff={}, dry_run=True)
        models.Sync.objects.create(source="Infoblox", target="Nautobot", start_time=None, diff={}, dry_run=True)

    @skip("Not implemented")
    def test_create_object_without_permission(self):
        pass

    @skip("Not implemented")
    def test_update_object(self):
        pass

    @skip("Not implemented")
    def test_update_object_without_permission(self):
        pass

    @skip("Sync doesn't support bulk operations.")
    def test_bulk_delete_objects(self):
        pass

    @skip("Not implemented")
    def test_delete_object(self):
        pass

    @skip("Not implemented")
    def test_get_object(self):
        pass

    @skip("Not implemented")
    def test_get_object_anonymous(self):
        pass

    @skip("Not implemented")
    def test_list_objects(self):
        pass

    @skip("Not implemented")
    def test_list_objects_anonymous(self):
        pass

    @skip("Not implemented")
    def test_list_objects_brief(self):
        pass

    @skip("Not implemented")
    def test_list_objects_filtered(self):
        pass

    @skip("Not implemented")
    def test_list_objects_unknown_filter_no_strict_filtering(self):
        pass


class SyncLogEntryAPITest(APIViewTestCases.APIViewTestCase):  # pylint: disable=too-many-ancestors
    """Test the SyncLogEntry API."""

    model = models.SyncLogEntry
    view_namespace = "plugins-api:nautobot_ssot"
    brief_fields = ["action", "status"]
    choices_fields = ["action", "status"]

    @classmethod
    def setUpTestData(cls):
        sync = models.Sync.objects.create(source="Nautobot", target="Nautobot", start_time=None, diff={}, dry_run=True)
        models.SyncLogEntry.objects.create(
            sync=sync, timestamp=None, action="create", status="success", diff={}, message="Created successfully"
        )
        models.SyncLogEntry.objects.create(
            sync=sync, timestamp=None, action="create", status="success", diff={}, message="Created successfully"
        )

    @skip("Not implemented")
    def test_create_object_without_permission(self):
        pass

    @skip("Not implemented")
    def test_update_object(self):
        pass

    @skip("Not implemented")
    def test_update_object_without_permission(self):
        pass

    @skip("Sync doesn't support bulk operations.")
    def test_bulk_delete_objects(self):
        pass

    @skip("Not implemented")
    def test_delete_object(self):
        pass

    @skip("Not implemented")
    def test_get_object(self):
        pass

    @skip("Not implemented")
    def test_get_object_anonymous(self):
        pass

    @skip("Not implemented")
    def test_list_objects(self):
        pass

    @skip("Not implemented")
    def test_list_objects_anonymous(self):
        pass

    @skip("Not implemented")
    def test_list_objects_brief(self):
        pass

    @skip("Not implemented")
    def test_list_objects_filtered(self):
        pass

    @skip("Not implemented")
    def test_list_objects_unknown_filter_no_strict_filtering(self):
        pass

    @skip("Not implemented")
    def test_status_options_returns_expected_choices(self):
        pass


class PlaceholderAPITest(TestCase):
    """Test the NautobotSSOTApp API."""

    def setUp(self):
        """Create a superuser and token for API calls."""
        self.user = User.objects.create(username="testuser", is_superuser=True)
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_placeholder(self):
        """Verify that devices can be listed."""
        url = reverse("dcim-api:device-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
