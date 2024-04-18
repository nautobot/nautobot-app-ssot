"""Utility functions for Nautobot ORM."""

import logging
import re
from typing import Mapping
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from nautobot.core.models.utils import slugify
from nautobot.core.settings_funcs import is_truthy
from nautobot.dcim.models import Device
from nautobot.dcim.models import DeviceType
from nautobot.dcim.models import Location
from nautobot.dcim.models import LocationType
from nautobot.dcim.models import Manufacturer
from nautobot.extras.choices import SecretsGroupAccessTypeChoices
from nautobot.extras.choices import SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration
from nautobot.extras.models import Relationship
from nautobot.extras.models import Role
from nautobot.extras.models import Secret
from nautobot.extras.models import SecretsGroup
from nautobot.extras.models import SecretsGroupAssociation
from nautobot.extras.models import Status
from nautobot.extras.models import Tag

from nautobot_ssot.integrations.aristacv import constants
from nautobot_ssot.integrations.aristacv.types import CloudVisionAppConfig

logger = logging.getLogger(__name__)

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM  # noqa: F401 # pylint: disable=unused-import

    LIFECYCLE_MGMT = True
except ImportError:
    logger.info("Device Lifecycle app isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False
except RuntimeError:
    logger.warning(
        "nautobot-device-lifecycle-mgmt is installed but not enabled. Did you forget to add it to your settings.PLUGINS?"
    )
    LIFECYCLE_MGMT = False


def _get_or_create_integration(integration_name: str, config: dict) -> ExternalIntegration:
    slugified_integration_name = slugify(integration_name)
    integration_env_name = slugified_integration_name.upper().replace("-", "_")

    integration, created = ExternalIntegration.objects.get_or_create(
        name=integration_name,
        defaults={
            "remote_url": config.pop("url"),
            "verify_ssl": config.pop("verify_ssl", False),
            "extra_config": config,
        },
    )
    if not created:
        return integration

    secrets_group = SecretsGroup.objects.create(name=f"{slugified_integration_name}-group")
    secret_token = Secret.objects.create(
        name=f"{slugified_integration_name}-token",
        provider="environment-variable",
        parameters={"variable": f"{integration_env_name}_TOKEN"},
    )
    SecretsGroupAssociation.objects.create(
        secret=secret_token,
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
    )
    secret_password = Secret.objects.create(
        name=f"{slugified_integration_name}-password",
        provider="environment-variable",
        parameters={"variable": f"{integration_env_name}_PASSWORD"},
    )
    SecretsGroupAssociation.objects.create(
        secret=secret_password,
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    secret_user = Secret.objects.create(
        name=f"{slugified_integration_name}-user",
        provider="environment-variable",
        parameters={"variable": f"{integration_env_name}_USER"},
    )
    SecretsGroupAssociation.objects.create(
        secret=secret_user,
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    integration.secrets_group = secrets_group
    integration.validated_save()
    return integration


def get_config() -> CloudVisionAppConfig:
    """Get Arista CloudVision configuration from Nautobot settings.

    Reads configuration from external integration if specified by `aristacv_external_integration_name` app configuration.

    Keeps backward compatibility with previous configuration settings.

    Create a new integration if specified but not found.
    """
    app_settings: dict = settings.PLUGINS_CONFIG["nautobot_ssot"]  # type: ignore

    config = {
        "is_on_premise": bool(app_settings.get("aristacv_cvp_host")),
        "delete_devices_on_sync": is_truthy(
            app_settings.get("aristacv_delete_devices_on_sync", constants.DEFAULT_DELETE_DEVICES_ON_SYNC)
        ),
        "from_cloudvision_default_site": app_settings.get(
            "aristacv_from_cloudvision_default_site", constants.DEFAULT_SITE
        ),
        "from_cloudvision_default_device_role": app_settings.get(
            "aristacv_from_cloudvision_default_device_role", constants.DEFAULT_DEVICE_ROLE
        ),
        "from_cloudvision_default_device_role_color": app_settings.get(
            "aristacv_from_cloudvision_default_device_role_color", constants.DEFAULT_DEVICE_ROLE_COLOR
        ),
        "apply_import_tag": is_truthy(
            app_settings.get("aristacv_apply_import_tag", constants.DEFAULT_APPLY_IMPORT_TAG)
        ),
        "import_active": is_truthy(app_settings.get("aristacv_import_active", constants.DEFAULT_IMPORT_ACTIVE)),
        "verify_ssl": is_truthy(app_settings.get("aristacv_verify", constants.DEFAULT_VERIFY_SSL)),
        "token": app_settings.get("aristacv_cvp_token", ""),
        "cvp_user": app_settings.get("aristacv_cvp_user", ""),
        "cvp_password": app_settings.get("aristacv_cvp_password", ""),
        "hostname_patterns": app_settings.get("aristacv_hostname_patterns", []),
        "site_mappings": app_settings.get("aristacv_site_mappings", {}),
        "role_mappings": app_settings.get("aristacv_role_mappings", {}),
        "controller_site": app_settings.get("aristacv_controller_site", ""),
        "create_controller": is_truthy(
            app_settings.get("aristacv_create_controller", constants.DEFAULT_CREATE_CONTROLLER)
        ),
    }

    if config["is_on_premise"]:
        url = app_settings.get("aristacv_cvp_host", "")
        if not url.startswith("http"):
            url = f"https://{url}"
        parsed_url = urlparse(url)
        port = parsed_url.port or app_settings.get("aristacv_cvp_port", 443)
        config["url"] = f"{parsed_url.scheme}://{parsed_url.hostname}:{port}"
    else:
        url = app_settings.get("aristacv_cvaas_url", constants.DEFAULT_CVAAS_URL)
        if not url.startswith("http"):
            url = f"https://{url}"
        parsed_url = urlparse(url)
        config["url"] = f"{parsed_url.scheme}://{parsed_url.hostname}:{parsed_url.port or 443}"

    def convert():
        expected_fields = set(CloudVisionAppConfig._fields)
        for key in list(config):
            if key not in expected_fields:
                logger.warning(f"Unexpected key found in Arista CloudVision config: {key}")
                config.pop(key)

        for key in expected_fields - set(config):
            logger.warning(f"Missing key in Arista CloudVision config: {key}")
            config[key] = ""

        return CloudVisionAppConfig(**config)

    integration_name = app_settings.get("aristacv_external_integration_name")
    if not integration_name:
        return convert()

    integration = _get_or_create_integration(integration_name, {**config})
    integration_config: Mapping = integration.extra_config  # type: ignore
    if not isinstance(integration.extra_config, Mapping):
        integration_config = config

    if isinstance(integration.verify_ssl, bool):
        config["verify_ssl"] = integration.verify_ssl

    config["url"] = integration.remote_url

    config.update(integration_config)

    secrets_group: SecretsGroup = integration.secrets_group  # type: ignore
    if not secrets_group:
        return convert()

    config["cvp_user"] = secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    config["cvp_password"] = secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    config["token"] = secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
    )

    return convert()


def verify_site(site_name):
    """Verifies whether site in app config is created. If not, creates site.

    Args:
        site_name (str): Name of the site.
    """
    loc_type = LocationType.objects.get_or_create(name="Site")[0]
    loc_type.content_types.add(ContentType.objects.get_for_model(Device))
    try:
        site_obj = Location.objects.get(name=site_name, location_type=loc_type)
    except Location.DoesNotExist:
        status, created = Status.objects.get_or_create(name="Staging")
        if created:
            status.content_types.add(ContentType.objects.get_for_model(Location))
        site_obj = Location.objects.create(
            name=site_name,
            status=status,
            location_type=loc_type,
        )
    return site_obj


def verify_device_type_object(device_type):
    """Verifies whether device type object already exists in Nautobot. If not, creates specified device type.

    Args:
        device_type (str): Device model gathered from CloudVision.
    """
    try:
        device_type_obj = DeviceType.objects.get(model=device_type)
    except DeviceType.DoesNotExist:
        device_type_obj = DeviceType(manufacturer=Manufacturer.objects.get(name="Arista"), model=device_type)
        device_type_obj.validated_save()
    return device_type_obj


def verify_device_role_object(role_name, role_color):
    """Verifies device role object exists in Nautobot. If not, creates specified device role.

    Args:
        role_name (str): Role name.
        role_color (str): Role color.
    """
    try:
        role_obj = Role.objects.get(name=role_name)
    except Role.DoesNotExist:
        role_obj = Role.objects.create(name=role_name, color=role_color)
    role_obj.content_types.add(ContentType.objects.get_for_model(Device))
    role_obj.validated_save()
    return role_obj


def verify_import_tag():
    """Verify `cloudvision_imported` tag exists. if not, creates the tag."""
    try:
        import_tag = Tag.objects.get(name="cloudvision_imported")
    except Tag.DoesNotExist:
        import_tag = Tag.objects.create(name="cloudvision_imported", color="ff0000")
        import_tag.content_types.add(ContentType.objects.get_for_model(Device))
        import_tag.validated_save()
    return import_tag


def get_device_version(device):
    """Determines Device version from Custom Field or RelationshipAssociation.

    Args:
        device (Device): The Device object to determine software version for.
    """
    version = ""
    if LIFECYCLE_MGMT:
        software_relation = Relationship.objects.get(label="Software on Device")
        relations = device.get_relationships()
        try:
            assigned_versions = relations["destination"][software_relation]
            if len(assigned_versions) > 0:
                version = assigned_versions[0].source.version
            else:
                return ""
        except KeyError:
            pass
        except IndexError:
            pass
    else:
        version = device.custom_field_data["arista_eos"] if device.custom_field_data.get("arista_eos") else ""
    return version


def parse_hostname(hostname: str, hostname_patterns: list):
    """Parse a device's hostname to find site and role.

    Args:
        hostname (str): Device hostname to be parsed for site and role.
    """
    site, role = None, None
    for pattern in hostname_patterns:
        match = re.search(pattern=pattern, string=hostname)
        if match:
            if "site" in match.groupdict() and match.group("site"):
                site = match.group("site")
            if "role" in match.groupdict() and match.group("role"):
                role = match.group("role")
    return (site, role)
