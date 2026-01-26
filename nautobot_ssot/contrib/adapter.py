"""Base adapter module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from typing import Dict, List, Type
from nautobot_ssot.contrib.cache import ORMCache
from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from nautobot.extras.models.metadata import MetadataType
from nautobot_ssot.contrib.base import BaseNautobotAdapter, BaseNautobotModel
from nautobot.extras.models import Job
from nautobot_ssot.contrib.interfaces.nautobot.attributes import build_attributes_dict
from functools import lru_cache

class NautobotAdapterMetadataMixin:
    """Mixin class to add Metadata object support to Nautobot-based DiffSync adapters."""

    metadata_type_obj: MetadataType
    metadata_scope_fields: Dict[object, list[str]]

    def __init__(self, *args, **kwargs):
        """Initialize data for"""
        super().__init__(*args, **kwargs)

        # Define the metadata type on the adapter so that can be used on the models crud operations
        self.metadata_scope_fields = {}
        self.get_or_create_metadatatype()

    def get_or_create_metadatatype(self):
        """Retrieve or create a MetadataType object to track the last sync time of this SSoT job."""
        metadata_type__name = self.job.__class__.Meta.data_source
        self.metadata_type_obj, _ = MetadataType.objects.get_or_create(
            name=f"Last sync from {metadata_type__name}",
            defaults={
                "data_type": "datetime",
                "description": f"Timestamp of the last sync from the Data source {metadata_type__name}",
            },
        )
        self.metadata_scope_fields = {}

        for diffsync_model in self.get_model_list():
            # Attach ContentTypes to MetadataType
            content_type = ContentType.objects.get_for_model(diffsync_model._model)
            if content_type not in self.metadata_type_obj.content_types.all():
                self.metadata_type_obj.content_types.add(content_type)
            
            # Define scope fields per model
            self.metadata_scope_fields[diffsync_model] = list(
                {parameter.split("__", maxsplit=1)[0] for parameter in diffsync_model.get_synced_attributes()}
            )


class NautobotAdapter(
        #NautobotAdapterMetadataMixin,
        BaseNautobotAdapter,
        Adapter,
    ):

    def __init__(self, *args, job: Job, sync=None, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job
        #self.sync = sync
        self.cache = kwargs.pop("cache", ORMCache())

        # MetadataType name will be extracted from the Data Source name.

    def add_nautobot_object(self, diffsync_model: Type[BaseNautobotModel], db_obj: Model):
        """Add a new Nautobot object from the ORM into the DiffSync Store."""
        diffsync_object = diffsync_model(
            pk=db_obj.pk,
            **build_attributes_dict(diffsync_model, db_obj, self)
        )
        self.add(diffsync_object)
        return diffsync_object

    def add_child_objects(self, parent_obj: BaseNautobotModel, db_obj: Model):
        """Add child objects to DiffSync store and to parent DiffSync object instance."""
        for db_field_name, diff_field_name in parent_obj._children.items():
            # Get DiffSync codel class for child
            child_model: BaseNautobotModel = getattr(self, db_field_name)
            for child_db_obj in getattr(db_obj, diff_field_name).all():
                parent_obj.add_child(self.add_nautobot_object(child_model, child_db_obj))

    @classmethod
    @lru_cache
    def get_model_list(self) -> List[BaseNautobotModel]:
        """Return a list of all DiffSync models associated with this adapter, including child models not listed in `top_level`."""
         # Get All diffsync models from adapter's top_level attribute
        diffsync_models: List[BaseNautobotModel] = []
        for model_name in self.top_level:
            diffsync_model = getattr(self, model_name)
            diffsync_models.append(diffsync_model)
            for children_parameter, _ in diffsync_model._children.items():
                diffsync_model_child = getattr(self, model_name=children_parameter)
                diffsync_models.append(diffsync_model_child)
        return diffsync_models

    def load(self):
        """Load data from Nautobot into DiffSync Store."""
        for model_name in self.top_level:
            diffsync_model: BaseNautobotModel = getattr(self, model_name)
            for db_obj in diffsync_model._get_queryset():
                diffsync_obj = self.add_nautobot_object(diffsync_model, db_obj)
                self.add_child_objects(diffsync_obj, db_obj)
