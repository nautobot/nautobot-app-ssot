"""Itential Automation Gateway Fixtures."""

from nautobot.extras.models import Secret, SecretsGroup, SecretsGroupAssociation, ExternalIntegration, Status
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.dcim.models import LocationType, Location

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel

gateways = [
    {
        "name": "IAG1",
        "description": "Test IAG 1",
        "region": "North America",
        "gateway": "https://iag1.example.com:8443",
        "enabled": True,
        "username_env": "IAG1_USERNAME",
        "password_env": "IAG1_PASSWORD",
        "secret_group": "testGroup1",
    },
    {
        "name": "IAG10",
        "description": "Test IAG 10",
        "region": "North America",
        "gateway": "https://iag10.example.com:8443",
        "enabled": False,
        "username_env": "IAG1_USERNAME",
        "password_env": "IAG1_PASSWORD",
        "secret_group": "testGroup1",
    },
    {
        "name": "IAG2",
        "description": "Test IAG 2",
        "region": "Europe",
        "gateway": "https://iag2.example.com:8443",
        "enabled": True,
        "username_env": "IAG2_USERNAME",
        "password_env": "IAG2_PASSWORD",
        "secret_group": "testGroup2",
    },
]

responses = {
    "iag1": {
        "hostname": "https://iag1.example.com:8443",
        "responses": {
            "login": {"token": "abc123="},
            "logout": "User was successfully logged out of session",
            "poll": {"success": True, "hostname": "localhost", "serverId": "00:00:00:00:00:00:8443"},
            "get_devices": {
                "meta": {
                    "count": 1,
                    "query_object": {"offset": None, "limit": None, "filter": None, "order": "ascending"},
                    "total_count": 1,
                },
                "data": [
                    {
                        "name": "rtr1.example.net",
                        "variables": {
                            "ansible_host": "192.0.2.1",
                            "ansible_network_os": "cisco.ios.ios",
                            "ansible_connection": "ansible.netcommon.network_cli",
                            "ansible_port": 22,
                        },
                    }
                ],
            },
            "get_device": {
                "name": "rtr1.example.net",
                "variables": {
                    "ansible_host": "192.0.2.1",
                    "ansible_network_os": "cisco.ios.ios",
                    "ansible_connection": "ansible.netcommon.network_cli",
                    "ansible_port": 22,
                },
            },
            "create_device": {"name": "rtr10.example.net", "variables": {"ansible_host": "192.0.2.10"}},
            "update_device": {"name": "rtr10.example.net", "variables": {"ansible_host": "192.0.2.10"}},
            "delete_device": {"code": 200, "status": 200, "message": "deleted"},
            "get_groups": {
                "meta": {
                    "count": 1,
                    "query_object": {"offset": None, "limit": None, "filter": None, "order": "ascending"},
                    "total_count": 1,
                },
                "data": [
                    {
                        "name": "rtr1.example.net",
                        "variables": {"ansible_user": "testUser", "ansible_password": "testPass"},
                        "devices": ["rtr1.example.net"],
                        "childGroups": [],
                    }
                ],
            },
            "get_group": {
                "name": "rtr1.example.net",
                "variables": {"ansible_user": "testUser", "ansible_password": "testPass"},
                "devices": ["rtr1.example.net"],
                "childGroups": [],
            },
            "create_group": {
                "name": "test-group",
                "variables": {},
                "devices": [],
                "childGroups": [],
            },
            "update_group": {
                "name": "test-group",
                "variables": {"key": "value"},
                "devices": [],
                "childGroups": [],
            },
            "delete_group": {"code": 200, "status": 200, "message": "deleted"},
        },
    },
}


def update_or_create_automation_gateways(
    name: str,
    description: str,
    location: str,
    region: str,
    gateway: str,
    enabled: bool,
    username_env: str,
    password_env: str,
    secret_group: str,
):
    """Fixture to populate Automation Gateways."""
    # Fetch the active status
    status = Status.objects.get(name="Active")

    # Create a region location type
    location_type, _ = LocationType.objects.update_or_create(name="Region")

    # Create a region location
    location, _ = Location.objects.update_or_create(name=region, location_type=location_type, status=status)

    # Create a REST username secret
    secret_username, _ = Secret.objects.update_or_create(
        name=username_env, provider="environment-variable", parameters={"variable": username_env}
    )

    # Create a REST password secret
    secret_password, _ = Secret.objects.update_or_create(
        name=password_env, provider="environment-variable", parameters={"variable": password_env}
    )

    # Create a secrets group
    secret_group, _ = SecretsGroup.objects.update_or_create(name=secret_group)

    # Associate the REST username with the secrets group
    username_assoc, _ = SecretsGroupAssociation.objects.update_or_create(
        secrets_group=secret_group,
        secret=secret_username,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )

    # Associate the REST password with the secrets group
    password_assoc, _ = SecretsGroupAssociation.objects.update_or_create(
        secrets_group=secret_group,
        secret=secret_password,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )

    # Create the external integration
    gateway, _ = ExternalIntegration.objects.update_or_create(name=name, remote_url=gateway, secrets_group=secret_group)

    # Create the Automation Gateway object
    automation_gateway, _ = AutomationGatewayModel.objects.update_or_create(
        name=name, description=description, location=location, gateway=gateway, enabled=enabled
    )
