"""Abstract base classes for primary contrib module classes.

These base classes are meant to define the expected interactions between the various classes
within contrib to allow for additional customization and extension based on individual needs.

Todo:
  - Add abstract & common methods
  - Update references in adapter and model
"""

from abc import ABC, abstractmethod
from uuid import UUID

from diffsync import Adapter, DiffSyncModel
from django.db.models import Model
from nautobot.extras.models.metadata import MetadataType
from typing_extensions import ClassVar, Dict, List, Optional

from nautobot_ssot.utils.cache import ORMCache


class BaseNautobotAdapter(Adapter, ABC):
    """Abstract Base Class for `NautobotAdapter`.

    TODO: Add `__init__` method to enforce the presence of attributes on initialization.
          This will need to be done when unittests can be updated.
    """

    cache: ORMCache
    metadata_type: MetadataType
    metadata_scope_fields: Dict[DiffSyncModel, List]


class BaseNautobotModel(DiffSyncModel, ABC):
    """Abstract Base Class for `NautobotModel`."""

    _model: ClassVar[Model]
    # TODO: Make `adapter` a required field when unittests can be updated.
    #       This will allow the system to validate it was properly created for required functionality.
    adapter: Optional[BaseNautobotAdapter] = None

    # For storing and tracking ORM object primary keys. Not synced.
    pk: Optional[UUID] = None

    @abstractmethod
    def synced_attributes(self) -> List[str]:
        """Return a list of attribute names the model compares against in the DiffSync process."""
