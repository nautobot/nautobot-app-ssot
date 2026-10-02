"""Fixtures for the Cisco SD-WAN SSoT integration tests."""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_json(filename):
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / filename, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


VEDGES_FIXTURE = load_json("get_vedges.json")
CONTROLLERS_FIXTURE = load_json("get_controllers.json")
INTERFACES_FIXTURE = load_json("get_interfaces.json")


def get_merged_devices():
    """Return the merged device list as CiscoSdwanManager.get_devices() would."""
    devices = list(VEDGES_FIXTURE["data"]) + list(CONTROLLERS_FIXTURE["data"])
    return [device for device in devices if device.get("host-name")]


def attach_interfaces(devices):
    """Attach interface fixtures to devices as CiscoSdwanManager.get_interfaces() would."""
    for device in devices:
        device_id = device.get("system-ip") or device.get("deviceId")
        device["interfaces"] = INTERFACES_FIXTURE.get(device_id, []) if device_id else []
    return devices
