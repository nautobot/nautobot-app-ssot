"""Utility functions for nautobot_ssot."""

from django.db.models import Prefetch

from ..choices import SyncRecordActionChoices
from ..models import SyncRecord


def reconstruct_diff_from_records(sync):
    """Reconstruct the diff structure from SyncRecord objects for a given Sync.

    Args:
        sync: A Sync instance

    Returns:
        dict: A diff dictionary in the format expected by DiffSync diff structure:
        {
            "record_type": {
                "object_name": {
                    "+": { ...added/changed attributes... },
                    "-": { ...removed/changed attributes... },
                    "nested_record_type": {
                        "nested_object": { ... }
                    }
                }
            }
        }
    """
    diff = {}
    # Fetch all records with children prefetched to avoid N+1 queries
    all_records = sync.records.select_related("parent").prefetch_related(
        Prefetch("children", queryset=SyncRecord.objects.select_related("parent"))
    )
    # Build a dictionary of children by parent_id for efficient recursive lookup
    children_by_parent = {}
    for record in all_records:
        if record.parent_id:
            if record.parent_id not in children_by_parent:
                children_by_parent[record.parent_id] = []
            children_by_parent[record.parent_id].append(record)

    def process_record(record, parent_dict):
        """Recursively process a SyncRecord and add it to the diff structure.

        Args:
            record: SyncRecord instance
            parent_dict: The parent dictionary in the diff structure to add this record to
        """
        record_type = record.obj_type
        obj_name = record.obj_name

        # Ensure record_type exists in parent_dict
        if record_type not in parent_dict:
            parent_dict[record_type] = {}

        # Ensure object_name exists under record_type
        if obj_name not in parent_dict[record_type]:
            parent_dict[record_type][obj_name] = {}

        obj_dict = parent_dict[record_type][obj_name]

        # Process attributes based on action
        source_attrs = record.source_attrs or {}
        target_attrs = record.target_attrs or {}

        if record.action == SyncRecordActionChoices.ACTION_CREATE:
            # Create: all target attributes go to "+"
            if target_attrs:
                obj_dict["+"] = target_attrs.copy()
        elif record.action == SyncRecordActionChoices.ACTION_UPDATE:
            # Update: compare source and target to find changes
            added_changed = {}
            removed_changed = {}

            # Find attributes that are new or changed
            for key, value in target_attrs.items():
                if key not in source_attrs or source_attrs[key] != value:
                    added_changed[key] = value

            # Find attributes that were removed or changed
            for key, value in source_attrs.items():
                if key not in target_attrs:
                    removed_changed[key] = value
                elif target_attrs[key] != value:
                    # Changed: old value goes to "-"
                    removed_changed[key] = value

            if added_changed:
                obj_dict["+"] = added_changed
            if removed_changed:
                obj_dict["-"] = removed_changed
        elif record.action == SyncRecordActionChoices.ACTION_DELETE:
            # Delete: all source attributes go to "-"
            if source_attrs:
                obj_dict["-"] = source_attrs.copy()

        # Process children recursively using the children_by_parent lookup
        child_records = children_by_parent.get(record.id, [])
        for child_record in child_records:
            process_record(child_record, obj_dict)

    # Process all top-level records (those without a parent)
    top_level_records = [r for r in all_records if r.parent_id is None]
    for record in top_level_records:
        process_record(record, diff)

    return diff
