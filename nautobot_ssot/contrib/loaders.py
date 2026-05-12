
import pydantic
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)
from diffsync.exceptions import ObjectCrudException
import re
from abc import ABC, abstractmethod
from nautobot.core.models import PrimaryModel
from dataclasses import dataclass, field
from diffsync import DiffSyncModel, Adapter
from typing import Any, Callable
from functools import lru_cache

from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship
from nautobot_ssot.utils.orm import (
    get_custom_relationship_associations,
    load_typed_dict,
    orm_attribute_lookup,
)
from nautobot_ssot.utils.typing import get_inner_type


@dataclass
class BaseDiffSyncLoader(ABC):
    """"""

    model_class: DiffSyncModel

    @abstractmethod
    def load_model(self, input: Any) -> DiffSyncModel:
        """"""

@dataclass
class NautobotORMInterface(BaseDiffSyncLoader):
    """"""

    def load_model(self, input: PrimaryModel, adapter: Adapter) -> DiffSyncModel:
        """Load a single `DiffsyncModel` class from Nautobot ORM data."""
        parameters = {
            attr_name: self.load_attribute_method(attr_name)(input, attr_name)
            for attr_name in self.model_class.get_synced_parameters()
        }
        parameters["pk"] = input.pk
        try:
            return self.model_class(**parameters)
        except pydantic.ValidationError as err:
            raise pydantic.ValidationError(f"Parameters: {parameters}") from err

    @lru_cache
    def load_attribute_method(self, attr_name: str) -> Callable:
        if hasattr(self.model_class, f"load_attr_{attr_name}"):
            return getattr(self.model_class, f"load_attr_{attr_name}")
        annotation = self.model_class.get_attr_annotation(attr_name)
        if isinstance(annotation, CustomFieldAnnotation):
            return self.load_attribute_custom_field
        if "__" in attr_name:
            if annotation:
                return self.load_attribute_custom_foreign_key
            return self.load_attribute_foreign_key
        if annotation:
            return self.load_attribute_custom_n_to_many
        database_field = self.model_class._model._meta.get_field(attr_name)
        if database_field.many_to_many or database_field.one_to_many:
            return self.load_attribute_n_to_many
        return self.load_attribute_standard

    def load_attribute_standard(self, input: PrimaryModel, attr_name: str, parameters: dict = {}) -> dict:
        parameters[attr_name] = getattr(input, attr_name)
        return parameters
                                        
    def load_attribute_foreign_key(self, input: PrimaryModel, attr_name: str, parameters: dict) -> dict:
        parameters[attr_name] = orm_attribute_lookup(input, attr_name)
        return parameters

    def load_attribute_n_to_many(self, input: PrimaryModel, attr_name: str, parameters: dict) -> dict:
        related_objects = []
        for related_object in getattr(input, attr_name).all():
            dict_rep = load_typed_dict(
                get_inner_type(self.model_class, attr_name),
                related_object,
            )
            if any(dict_rep.values()):
                related_objects.append(dict_rep)
        parameters[attr_name] = related_object
        return parameters

    def load_attribute_custom_field(self, input: PrimaryModel, attr_name: str, parameters: dict) -> dict:
        annotation = self.model_class.get_attr_annotation(attr_name)
        field_key = annotation.key or annotation.name
        if field_key in input.cf:
            parameters[attr_name] = input.cf[field_key]
        return parameters

    def load_attribute_custom_foreign_key(self, input: PrimaryModel, attr_name: str, parameters: dict) -> dict:
        """"""
        annotation = self.model_class.get_attr_annotation(attr_name)
        relationship_associations, association_count = get_custom_relationship_associations(
            relationship=self.cache.get_from_orm(Relationship, {"label": annotation.name}),
            db_obj=input,
            relationship_side=annotation.side,
        )

        if association_count == 0:
            return None
        if association_count > 1:
            self.job.logger.warning(
                f"Foreign key ({input.__name__}.{attr_name}) "
                "custom relationship matched two associations - this shouldn't happen."
            )
        
        parameters[attr_name] = orm_attribute_lookup(
            getattr(
                relationship_associations.first(),
                "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination",
            ),
            # Discard the first part of the paramater name as it references the initial related object
            re.sub("^(.*?)__", "", attr_name),
        )
        return parameters


    def load_attribute_custom_n_to_many(self, input: PrimaryModel, attr_name: str, parameters: dict) -> dict:
        """"""
        annotation = self.model_class.get_attr_annotation(attr_name)

# Introspect type annotations to deduce which fields are of interest
        # for this many-to-many relationship.
        inner_type = get_inner_type(self.model_class, attr_name)
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        relationship: Relationship = self.cache.get_from_orm(Relationship, {"label": annotation.name})
        relationship_associations, _ = get_custom_relationship_associations(
            relationship=relationship,
            db_obj=input,
            relationship_side=annotation.side,
        )

        related_objects_list = []
        for association in relationship_associations:
            related_object = getattr(
                association, "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination"
            )
            dictionary_representation = load_typed_dict(inner_type, related_object)
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(dictionary_representation.values()):
                related_objects_list.append(dictionary_representation)

        # For one-to-many, we need to return an object, not a list of objects
        if (
            relationship.type == RelationshipTypeChoices.TYPE_ONE_TO_MANY
            and annotation.side == RelationshipSideEnum.DESTINATION
        ):
            if not related_objects_list:
                return None

            if len(related_objects_list) == 1:
                return related_objects_list[0]

            raise ObjectCrudException(
                f"More than one related objects for a {RelationshipTypeChoices.TYPE_ONE_TO_MANY} relationship: {related_objects_list}"
            )

        parameters[attr_name] = related_objects_list
        return parameters
