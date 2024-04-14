"""Itential Automation Gateway Fixtures."""

from nautobot.extras.models import Secret, SecretsGroup, SecretsGroupAssociation, ExternalIntegration, Status
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.dcim.models import LocationType, Location

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel

gateways = [
    {
        "name": "IAG1",
        "description": "Test IAG 1",
        "region": "USA",
        "location": "NYC",
        "gateway": "iag1.example.com",
        "enabled": True,
        "username_env": "IAG1_USERNAME",
        "password_env": "IAG1_PASSWORD",
        "secret_group": "testGroup1",
    },
    {
        "name": "IAG10",
        "description": "Test IAG 10",
        "region": "USA",
        "location": "NYC",
        "gateway": "iag10.example.com",
        "enabled": False,
        "username_env": "IAG1_USERNAME",
        "password_env": "IAG1_PASSWORD",
        "secret_group": "testGroup1",
    },
    {
        "name": "IAG2",
        "description": "Test IAG 2",
        "region": "Europe",
        "location": "LON",
        "gateway": "iag2.example.com",
        "enabled": True,
        "username_env": "IAG2_USERNAME",
        "password_env": "IAG2_PASSWORD",
        "secret_group": "testGroup2",
    },
]

responses = {}


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
    region_type, _ = LocationType.objects.update_or_create(name="Region")

    # Create a site location type
    site_type, _ = LocationType.objects.update_or_create(name="Site", parent=region_type)

    # Create a region location
    region, _ = Location.objects.update_or_create(name=region, location_type=region_type, status=status)

    # Create a location with the region as the parent
    location, _ = Location.objects.update_or_create(
        name=location, location_type=site_type, parent=region, status=status
    )

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
        name=name, description=description, location=region, gateway=gateway, enabled=enabled
    )
