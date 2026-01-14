"""Base adapter module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from typing import Dict, List, Type

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from nautobot.extras.models.metadata import MetadataType
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.base import BaseNautobotAdapter, BaseNautobotModel

from nautobot_ssot.utils.cache import ORMCache

from nautobot_ssot.contrib.interfaces.nautobot.attributes import build_attributes_dict




class NautobotAdapter(Adapter, BaseNautobotAdapter):
    """
    Adapter for loading data from Nautobot through the ORM.

    This adapter is able to infer how to load data from Nautobot based on how the models attached to it are defined.
    """

    def __init__(self, *args, job, sync=None, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.cache: ORMCache = kwargs.pop("cache", ORMCache())
        self.metadata_type = None
        self.metadata_scope_fields = {}

    def get_from_orm_cache(self, parameters: Dict, model_class: Type[Model]):
        """Retrieve an object from the ORM or the cache."""
        return self.cache.get_from_orm(model_class, parameters)

    @staticmethod
    def _get_parameter_names(diffsync_model):
        """Ignore the differences between identifiers and attributes, because at this point they don't matter to us."""
        return list(diffsync_model._identifiers) + list(diffsync_model._attributes)  # pylint: disable=protected-access

    def invalidate_cache(self, zero_out_hits=True):
        """Deprecated, kept for backwards compatibility."""
        self.job.logger.warning(
            "Adapter class method `self.invalidate_cache()` is deprecated and will be removed in a future version. "
            "Use `self.cache.invalidate_cache()` instead."
        )
        self.cache.invalidate_cache(zero_out_hits=zero_out_hits)

    def _load_objects(self, diffsync_model: BaseNautobotModel):
        """Given a diffsync model class, load a list of models from the database and return them."""
        parameter_names = diffsync_model.get_synced_attributes()
        for database_object in diffsync_model._get_queryset():
            self._load_single_object(database_object, diffsync_model, parameter_names)

    def load_children(self):
        pass

    def load_object(self, database_object, diffsync_model, parameter_names):
        diffsync_object = diffsync_model(
            pk=database_object.pk,
            **build_attributes_dict(diffsync_model, database_object)
        )
        self.add(diffsync_object)
        self.load_children()

    def _load_single_object(self, database_object, diffsync_model, parameter_names):
        """Load a single diffsync object from a single database object."""
        diffsync_object = diffsync_model(
            pk=database_object.pk,
            **build_attributes_dict(diffsync_model, database_object, self)
        )
        self.add(diffsync_object)
        self._handle_children(database_object, diffsync_object)
        return diffsync_object

    def _handle_children(self, database_object, diffsync_model: BaseNautobotModel):
        """Recurse through all the children for this model."""
        for children_parameter, children_field in diffsync_model._children.items():
            children = getattr(database_object, children_field).all()
            diffsync_model_child: BaseNautobotModel = self._get_diffsync_class(model_name=children_parameter)
            for child in children:
                parameter_names = diffsync_model_child.get_synced_attributes()
                child_diffsync_object = self._load_single_object(child, diffsync_model_child, parameter_names)
                diffsync_model.add_child(child_diffsync_object)

    def load(self):
        """Generic implementation of the load function."""
        if not hasattr(self, "top_level") or not self.top_level:
            raise ValueError("'top_level' needs to be set on the class.")

        for model_name in self.top_level:
            diffsync_model = self._get_diffsync_class(model_name)

            # This function directly mutates the diffsync store, i.e. it will create and load the objects
            # for this specific model class as well as its children without returning anything.
            self._load_objects(diffsync_model)

    def _get_diffsync_class(self, model_name):
        """Given a model name, return the diffsync class."""
        try:
            diffsync_model = getattr(self, model_name)
        except AttributeError as error:
            raise AttributeError(
                f"Please define {model_name} to be the diffsync model on this adapter as a class level attribute."
            ) from error
        return diffsync_model

    def get_or_create_metadatatype(self):
        """Retrieve or create a MetadataType object to track the last sync time of this SSoT job."""
        # MetadataType name will be extracted from the Data Source name.
        metadata_type__name = self.job.__class__.Meta.data_source

        # Create a MetadataType of type datetime
        metadata_type, _ = MetadataType.objects.get_or_create(
            name=f"Last sync from {metadata_type__name}",
            defaults={
                "data_type": "datetime",
                "description": f"Timestamp of the last sync from the Data source {metadata_type__name}",
            },
        )

        # Get All diffsync models from adapter's top_level attribute
        diffsync_models: List[BaseNautobotModel] = []
        for model_name in self.top_level:
            diffsync_model = self._get_diffsync_class(model_name)
            diffsync_models.append(diffsync_model)
            for children_parameter, _ in diffsync_model._children.items():
                diffsync_model_child = self._get_diffsync_class(model_name=children_parameter)
                diffsync_models.append(diffsync_model_child)

        for diffsync_model in diffsync_models:
            # Get nautobot model from diffsync model
            nautobot_model = diffsync_model._model
            # Attach ContentTypes to MetadataType
            content_type = ContentType.objects.get_for_model(nautobot_model)
            if content_type not in metadata_type.content_types.all():
                metadata_type.content_types.add(content_type)
            # Define scope fields per model
            obj_metadata_scope_fields = list(
                {parameter.split("__", maxsplit=1)[0] for parameter in diffsync_model.get_synced_attributes()}
            )
            self.metadata_scope_fields[diffsync_model] = obj_metadata_scope_fields

        # Define the metadata type on the adapter so that can be used on the models crud operations
        self.metadata_type = metadata_type
