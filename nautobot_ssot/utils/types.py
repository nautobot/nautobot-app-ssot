""""""

from typing import Optional, TypedDict
from nautobot.extras.models import Relationship
from django.contrib.contenttypes.models import ContentType
from uuid import UUID
from typing_extensions import Optional


class RelationshipAssociationParameters(TypedDict):
    """TypedDict defining relationship association parameters."""

    relationship: Relationship
    source_type: ContentType
    destination_type: ContentType
    source_id = Optional[UUID]
    destination_id = Optional[UUID]
