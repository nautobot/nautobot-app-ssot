"""Utility type definitions."""

from typing import Optional, TypedDict
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models import Relationship


class RelationshipAssociationParameters(TypedDict):
    """TypedDict defining relationship association parameters."""

    relationship: Relationship
    source_type: ContentType
    destination_type: ContentType
    source_id: Optional[UUID]
    destination_id: Optional[UUID]
