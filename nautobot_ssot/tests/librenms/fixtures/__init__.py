"""Fixtures for tests."""

import json


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


DEVICE_FIXTURE_RECV = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_devices.json")["devices"]
LOCATION_FIXURE_RECV = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_locations.json")["locations"]
