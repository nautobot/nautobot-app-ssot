"""Create fixtures for tests."""

from nautobot_ssot.models import Sync


def create_sync():
    """Fixture to create necessary number of Sync for tests."""
    Sync.objects.create(name="Test One")
    Sync.objects.create(name="Test Two")
    Sync.objects.create(name="Test Three")
