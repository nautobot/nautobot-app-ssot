"""Abstract base classes for primary contrib module classes.

NOTE: Classes in this file should not have any implementation.

These base classes are meant to define the expected interactions between the various classes
within contrib to allow for additional customization and extension based on individual needs.

Althought the contrib module provides helpful functionality that cuts for most use cases, significantly
cutting down development time, not every integration of SSoT will will use both `NautobotModel` and `NautobotAdapter`.

As such, we must identify the requirements and expectations each class has on the other in addition to
the attributes and methods in the parent classes. The intent is any SSoT integration using one contrib
class, but not the other, can inherit from the associated class in their custom definition to ensure the
contrib-provided class can properly interact without raising errors.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional
from uuid import UUID

from diffsync import DiffSyncModel
from django.db.models import Model, QuerySet
from nautobot.extras.jobs import BaseJob
from nautobot.extras.models.metadata import MetadataType

from nautobot_ssot.utils.cache import ORMCache


class BaseNautobotAdapter(ABC):
    """Abstract Base Class for `NautobotAdapter`."""

    cache: ORMCache
    job: BaseJob
    metadata_type: MetadataType
    metadata_scope_fields: dict[DiffSyncModel, list]


class BaseNautobotModel(ABC):
    """Abstract Base Class for `NautobotModel`."""

    _model: ClassVar[Model]
    _type_hints: ClassVar[dict[str, Any]]
    adapter: Optional[BaseNautobotAdapter]

    # DB Object Attributes
    pk: Optional[UUID] = None  # For storing and tracking ORM object primary keys. Not synced.

    @classmethod
    @abstractmethod
    def get_synced_attributes(cls) -> list[str]:
        """Abstract method for returning a list of all attributes synced during the SSoT process."""

    @classmethod
    @abstractmethod
    def _get_queryset(cls) -> QuerySet:
        """Abstract method for retreiving data from Nautobot about associated model."""
