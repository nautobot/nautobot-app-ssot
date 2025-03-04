"""Collection of fixtures to be used for unit testing."""

import json


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


GET_ORG_NETWORKS_SENT_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_org_networks_sent.json")
GET_ORG_NETWORKS_RECV_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_org_networks_recv.json")
NETWORK_MAP_FIXTURE = load_json("./nautobot_ssot/tests/meraki//fixtures/network_map.json")
GET_ORG_DEVICES_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_org_devices.json")
GET_ORG_DEVICE_STATUSES_SENT_FIXTURE = load_json(
    "./nautobot_ssot/tests/meraki/fixtures/get_org_device_statuses_sent.json"
)
GET_ORG_DEVICE_STATUSES_RECV_FIXTURE = load_json(
    "./nautobot_ssot/tests/meraki/fixtures/get_org_device_statuses_recv.json"
)
GET_MANAGEMENT_PORTS_SENT_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_management_ports_sent.json")
GET_MANAGEMENT_PORTS_RECV_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_management_ports_recv.json")
GET_ORG_SWITCHPORTS_SENT_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_org_switchports_sent.json")
GET_ORG_SWITCHPORTS_RECV_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_org_switchports_recv.json")
GET_ORG_UPLINK_ADDRESSES_BY_DEVICE_FIXTURE = load_json(
    "./nautobot_ssot/tests/meraki/fixtures/get_org_uplink_addresses_by_device.json"
)
GET_ORG_UPLINK_STATUSES_SENT_FIXTURE = load_json(
    "./nautobot_ssot/tests/meraki/fixtures/get_org_uplink_statuses_sent.json"
)
GET_ORG_UPLINK_STATUSES_RECV_FIXTURE = load_json(
    "./nautobot_ssot/tests/meraki/fixtures/get_org_uplink_statuses_recv.json"
)
GET_SWITCHPORT_STATUSES = load_json("./nautobot_ssot/tests/meraki/fixtures/get_switchport_statuses.json")
GET_UPLINK_SETTINGS_SENT = load_json("./nautobot_ssot/tests/meraki/fixtures/get_uplink_settings_sent.json")
GET_UPLINK_SETTINGS_RECV = load_json("./nautobot_ssot/tests/meraki/fixtures/get_uplink_settings_recv.json")
GET_APPLIANCE_SWITCHPORTS_FIXTURE = load_json("./nautobot_ssot/tests/meraki/fixtures/get_appliance_switchports.json")
