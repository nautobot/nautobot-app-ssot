"""Fixtures for tests."""

import json


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


DEVICE_FIXTURE_RECV = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_devices.json")["devices"]
LOCATION_FIXURE_RECV = load_json("./nautobot_ssot/tests/librenms/fixtures/get_librenms_locations.json")["locations"]
ADD_LIBRENMS_DEVICE_SUCCESS = load_json("./nautobot_ssot/tests/librenms/fixtures/add_device_success.json")
ADD_LIBRENMS_DEVICE_FAILURE = load_json("./nautobot_ssot/tests/librenms/fixtures/add_device_failure.json")
ADD_LIBRENMS_DEVICE_PING_FALLBACK = load_json("./nautobot_ssot/tests/librenms/fixtures/add_device_ping_fallback.json")
