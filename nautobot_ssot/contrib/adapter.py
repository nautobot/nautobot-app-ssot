"""Base adapter module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

import re
from typing import Dict, List, Type

import pydantic
from diffsync import Adapter, DiffSyncModel
from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship
from nautobot.extras.models.metadata import MetadataType
from django.db.models import QuerySet
from nautobot_ssot.contrib.base import BaseNautobotAdapter, BaseNautobotModel
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)
from nautobot_ssot.utils.cache import ORMCache
from nautobot_ssot.utils.orm import (
    get_custom_relationship_associations,
    load_typed_dict,
    orm_attribute_lookup,
)
from nautobot_ssot.utils.typing import get_inner_type
from nautobot_ssot.contrib.interfaces import NautobotORMInterface
from nautobot.core.models import BaseModel

from dataclasses import dataclass, field
from functools import lru_cache

from typing import Iterable, Any, Union

@dataclass
class BaseInterface:
    """"""

    diffsync_model: BaseNautobotModel

    def get_dict(self, nautobot_object: BaseModel, attributes: list[str]) -> dict:
        """"""




class NautobotAdapter(Adapter, BaseNautobotAdapter):
    """
    Adapter for loading data from Nautobot through the ORM.

    This adapter is able to infer how to load data from Nautobot based on how the models attached to it are defined.
    """

    _interface = NautobotORMInterface

    def __init__(self, *args, job, sync=None, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.cache: ORMCache = kwargs.pop("cache", ORMCache())

    def load(self):
        for model_name in self.top_level:
            self.load_objects_iterable(getattr(self, model_name))

    def load_objects_iterable(self, diffsync_model: BaseNautobotModel, iterable: Iterable = None):
        return [self.load_single_object(diffsync_model, obj_data) for obj_data in iterable]

    def load_single_object(self, diffsync_model: BaseNautobotModel, obj_data: Union[BaseModel, dict]):
        interface = self.get_model_interface(diffsync_model._modelname)
        diffsync_instance = diffsync_model(**interface.get_dict(obj_data, diffsync_model.get_synced_attributes()))
        self.add(diffsync_instance)

        # for child_name, child_plural in diffsync_model._children.items():
        #     child_diffsync_model = getattr(self, child_name)
        #     child_objects = getattr(nautobot_object, child_plural)
        #     diffsync_instance.add_child(child_instance for child_instance in self.load_class_objects(child_diffsync_model, child_objects))
        return diffsync_instance

    @lru_cache
    def get_model_interface(self, model_name: str):
        return self._interface(getattr(self, model_name))
        

