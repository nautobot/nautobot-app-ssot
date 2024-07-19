"""Itential SSoT URL fixtures."""

from nautobot_ssot.tests.itential.fixtures import gateways


data = [
    {
        "method": "POST",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/login",
        "json": gateways.responses["iag1"]["responses"].get("login"),
    },
    {
        "method": "POST",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/logout",
        "json": gateways.responses["iag1"]["responses"].get("logout"),
    },
    {
        "method": "GET",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/poll",
        "json": gateways.responses["iag1"]["responses"].get("poll"),
    },
    {
        "method": "GET",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/devices",
        "json": gateways.responses["iag1"]["responses"].get("get_devices"),
    },
    {
        "method": "GET",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/devices/rtr1.example.net",
        "json": gateways.responses["iag1"]["responses"].get("get_device"),
    },
    {
        "method": "POST",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/devices",
        "json": gateways.responses["iag1"]["responses"].get("create_device"),
    },
    {
        "method": "PUT",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/devices/rtr10.example.net",
        "json": gateways.responses["iag1"]["responses"].get("update_device"),
    },
    {
        "method": "DELETE",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/devices/rtr10.example.net",
        "json": gateways.responses["iag1"]["responses"].get("delete_device"),
    },
    {
        "method": "DELETE",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/devices/rtr12.example.net",
        "json": gateways.responses["iag1"]["responses"].get("delete_device"),
    },
    {
        "method": "GET",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/groups",
        "json": gateways.responses["iag1"]["responses"].get("get_groups"),
    },
    {
        "method": "GET",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/groups/all",
        "json": gateways.responses["iag1"]["responses"].get("get_group"),
    },
    {
        "method": "POST",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/groups",
        "json": gateways.responses["iag1"]["responses"].get("create_group"),
    },
    {
        "method": "PUT",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/groups/test-group",
        "json": gateways.responses["iag1"]["responses"].get("update_group"),
    },
    {
        "method": "DELETE",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/groups/test-group",
        "json": gateways.responses["iag1"]["responses"].get("delete_group"),
    },
    {
        "method": "POST",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/groups/all/devices",
        "json": gateways.responses["iag1"]["responses"].get("add_device_to_group"),
    },
    {
        "method": "DELETE",
        "url": f"{gateways.responses['iag1'].get('hostname')}/api/v2.0/groups/all/devices/rtr12.example.net",
        "json": gateways.responses["iag1"]["responses"].get("delete_device_from_group"),
    },
]
