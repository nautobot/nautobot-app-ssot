"""Utility functions for nautobot_ssot integrations."""

import logging
from datetime import datetime
from typing import Optional

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models.metadata import MetadataType, MetadataTypeDataTypeChoices, ObjectMetadata

logger = logging.getLogger("nautobot.ssot")

_DATE_TYPE_NOTICE_ATTR = "_ssot_metadata_date_type_notice_logged"


def get_last_sync_value(metadata_type: MetadataType, now: Optional[datetime] = None) -> str:
    """Return the "last sync" timestamp formatted for the data type of the given MetadataType.

    The "Last Sync from <integration>" MetadataType is created as DATETIME, but older releases of some
    integrations (e.g. DNA Center prior to v3.9.3) created it as DATE. Nautobot does not allow the
    data_type of an existing MetadataType to be changed, so the value is formatted to match whatever
    type already exists.

    Args:
        metadata_type (MetadataType): MetadataType the value will be assigned to.
        now (Optional[datetime]): Timestamp to format. Defaults to the current time.

    Returns:
        str: `YYYY-MM-DD` for DATE MetadataTypes, otherwise an ISO 8601 datetime (`YYYY-MM-DDTHH:MM:SS`).
    """
    if now is None:
        now = datetime.now()
    if metadata_type.data_type == MetadataTypeDataTypeChoices.TYPE_DATE:
        return now.date().isoformat()
    return now.isoformat(timespec="seconds")


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
    last_sync_type = MetadataType.objects.get_or_create(
        name=f"Last Sync from {adapter.job.data_source}",
        defaults={
            "description": f"Describes the last date that a object's field was updated from {adapter.job.data_source}.",
            "data_type": MetadataTypeDataTypeChoices.TYPE_DATETIME,
        },
    )[0]
    model_type = f"{obj._meta.app_label}.{obj._meta.model_name}"
    relevant_fields = []
    if scoped_fields.get(model_type):
        relevant_fields.extend(scoped_fields[model_type])
    else:
        adapter.job.logger.warning(f"Model type {model_type} not defined in scoped_fields for {obj}.")

    last_sync_type.content_types.add(ContentType.objects.get_for_model(type(obj)))
    try:
        metadata = ObjectMetadata.objects.get(
            assigned_object_id=obj.id,
            metadata_type=last_sync_type,
        )
        metadata.scoped_fields = relevant_fields
    except ObjectMetadata.DoesNotExist:
        metadata = ObjectMetadata(assigned_object=obj, metadata_type=last_sync_type, scoped_fields=relevant_fields)
    if last_sync_type.data_type == MetadataTypeDataTypeChoices.TYPE_DATE and not getattr(
        adapter, _DATE_TYPE_NOTICE_ATTR, False
    ):
        adapter.job.logger.info(
            f"MetadataType {last_sync_type} uses data type 'date' (created by an older release), "
            "so only the date of the last sync will be recorded. To record full timestamps, delete this "
            "MetadataType (this also deletes its existing values) and it will be recreated as 'datetime'."
        )
        setattr(adapter, _DATE_TYPE_NOTICE_ATTR, True)
    metadata.value = get_last_sync_value(last_sync_type)

    if adapter.job.debug:
        adapter.job.logger.debug(f"Metadata {last_sync_type} added to {obj}.")
    return metadata
