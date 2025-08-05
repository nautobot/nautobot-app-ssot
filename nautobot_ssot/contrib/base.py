"""Abstract base classes for primary contrib module classes.

These base classes are meant to define the expected interactions between the various classes
within contrib to allow for additional customization and extension based on individual needs.

Althought the contrib module provides helpful functionality that cuts for most use cases, significantly
cutting down, not every integration of SSoT will will use both `NautobotModel` and `NautobotAdapter`.

As such, we must identify the requirements and expectations each class has on the other in addition to
the attributes and methods in the parent classes. The intent is any SSoT integration using one contrib
class, but not the other, can inherit from the associated class in their custom definition to ensure the
contrib-provided class can properly interact without raising errors.

TODO: Update references in adapter and model
"""

from abc import ABC, abstractmethod
from uuid import UUID

from typing import get_type_hints, Any
from diffsync import Adapter, DiffSyncModel
from django.db.models import Model
from nautobot.extras.models.metadata import MetadataType
from typing_extensions import ClassVar, Dict, List, Optional

from nautobot_ssot.utils.cache import ORMCache


class BaseNautobotAdapter(Adapter, ABC):
    """Abstract Base Class for `NautobotAdapter`."""

    cache: ORMCache
    metadata_type: MetadataType
    metadata_scope_fields: Dict[DiffSyncModel, List]

    def __init__(self, *args, **kwargs):
        """Initialize the class."""
        self.cache = kwargs.pop("cache", ORMCache())
        self.metadata_type = kwargs.pop("metadata_type", None)
        self.metadata_scope_fields = kwargs.pop("metadata_scope_fields", {})
        return super().__init__(*args, **kwargs)


class BaseNautobotModel(DiffSyncModel, ABC):
    """Abstract Base Class for `NautobotModel`."""

    _model: ClassVar[Model]
    _type_hints: ClassVar[Dict[str, Any]]
    # TODO: Make `adapter` a required field when unittests can be updated.
    #       This will allow the system to validate it was properly created for required functionality.
    adapter: Optional[BaseNautobotAdapter] = None

    # For storing and tracking ORM object primary keys. Not synced.
    pk: Optional[UUID] = None
    
    # Abstract Methods
    # ==============================================

    @classmethod
    @abstractmethod
    def get_queryset(cls):
        """Return queryset for model."""

    # Default Methods
    # ==============================================

    @classmethod
    def get_synced_attributes(cls) -> List[str]:
        """Return a list of attribute names the model compares against in the DiffSync process."""
        return list(cls._identifiers) + list(cls._attributes)

    @classmethod
    def get_model(cls):
        """Return ORM model class attribute."""
        return cls._model

    @classmethod
    def get_type_hints(cls, include_extras=True):
        if not hasattr(cls, "_type_hints"):
            cls._type_hints = get_type_hints(cls, include_extras=include_extras)
        return cls._type_hints
    
    @classmethod
    def get_model_meta_field(cls, attr_name: str):
        """Get attribute metadata from ORM object."""
        return cls._model._meta.get_field(attr_name)
    
    @classmethod
    def get_children(cls):
        """Get `_children` attribute."""
        return cls._children
