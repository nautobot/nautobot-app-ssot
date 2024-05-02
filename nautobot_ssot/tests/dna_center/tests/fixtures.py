"""Create fixtures for tests."""

import json


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


LOCATION_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_locations.json")
EXPECTED_DNAC_LOCATION_MAP = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/expected_dnac_location_map.json")
EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL = load_json(
    path="./nautobot_ssot_dna_center/tests/fixtures/expected_dnac_location_map_wo_global.json"
)
RECV_LOCATION_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_locations_recv.json")
DEVICE_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_devices.json")
RECV_DEVICE_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_devices_recv.json")
DEVICE_DETAIL_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_device_detail.json")
RECV_DEVICE_DETAIL_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_device_detail_recv.json")
PORT_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_port_info.json")
RECV_PORT_FIXTURE = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/get_port_info_recv.json")

EXPECTED_AREAS = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/expected_areas.json")
EXPECTED_AREAS_WO_GLOBAL = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/expected_areas_wo_global.json")
EXPECTED_BUILDINGS = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/expected_buildings.json")
EXPECTED_FLOORS = load_json(path="./nautobot_ssot_dna_center/tests/fixtures/expected_floors.json")
