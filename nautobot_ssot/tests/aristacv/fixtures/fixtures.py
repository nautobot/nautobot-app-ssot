"""Test fixtures to be used with unit tests."""

import json


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


DEVICE_FIXTURE = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_devices_response.json")
FIXED_INTF_QUERY = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_interfaces_fixed_client_query.json")
CHASSIS_INTF_QUERY = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_interfaces_chassis_client_query.json")
TRANSCEIVER_EEPROM_QUERY = load_json(
    "./nautobot_ssot/tests/aristacv/fixtures/get_interface_transceiver_eeprom_client_query.json"
)
TRANSCEIVER_LOCAL_QUERY = load_json(
    "./nautobot_ssot/tests/aristacv/fixtures/get_interface_transceiver_local_client_query.json"
)
FIXED_INTERFACE_FIXTURE = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_interfaces_fixed_response.json")
CHASSIS_INTERFACE_FIXTURE = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_interfaces_chassis_response.json")
INTF_DESCRIPTION_QUERY = load_json(
    "./nautobot_ssot/tests/aristacv/fixtures/get_interface_description_client_query.json"
)
TRUNK_INTF_MODE_QUERY = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_interface_mode_client_query_trunk.json")
ACCESS_INTF_MODE_QUERY = load_json(
    "./nautobot_ssot/tests/aristacv/fixtures/get_interface_mode_client_query_access.json"
)
IP_INTF_QUERY = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_ip_interfaces_client_query.json")
IP_INTF_FIXTURE = load_json("./nautobot_ssot/tests/aristacv/fixtures/get_ip_interfaces_response.json")
