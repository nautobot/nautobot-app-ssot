"""Collection of utility functions for interacting with Django ORM."""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from typing_extensions import Any, Type, get_type_hints, is_typeddict, Dict
from nautobot_ssot.contrib.types import RelationshipSideEnum, CustomRelationshipAnnotation
from nautobot_ssot.utils.cache import ORMCache
from nautobot.extras.models import Relationship, RelationshipAssociation
from nautobot.core.models import BaseModel
from nautobot_ssot.utils.types import RelationshipAssociationParameters
from uuid import UUID

def get_orm_attribute(db_obj: Model, attr_name: str) -> Any:
    """Lookup the value of a single ORM attribute.

    NOTE: Not compatible with foreign key lookups, use `orm_attribute_lookup` instead.
    """
    try:
        return getattr(db_obj, attr_name)
    except AttributeError as err:
        # If the lookup doesn't point anywhere, check whether it is using the convention for generic foreign keys.
        if attr_name in ["app_label", "model"]:
            return getattr(ContentType.objects.get_for_model(db_obj), attr_name)
        raise AttributeError(err)  # pylint: disable=raise-missing-from


def orm_attribute_lookup(db_obj: Model, attr_name: str) -> Any:
    """Get the value of a Django ORM attribute, including foreign key lookups if applicable.

    NOTE: Not compatible with custom relationships or attributes.

    Args:
        attr_name (str): Name of the foreign key attribute to retrieve using Django queryset format
          for foreign keys (`__`).
        db_obj (Model): An instance of a Django ORM model.

    Returns:
        Any: `Any` object with the value of the specified foreign key attribute. This can include,
          but not limited to, ORM model objects, str, int, bool, float, etc.

    Raises:
        TypeError: When the `db_obj` is not a child instance of the Django ORM.
    """
    if not isinstance(db_obj, Model):
        raise TypeError(f"{db_obj} is not an instance of `django.db.models.Model`.")

    if "__" not in attr_name:
        return get_orm_attribute(db_obj, attr_name)
    lookups = attr_name.split("__")
    if related_object := getattr(db_obj, lookups.pop(0)):
        for lookup in lookups:
            related_object = get_orm_attribute(related_object, lookup)
            if not related_object:
                break
    return related_object


def load_typed_dict(typed_dict_class: Type, db_obj: Model) -> dict:
    """Convert a Django ORM object into an associated TypedDict instance.

    Args:
        typed_dict_class (Type): A class type inheriting from TypedDict.
        db_obj (Model): An instance of a Django ORM model.

    Returns:
        dict: An instance of a TypedDict class with keys and values matching the type
          hints specified in the TypedDict.

    Raises:
        TypeError: Raised if the `typed_dict_class` is not a child class of TypedDict.
    """
    if not is_typeddict(typed_dict_class):
        raise TypeError("`typed_dict_class` must be a subclass of `TypedDict`.")
    if not isinstance(db_obj, Model):
        raise TypeError(f"{db_obj} is not an instance of `django.db.models.Model`.")

    typed_dict = {}
    for field_name in get_type_hints(typed_dict_class):
        typed_dict[field_name] = orm_attribute_lookup(db_obj, field_name)
    return typed_dict


def get_custom_relationship_association_parameters(
        relationship: Relationship,
        db_obj_id: UUID,
        relationship_side: RelationshipSideEnum,
    ) -> Dict:
    """Build relationship parameters for retreiving associations of a specified database object."""
    if not isinstance(relationship, Relationship):
        raise TypeError("`relationship` parameter must be type `nautobot.extras.models.relationships.Relationship`")
    if not isinstance(db_obj_id, UUID):
        raise TypeError("`db_obj_id` must be type UUID.")

    parameters = RelationshipAssociationParameters(
        relationship=relationship,
        source_type=relationship.source_type,
        destination_type=relationship.destination_type,
    )

    # Add `source_id` or `destintaion_id` based on identified relationship side.
    # Only the id of the labeled side should be included to get associations for that DB object.
    if relationship_side == RelationshipSideEnum.SOURCE:
        parameters["source_id"] = db_obj_id
    elif relationship_side == RelationshipSideEnum.DESTINATION:
        parameters["destination_id"] = db_obj_id
    else:
        raise ValueError(f"Invalid value for `CustomRelationshipAnnotation.side`: {relationship_side}")
    return parameters
