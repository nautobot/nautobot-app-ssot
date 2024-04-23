"""Test Utils."""

import json

from nautobot.dcim.models import Device, Location
from nautobot.ipam.models import VLAN


def json_fixture(json_file_path):
    """Load and return JSON Fixture."""
    with open(json_file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def clean_slate():
    """Delete all objects synced.

    Use this with caution. Never use in production env.
    """
    VLAN.objects.all().delete()
    Device.objects.all().delete()
    Location.objects.all().delete()
