"""Fixtures for tests."""

import json


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


SITE_FIXTURE_SENT = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_sites_sent.json")
SITE_FIXTURE_RECV = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_sites_recv.json")
DEVICE_FIXTURE_SENT = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_devices_sent.json")
DEVICE_FIXTURE_RECV = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_devices_recv.json")
VLAN_FIXTURE_SENT = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_vlan_bindings_sent.json")
VLAN_FIXTURE_RECV = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_vlan_bindings_recv.json")
NSIP6_FIXTURE_SENT = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_nsip6_sent.json")
NSIP6_FIXTURE_RECV = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_nsip6_recv.json")
ADM_DEVICE_MAP_FIXTURE = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/adm_device_map.json")
NSIP_FIXTURE_SENT = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_nsip_sent.json")
NSIP_FIXTURE_RECV = load_json("./nautobot_ssot/tests/citrix_adm/fixtures/get_nsip_recv.json")
