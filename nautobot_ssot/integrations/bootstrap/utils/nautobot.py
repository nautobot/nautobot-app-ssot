"""Utility functions for working with Nautobot."""

from datetime import datetime

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.ipam.models import PrefixLocationAssignment, VRFPrefixAssignment

try:
    from nautobot.extras.models.metadata import MetadataType, MetadataTypeDataTypeChoices, ObjectMetadata  # noqa: F401

    from nautobot_ssot.integrations.bootstrap.constants import SCOPED_FIELDS_MAPPING

    METADATA_FOUND = True
except (ImportError, RuntimeError):
    METADATA_FOUND = False


def get_vrf_prefix_assignments(prefix):
    """Retreive all VRF assignments for a Prefix and return a list of VRF Names."""
    _assignments = []
    _vrf_assignments = VRFPrefixAssignment.objects.filter(prefix_id=prefix.id)

    if _vrf_assignments:
        for _vrf in _vrf_assignments:
            _assignments.append(f"{_vrf.vrf.name}__{prefix.namespace.name}")
        return _assignments

    return None


def get_prefix_location_assignments(prefix):
    """Retrieve all Location assignments for a Prefix and return a list of Location Names."""
    _locations = []
    _location_assignments = PrefixLocationAssignment.objects.filter(prefix_id=prefix.id)

    if _location_assignments:
        for _location in _location_assignments:
            _locations.append(_location.location.name)
        return _locations

    return None


if METADATA_FOUND:
    # pylint: disable=duplicate-code
    def add_or_update_metadata_on_object(adapter: Adapter, obj: object) -> ObjectMetadata:  # pylint: disable=inconsistent-return-statements
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
            name="Last Sync from Bootstrap",
            defaults={
                "description": "Describes the last date that a object's field was updated from Bootstrap.",
                "data_type": MetadataTypeDataTypeChoices.TYPE_DATETIME,
            },
        )[0]
        last_sync_type.content_types.add(ContentType.objects.get_for_model(type(obj)))
        try:
            metadata = ObjectMetadata.objects.get(
                assigned_object_id=obj.id,
                metadata_type=last_sync_type,
            )
            metadata.scoped_fields = SCOPED_FIELDS_MAPPING[type(obj)]
        except ObjectMetadata.DoesNotExist:
            metadata = ObjectMetadata(
                assigned_object=obj, metadata_type=last_sync_type, scoped_fields=SCOPED_FIELDS_MAPPING[type(obj)]
            )
        metadata.value = datetime.now().isoformat(timespec="seconds")

        if adapter.job.debug:
            adapter.job.logger.debug(f"Metadata {last_sync_type} added to {obj}.")
        return metadata
