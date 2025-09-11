"""Utility functions for DiffSync operations in Forward Enterprise integration."""

import uuid
from typing import Any, Dict

from diffsync import DiffSyncModelFlags

from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.diffsync.models.models import (
    DeviceModel,
)


def create_placeholder_device(device_name: str, **kwargs) -> DeviceModel:
    """Create a placeholder DeviceModel with a unique name and specific flags."""
    placeholder_device = DeviceModel(
        name=f"PLACEHOLDER-{device_name}-{uuid.uuid4().hex[:8]}",
        device_type__manufacturer__name="Unknown",
        device_type__model="Unknown",
        status__name=constants.DEFAULT_DEVICE_STATUS,
        role__name=constants.DEFAULT_DEVICE_ROLE,
        location__name="Unknown",
        serial="",
        **kwargs,
    )
    placeholder_device.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_SRC
    return placeholder_device


def log_processing_error(logger, object_type: str, object_id: str, error: Exception, context: Dict[str, Any] = None):
    """Log processing errors in a consistent format."""
    context_info = ""
    if context:
        context_info = f"\nContext: {context}"

    logger.error(
        "Error processing %s %s:\n```\n%s\n```%s",
        object_type,
        object_id,
        error,
        context_info,
    )


def log_processing_warning(logger, object_type: str, object_id: str, warning: str, context: Dict[str, Any] = None):
    """Log processing warnings in a consistent format."""
    context_info = ""
    if context:
        context_info = f"\nContext: {context}"

    logger.warning(
        "Warning processing %s %s:\n```\n%s\n```%s",
        object_type,
        object_id,
        warning,
        context_info,
    )
