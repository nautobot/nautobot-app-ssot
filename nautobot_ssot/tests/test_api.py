"""Unit tests for nautobot_ssot."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from nautobot.users.models import Token
from nautobot.core.testing import TestCase
from rest_framework import status
from rest_framework.test import APIClient


User = get_user_model()


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
