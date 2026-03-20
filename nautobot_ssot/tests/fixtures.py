"""Create fixtures for tests."""

from nautobot_ssot.models import Sync


def create_sync():
    """Fixture to create necessary number of Sync for tests."""
    Sync.objects.create(source="Test One", target="Nautobot", diff={})
    Sync.objects.create(source="Test Two", target="Nautobot", diff={})
    Sync.objects.create(source="Test Three", target="Nautobot", diff={})
