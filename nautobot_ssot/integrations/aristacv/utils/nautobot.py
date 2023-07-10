"""Utility functions for Nautobot ORM."""
import re
from django.utils.text import slugify

from nautobot.dcim.models import DeviceRole, DeviceType, Manufacturer, Site
from nautobot.extras.models import Status, Tag, Relationship

from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM  # noqa: F401 # pylint: disable=unused-import

    LIFECYCLE_MGMT = True
except ImportError:
    print("Device Lifecycle plugin isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False


def verify_site(site_name):
    """Verifies whether site in plugin config is created. If not, creates site.

    Args:
        site_name (str): Name of the site.
    """
    try:
        site_obj = Site.objects.get(name=site_name)
    except Site.DoesNotExist:
        site_obj = Site(name=site_name, slug=slugify(site_name), status=Status.objects.get(name="Staging"))
        site_obj.validated_save()
    return site_obj


def verify_device_type_object(device_type):
    """Verifies whether device type object already exists in Nautobot. If not, creates specified device type.

    Args:
        device_type (str): Device model gathered from Cloudvision.
    """
    try:
        device_type_obj = DeviceType.objects.get(model=device_type)
    except DeviceType.DoesNotExist:
        device_type_obj = DeviceType(
            manufacturer=Manufacturer.objects.get(name="Arista"), model=device_type, slug=slugify(device_type)
        )
        device_type_obj.validated_save()
    return device_type_obj


def verify_device_role_object(role_name, role_color):
    """Verifies device role object exists in Nautobot. If not, creates specified device role.

    Args:
        role_name (str): Role name.
        role_color (str): Role color.
    """
    try:
        role_obj = DeviceRole.objects.get(name=role_name)
    except DeviceRole.DoesNotExist:
        role_obj = DeviceRole(name=role_name, slug=slugify(role_name), color=role_color)
        role_obj.validated_save()
    return role_obj


def verify_import_tag():
    """Verify `cloudvision_imported` tag exists. if not, creates the tag."""
    try:
        import_tag = Tag.objects.get(name="cloudvision_imported")
    except Tag.DoesNotExist:
        import_tag = Tag(name="cloudvision_imported", slug="cloudvision_imported", color="ff0000")
        import_tag.validated_save()
    return import_tag


def get_device_version(device):
    """Determines Device version from Custom Field or RelationshipAssociation.

    Args:
        device (Device): The Device object to determine software version for.
    """
    version = ""
    if LIFECYCLE_MGMT:
        software_relation = Relationship.objects.get(name="Software on Device")
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


def parse_hostname(hostname: str):
    """Parse a device's hostname to find site and role.

    Args:
        hostname (str): Device hostname to be parsed for site and role.
    """
    hostname_patterns = APP_SETTINGS.get("hostname_patterns")

    site, role = None, None
    for pattern in hostname_patterns:
        match = re.search(pattern=pattern, string=hostname)
        if match:
            if "site" in match.groupdict() and match.group("site"):
                site = match.group("site")
            if "role" in match.groupdict() and match.group("role"):
                role = match.group("role")
    return (site, role)


def get_site_from_map(site_code: str):
    """Get name of Site from site_mapping based upon sitecode.

    Args:
        site_code (str): Site code from device hostname.

    Returns:
        str|None: Name of Site if site code found else None.
    """
    site_map = APP_SETTINGS.get("site_mappings")
    site_name = None
    if site_code in site_map:
        site_name = site_map[site_code]
    return site_name


def get_role_from_map(role_code: str):
    """Get name of Role from role_mapping based upon role code in hostname.

    Args:
        role_code (str): Role code from device hostname.

    Returns:
        str|None: Name of Device Role if role code found else None.
    """
    role_map = APP_SETTINGS.get("role_mappings")
    role_name = None
    if role_code in role_map:
        role_name = role_map[role_code]
    return role_name
