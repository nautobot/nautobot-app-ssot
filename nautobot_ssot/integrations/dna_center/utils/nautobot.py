"""Utility functions for working with Nautobot."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device, Platform
from nautobot.extras.models import Relationship, RelationshipAssociation

try:
    from nautobot.extras.models.metadata import MetadataType, MetadataTypeDataTypeChoices, ObjectMetadata  # noqa: F401

    METADATA_FOUND = True
except (ImportError, RuntimeError):
    METADATA_FOUND = False

from netutils.lib_mapper import ANSIBLE_LIB_MAPPER_REVERSE, NAPALM_LIB_MAPPER_REVERSE

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM

    LIFECYCLE_MGMT = True
except ImportError:
    LIFECYCLE_MGMT = False


def verify_platform(platform_name: str, manu: UUID) -> Platform:
    """Verifies Platform object exists in Nautobot. If not, creates it.

    Args:
        platform_name (str): Name of platform to verify.
        manu (UUID): The ID (primary key) of platform manufacturer.

    Returns:
        Platform: Found or created Platform object.
    """
    if ANSIBLE_LIB_MAPPER_REVERSE.get(platform_name):
        _name = ANSIBLE_LIB_MAPPER_REVERSE[platform_name]
    else:
        _name = platform_name
    if NAPALM_LIB_MAPPER_REVERSE.get(platform_name):
        napalm_driver = NAPALM_LIB_MAPPER_REVERSE[platform_name]
    else:
        napalm_driver = platform_name
    try:
        platform_obj = Platform.objects.get(network_driver=platform_name)
    except Platform.DoesNotExist:
        platform_obj = Platform(
            name=_name, manufacturer_id=manu, napalm_driver=napalm_driver[:50], network_driver=platform_name
        )
        platform_obj.validated_save()
    return platform_obj


def add_software_lcm(adapter, platform: str, version: str):
    """Add OS Version as SoftwareLCM if Device Lifecycle Plugin found.

    Args:
        diffsync (DiffSyncAdapter): DiffSync adapter with Job and maps.
        platform (str): Name of platform to associate version to.
        version (str): The software version to be created for specified platform.

    Returns:
        UUID: UUID of the OS Version that is being found or created.
    """
    try:
        os_ver = SoftwareLCM.objects.get(device_platform_id=adapter.platform_map[platform], version=version).id
    except SoftwareLCM.DoesNotExist:
        adapter.job.logger.info(f"Creating Version {version} for {platform}.")
        os_ver = SoftwareLCM(
            device_platform_id=adapter.platform_map[platform],
            version=version,
        )
        os_ver.validated_save()
        os_ver = os_ver.id
    return os_ver


def assign_version_to_device(adapter, device: Device, software_lcm: UUID):
    """Add Relationship between Device and SoftwareLCM."""
    try:
        software_relation = Relationship.objects.get(label="Software on Device")
        relationship = RelationshipAssociation.objects.get(relationship=software_relation, destination_id=device.id)
        adapter.job.logger.warning(
            f"Deleting Software Version Relationships for {device.name} to assign a new version."
        )
        relationship.delete()
    except RelationshipAssociation.DoesNotExist:
        pass
    new_assoc = RelationshipAssociation(
        relationship=software_relation,
        source_type=ContentType.objects.get_for_model(SoftwareLCM),
        source_id=software_lcm,
        destination_type=ContentType.objects.get_for_model(Device),
        destination_id=device.id,
    )
    new_assoc.validated_save()


if METADATA_FOUND:

    def object_has_metadata(obj: object) -> Optional[bool]:
        """Check if object has MetadataType assigned to it.

        Args:
            obj (object): Object to check for MetadataType.

        Returns:
            bool: True if MetadataType is found, False otherwise.
        """
        try:
            ObjectMetadata.objects.get(
                assigned_object_id=obj.id,
                metadata_type=MetadataType.objects.get(name="Last Sync from DNA Center"),
            )
            return True
        except (MetadataType.DoesNotExist, ObjectMetadata.DoesNotExist):
            return False

    def add_or_update_metadata_on_object(adapter: Adapter, obj: object, scoped_fields: List[str]) -> ObjectMetadata:  # pylint: disable=inconsistent-return-statements
        """Add or Update Metadata on passed object and assign scoped fields.

        Args:
            adapter (Adapter): Adapter that has logging facility.
            obj (object): Object to assign Metadata to.
            scoped_fields (List[str]): List of strings that are scoped fields for object.

        Returns:
            ObjectMetadata: Metadata object that is created or updated.
        """
        if not METADATA_FOUND:
            return None

        last_sync_type = MetadataType.objects.get_or_create(
            name="Last Sync from DNA Center",
            defaults={
                "description": "Describes the last date that a object's field was updated from DNA Center.",
                "data_type": MetadataTypeDataTypeChoices.TYPE_DATE,
            },
        )[0]
        last_sync_type.content_types.add(ContentType.objects.get_for_model(type(obj)))
        try:
            metadata = ObjectMetadata.objects.get(
                assigned_object_id=obj.id,
                metadata_type=last_sync_type,
            )
        except ObjectMetadata.DoesNotExist:
            metadata = ObjectMetadata(assigned_object=obj, metadata_type=last_sync_type, scoped_fields=scoped_fields)
        metadata.value = datetime.today().date().isoformat()
        if adapter.job.debug:
            adapter.job.logger.debug(f"Metadata {last_sync_type} added to {obj}.")
        return metadata
