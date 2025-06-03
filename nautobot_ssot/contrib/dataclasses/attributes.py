"""Data classes for interacting with attributes in the Nautobot database."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from django.db.models import Model
from typing_extensions import Type, List
from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models import Relationship, RelationshipAssociation

from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)

from nautobot_ssot.contrib.dataclasses.cache import ORMCache




@dataclass
class AttributeInterface(ABC):
    """Interface class for loading attribute-specific values from the database during SSoT sync.
    
    The contrib modules interact with Nautobot objects to get attribute information. The process
    of getting that data can vary between attribute types and each has their own set of requirements.

    This interface class for attributes provides base requirements for child classes to implement. Any
    external interactions with implementations should be done using methods defined in this interface
    class. Any child classes should not have dependencies for interactions based on added methods or
    attributes.
    """

    name: str
    model_class: Type[Model]
    type_hints: dict = field(repr=False)
    is_sortable: bool = field(default=False)
    metadata: list = field(init=False, repr=False)

    def __post_init__(self):
        """Post initialization."""
        self.__init_attr__()

    def __init_attr__(self):
        """Placeholder method called by `__post_init__` to avoid overloading it."""

    @abstractmethod
    def load(self, obj: Model):
        """Abstract method for loading attribute value.

        This method is specific to each implementation as different implementations do not the same
        process or requirements for loading attribute data.
        """


@dataclass
class StandardAttribute(AttributeInterface):
    """Standard attribute interface.

    Standard attributes are native attributes for the specific model and represented as columns within the database.
    """

    def load(self, obj: Model):
        """Standard attributes return the value stored within the model, no additional processing required."""
        return getattr(obj, self.name)


@dataclass
class CustomFieldAttribute(AttributeInterface):
    """"""

    annotation: CustomFieldAnnotation = field(default=None)

    def __init_attr__(self):
        """"""
        if not self.annotation:
            raise ValueError("`annotation` parameter required for `CustomFieldAttribute` class.")

    def load(self, obj: Model):
        """standard return the value stored within the model, no additional processing required."""
        if not hasattr(obj, "cf"):
            return
        if self.annotation.name in obj.cf:
            return obj.cf[self.annotation.key]
        return None


@dataclass
class ForeignKeyAttribute(AttributeInterface):
    """Attribute interface for foreign keys."""
    
    lookups: List[str] = field(init=False, repr=False)
    related_attr_name: str = field(init=False, repr=False)

    def __init_attr__(self):
        """Initialize the attribute."""
        if "__" not in self.name:
            raise ValueError(f"Foreign key values require double underscores in attribute name, got {self.name}")
        self.lookups = self.name.split("__")
        self.related_attr_name = self.lookups.pop(-1)

    def get_related_object(self, obj: Model, attribute: str):
        """Get related object from Django model instance."""
        return getattr(obj, attribute)
    
    def get_nested_related_object(self, obj: Model):
        """Get related objects from the database, multiple relations deep."""
        # Need to get initial related object before loop
        # NOTE: Can't use .pop() because we need the list intact for multiple calls.
        if related_object := getattr(obj, self.lookups[0]):
            # Ignore first entry and last entry in loop
            for lookup in self.lookups[1:]:
                related_object = self.get_related_object(related_object, lookup)
                if not related_object:
                    break
            else:
                return related_object
        return None
    
    def get_lookup_value(self, obj: Model):
        """Get the value for an attribute of a related object by its lookup."""
        try:
            return getattr(obj, self.related_attr_name)
        # If the lookup doesn't point anywhere, check whether it is using the convention for generic foreign keys.
        except AttributeError:
            if self.related_attr_name in ["app_label", "model"]:
                return getattr(ContentType.objects.get_for_model(obj), self.related_attr_name)
        return None

    def load(self, obj: Model):
        """Load the foreign key value."""
        related_object = self.get_nested_related_object(obj)
        # If the foreign key does not point to anything, return None
        if not related_object:
            return None
        # Return the result of the last lookup directly.
        if attr_value := self.get_lookup_value(related_object):
            return attr_value
        return None


def orm_cache_factory():
    """"""
    return ORMCache()

@dataclass
class CustomForeignKeyAttribute(AttributeInterface):
    """"""

    annotation: CustomFieldAnnotation = field(default=None)
    cache: ORMCache = field(repr=False, default_factory=orm_cache_factory)

    def __init_attr__(self):
        """"""
        if not self.annotation:
            raise ValueError("`annotation` parameter required for `CustomFieldAttribute` class.")


    def relationship_parameters(self, obj: Model):
        """"""
        relationship = self.cache.get_from_orm_cache({"label": self.annotation.name}, Relationship)
        relationship_association_parameters = {
            "relationship": relationship,
            "source_type": relationship.source_type,
            "destination_type": relationship.destination_type,
        }


        if self.annotation.side == RelationshipSideEnum.SOURCE:
            relationship_association_parameters["source_id"] = obj.id
        else:
            relationship_association_parameters["destination_id"] = obj.id
        return relationship_association_parameters


    def load(self, obj: Model):
        """"""




@dataclass
class ManyRelationshipAttribute(AttributeInterface):
    """"""


@dataclass
class CustomManyRelationshipAttribute(AttributeInterface):
    """"""


def attribute_interface_factory(name, model_class, type_hints):
    """"""
    metadata = getattr(type_hints, "__metadata__", [])

    # Check for custom annotations
    for meta in metadata:
        if isinstance(meta, CustomFieldAnnotation):
            is_custom = True
            #return None
            return CustomFieldAttribute(
                name=name,
                model_class=model_class,
                type_hints=type_hints,
                annotation=meta,
            )
        if isinstance(meta, CustomRelationshipAnnotation):
            is_custom = True
            return None
    else:
        is_custom = False

    if "__" in name:
        if is_custom:
            #return CustomForeignKeyAttribute()
            return None
        else:
            return ForeignKeyAttribute(
                name=name,
                model_class=model_class,
                type_hints=type_hints,
            )
    # End if - Foreign Keys

    database_field = model_class._model._meta.get_field(name)
    if database_field.many_to_many or database_field.one_to_many:
        return None
    
    # Default type
    return StandardAttribute(
        name=name,
        model_class=model_class,
        type_hints=type_hints,
    )


    