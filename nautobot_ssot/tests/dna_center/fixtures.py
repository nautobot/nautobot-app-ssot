"""Create fixtures for tests."""

import json


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


LOCATION_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_locations.json")
LOCATION_WO_GLOBAL_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_locations_wo_global.json")
EXPECTED_BUILDING_MAP = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/expected_building_map.json")
EXPECTED_DNAC_LOCATION_MAP = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/expected_dnac_location_map.json")
EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL = load_json(
    path="./nautobot_ssot/tests/dna_center/fixtures/expected_dnac_location_map_wo_global.json"
)
EXPECTED_DNAC_LOCATION_MAP_W_JOB_LOCATION_MAP = load_json(
    path="./nautobot_ssot/tests/dna_center/fixtures/expected_dnac_location_map_w_job_location_map.json"
)
RECV_LOCATION_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_locations_recv.json")
DEVICE_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_devices.json")
RECV_DEVICE_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_devices_recv.json")
DEVICE_DETAIL_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_device_detail.json")
RECV_DEVICE_DETAIL_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_device_detail_recv.json")
PORT_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_port_info.json")
RECV_PORT_FIXTURE = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/get_port_info_recv.json")

EXPECTED_FLOORS = load_json(path="./nautobot_ssot/tests/dna_center/fixtures/expected_floors.json")

MULTI_LEVEL_LOCATION_FIXTURE = load_json(
    path="./nautobot_ssot/tests/dna_center/fixtures/get_multi_level_locations.json"
)
EXPECTED_DNAC_LOCATION_MAP_W_MULTI_LEVEL_LOCATIONS = load_json(
    path="./nautobot_ssot/tests/dna_center/fixtures/expected_dnac_location_map_multi_level_locations.json"
)
DEVICE_DETAIL_MULTI_LEVEL_FIXTURE = load_json(
    path="./nautobot_ssot/tests/dna_center/fixtures/get_device_detail_multi_level.json"
)
