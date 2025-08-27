"""Utility functions for nautobot_ssot integrations."""

import logging
from datetime import datetime
from typing import Optional

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType

try:
    from nautobot.extras.models.metadata import MetadataType, MetadataTypeDataTypeChoices, ObjectMetadata  # noqa: F401

    METADATA_FOUND = True
except (ImportError, RuntimeError):
    METADATA_FOUND = False

logger = logging.getLogger("nautobot.ssot")


if METADATA_FOUND:

    def object_has_metadata(obj: object, integration: str) -> Optional[bool]:
        """Check if object has MetadataType assigned to it.

        Args:
            obj (object): Object to check for MetadataType.
            integration (str): Name of SSOT integration is use for this Metadata.

        Returns:
            bool: True if MetadataType is found, False otherwise.
        """
        try:
            ObjectMetadata.objects.get(
                assigned_object_id=obj.id,
                metadata_type=MetadataType.objects.get(name=f"Last Sync from {integration}"),
            )
            return True
        except (MetadataType.DoesNotExist, ObjectMetadata.DoesNotExist):
            return False

    def add_or_update_metadata_on_object(
        adapter: Adapter, obj: object, scoped_fields: dict[str, list[str]]
    ) -> ObjectMetadata:  # pylint: disable=inconsistent-return-statements
        """Add or Update Metadata on passed object and assign scoped fields.

        Args:
            adapter (Adapter): Adapter that has logging facility.
            obj (object): Object to assign Metadata to.
            scoped_fields (dict[str, list[str]]): Dictionary mapping objects to a list of scoped fields for object.

        Returns:
            ObjectMetadata: Metadata object that is created or updated.
        """
        if not METADATA_FOUND:
            return None

        last_sync_type = MetadataType.objects.get_or_create(
            name=f"Last Sync from {adapter.job.data_source}",
            defaults={
                "description": f"Describes the last date that a object's field was updated from {adapter.job.data_source}.",
                "data_type": MetadataTypeDataTypeChoices.TYPE_DATETIME,
            },
        )[0]
        model_type = f"{obj._meta.app_label}.{obj._meta.model_name}"
        last_sync_type.content_types.add(ContentType.objects.get_for_model(type(obj)))
        try:
            metadata = ObjectMetadata.objects.get(
                assigned_object_id=obj.id,
                metadata_type=last_sync_type,
            )
            metadata.scoped_fields = scoped_fields[model_type]
        except ObjectMetadata.DoesNotExist:
            metadata = ObjectMetadata(
                assigned_object=obj, metadata_type=last_sync_type, scoped_fields=scoped_fields[model_type]
            )
        metadata.value = datetime.now().isoformat(timespec="seconds")

        if adapter.job.debug:
            adapter.job.logger.debug(f"Metadata {last_sync_type} added to {obj}.")
        return metadata
