"""Interfaces for interacting with the Nautobot ORM to retrieve data about model attributes.

Each implementation must inherit from `AttributeInterface` to ensure it has the proper attributes
and methods for external interaction.

Data classes for interacting with attributes in the Nautobot database.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, RelationshipAssociation
from typing_extensions import List, Type, get_args, get_type_hints

from nautobot_ssot.contrib.dataclasses.cache import ORMCache
from nautobot_ssot.contrib.helpers import get_relationship_parameters, load_typed_dict
from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)


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

    @abstractmethod
    def load(self, db_obj: Model):
        """Abstract method for loading attribute value.

        This method is specific to each implementation as different implementations do not the same
        process or requirements for loading attribute data.
        """


@dataclass
class StandardAttribute(AttributeInterface):
    """Standard attribute interface.

    Standard attributes are native attributes for the specific model and represented as columns within the database.
    """

    def load(self, db_obj: Model):
        """Standard attributes return the value stored within the model, no additional processing required."""
        return getattr(db_obj, self.name)


@dataclass
class CustomFieldAttribute(AttributeInterface):
    """Attribute interface for custom fields."""

    annotation: CustomFieldAnnotation = field(default=None)

    def __post_init__(self):
        """Initialize the attribute."""
        if not self.annotation:
            raise ValueError("`annotation` parameter required for `CustomFieldAttribute` class.")

    def load(self, db_obj: Model):
        """Standard return the value stored within the model, no additional processing required."""
        if not hasattr(db_obj, "cf"):
            return None
        if self.annotation.name in db_obj.cf:
            return db_obj.cf[self.annotation.key]
        return None


@dataclass
class CustomForeignKeyAttribute(AttributeInterface):
    """Attribute interface for custom foreign keys."""

    annotation: CustomRelationshipAnnotation = field(default=None)
    cache: ORMCache = field(repr=False, default_factory=lambda: ORMCache())  # pylint: disable=unnecessary-lambda

    def __post_init__(self):
        """Initialize the attribute."""
        if not self.annotation:
            raise ValueError(f"annotation field required for `CustomForeignKeyAttribute.")

    def load(self, db_obj: Model):
        """Load custom, one-to-one foreign key attribute."""
        # Raises error if more than one relationship associations returned
        relationship_association = RelationshipAssociation.objects.get(
            **get_relationship_parameters(db_obj, self.annotation, self.cache)
        )
        if not relationship_association:
            return None

        related_object = getattr(
            relationship_association,
            "source" if self.annotation.side == RelationshipSideEnum.DESTINATION else "destination",
        )
        # Discard the first part as there is no actual field on the model corresponding to that part.
        _, *lookups = self.name.split("__")
        for lookup in lookups[:-1]:
            related_object = getattr(related_object, lookup)
        return getattr(related_object, lookups[-1])


@dataclass
class ForeignKeyAttribute(AttributeInterface):
    """Attribute interface for foreign keys."""

    lookups: List[str] = field(init=False, repr=False)
    related_attr_name: str = field(init=False, repr=False)

    def __post_init__(self):
        """Initialize the attribute."""
        if "__" not in self.name:
            raise ValueError(f"Foreign key values require double underscores in attribute name, got {self.name}")
        self.lookups = self.name.split("__")
        self.related_attr_name = self.lookups.pop(-1)

    def get_related_object(self, db_obj: Model, attribute: str):
        """Get related object from Django model instance."""
        return getattr(db_obj, attribute)

    def get_nested_related_object(self, db_obj: Model):
        """Get related objects from the database, multiple relations deep."""
        # Need to get initial related object before loop
        # NOTE: Can't use .pop() because we need the list intact for multiple calls.
        if related_object := getattr(db_obj, self.lookups[0]):
            # Ignore first entry and last entry in loop
            for lookup in self.lookups[1:]:
                related_object = self.get_related_object(related_object, lookup)
                if not related_object:
                    break
            else:
                return related_object
        return None

    def get_lookup_value(self, db_obj: Model):
        """Get the value for an attribute of a related object by its lookup."""
        try:
            return getattr(db_obj, self.related_attr_name)
        # If the lookup doesn't point anywhere, check whether it is using the convention for generic foreign keys.
        except AttributeError:
            if self.related_attr_name in ["app_label", "model"]:
                return getattr(ContentType.objects.get_for_model(db_obj), self.related_attr_name)
        return None

    def load(self, db_obj: Model):
        """Load the foreign key value."""
        related_object = self.get_nested_related_object(db_obj)
        # If the foreign key does not point to anything, return None
        if not related_object:
            return None
        # Return the result of the last lookup directly.
        if attr_value := self.get_lookup_value(related_object):
            return attr_value
        return None


@dataclass
class ManyRelationshipAttribute(AttributeInterface):
    """Interface class for many-to-many and one-to-many relationship attributes."""

    inner_type: type = field(init=False)

    def __post_init__(self):
        """Post initialization."""
        self.inner_type = get_args(self.type_hints)[0]

    def load(self, db_obj: Model):
        """Load standard many-to-many or one-to-many relationship."""
        related_objects = []
        # Loop through all entries of the foreign key.
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        for related_object in getattr(db_obj, self.name).all():
            type_dict = load_typed_dict(self.inner_type, related_object)
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(type_dict.values()):
                related_objects.append(type_dict)

        return related_objects


@dataclass
class CustomManyRelationshipAttribute(AttributeInterface):
    """Attribute interfaces for custom many-to-many and one-to-many attributes."""

    annotation: CustomRelationshipAnnotation
    inner_type: type = field(init=False)
    relationship_type: RelationshipTypeChoices = field(init=False)
    relationship_side: RelationshipSideEnum = field(init=False)
    cache: ORMCache = field(repr=False, default_factory=lambda : ORMCache())  # pylint: disable=unnecessary-lambda

    def __post_init__(self):
        """Post initialization."""
        if not self.annotation:
            raise ValueError(f"annotation field required for `CustomForeignKeyAttribute.")

        # Introspect type annotations to deduce which fields are of interest
        # for this many-to-many relationship.
        diffsync_field_type = get_type_hints(self.model_class)[self.name]
        self.inner_type = get_args(diffsync_field_type)[0]

        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        relationship: Relationship = self.cache.get_from_orm_cache({"label": self.annotation.name}, Relationship)
        self.relationship_type = relationship.type
        self.relationship_side = self.annotation.side

    def get_relationship_associations(self, db_obj: Model):
        """Get a list of related objects from the database."""
        return RelationshipAssociation.objects.filter(
            **get_relationship_parameters(db_obj, self.annotation, self.cache)
        )

    def load(self, db_obj: Model):
        """Load custom many to many or one to many relationship attribute from the database."""
        related_objects_list = []

        for association in self.get_relationship_associations(db_obj):
            related_object = getattr(
                association, "source" if self.relationship_side == RelationshipSideEnum.DESTINATION else "destination"
            )
            dictionary_representation = load_typed_dict(self.inner_type, related_object)
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(dictionary_representation.values()):
                related_objects_list.append(dictionary_representation)

        # For one-to-many, we need to return an object, not a list of objects
        if (
            self.relationship_type == RelationshipTypeChoices.TYPE_ONE_TO_MANY
            and self.relationship_side == RelationshipSideEnum.DESTINATION
        ):
            if not related_objects_list:
                return None

            if len(related_objects_list) == 1:
                return related_objects_list[0]

            raise ObjectCrudException(
                f"More than one related objects for a {RelationshipTypeChoices.TYPE_ONE_TO_MANY} relationship: {related_objects_list}"
            )
        return related_objects_list


def attribute_interface_factory(
    name: str, model_class: NautobotModel, attr_type_hints: dict, cache: ORMCache = None
) -> AttributeInterface:
    """Factory function for building attribute interfaces.

    Attribute interfaces should only ever be created from within this function (except for
    testing modules).
    """
    db_model_class = model_class._model  # pylint: disable=protected-access
    metadata = getattr(attr_type_hints, "__metadata__", [])

    # Check for custom annotations
    for meta in metadata:
        if isinstance(meta, CustomFieldAnnotation):
            return CustomFieldAttribute(
                name=name,
                model_class=model_class,
                type_hints=attr_type_hints,
                annotation=meta,
            )
        if isinstance(meta, CustomRelationshipAnnotation):
            annotation = meta
            break
    else:
        annotation = None

    if "__" in name:
        if annotation:
            return CustomForeignKeyAttribute(
                name=name,
                model_class=model_class,
                type_hints=attr_type_hints,
                annotation=annotation,
                cache=cache,
            )
        return ForeignKeyAttribute(
            name=name,
            model_class=model_class,
            type_hints=attr_type_hints,
        )
    # End if - Foreign Keys

    if annotation:
        return CustomManyRelationshipAttribute(
            name=name,
            model_class=model_class,
            type_hints=attr_type_hints,
            annotation=annotation,
        )

    database_field = db_model_class._meta.get_field(name)

    # Handling of one- and many-to-many non-custom relationship fields.
    #
    # NOTES:
    # - This includes the side of a generic foreign key that constitutes the foreign key,
    #   i.e. the 'one' side.
    # - Must come after checking for `__`/dunder in name since `__` indicates it's a
    #   custom, 1-to-1 foreign key relationship.
    # - Must check for this before checking for database field as custom relationships
    #   will not have a database field for that attribute.
    if database_field.many_to_many or database_field.one_to_many:
        return ManyRelationshipAttribute(
            name=name,
            model_class=model_class,
            type_hints=attr_type_hints,
        )

    # Default type
    return StandardAttribute(
        name=name,
        model_class=model_class,
        type_hints=attr_type_hints,
    )
