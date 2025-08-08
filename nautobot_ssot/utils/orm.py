"""Collection of utility functions for interacting with Django ORM."""

from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, QuerySet
from nautobot.core.models import BaseModel
from nautobot.extras.models import Relationship, RelationshipAssociation
from typing_extensions import Any, Dict, Tuple, Type, get_type_hints, is_typeddict

from nautobot_ssot.contrib.types import RelationshipSideEnum
from nautobot_ssot.utils.types import RelationshipAssociationParameters


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
) -> Dict[str, Any]:
    """Build relationship parameters for retreiving associations of a specified database object.

    Relationship parameters are the fields required to connect one relationship association(s) for a single Nautobot
    object with a custom relationship defined within Nautobot.

    Args:
        relationship (Relationship): Relationship instance from the ORM defining the relationships betweeen two objects.
        db_obj_id (UUID): UUID of database object to build relationship parameters in context to.
        relationship_side (RelationshipSideEnum): Instance of enum defining which side of relationship `db_obj_id` is on.

    Returns:
        Dict[str, Any]: Dictionary of values representing ORM parameters to filter by.

    Raises:
        TypeError: When parameters passed to the function are not of the corret/specified type.

    Returns:
        dict: Dictionary of parameters relative to Nautobot object.
    """
    # Base Parameters, required for all instances
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


def get_custom_relationship_associations(
    relationship: Relationship,
    db_obj: BaseModel,
    relationship_side: RelationshipSideEnum,
) -> Tuple[QuerySet, int]:
    """Get custom relationship associations from database and their count.

    Args:
        relationship (Relationship): Instance of Nautobot `Relationship` object.
        db_obj (BaseModel): Instance of Nautobot `BaseModel`.
            NOTE: Nautobot's `BaseModel` is required vs Django's `BaseModel` because relationship associations
                are linked to an object the the UUID, which is not a default field in Django's `BaseModel` object.
        relationship_side (RelationshipSideEnum): Enum defining which side of the relationship `db_obj` is on.

    Returns:
        Tuple[QuerySet, int]:
            Tuple containing the ORM query set of RelationshipAssociations and integer count of total items.

    Raises:
        TypeError: Raised when inputs don't match specified types.
    """
    if not isinstance(relationship, Relationship):
        raise TypeError("`relationship` parameter must be an instance of `nautobot.extras.models.Relationship`")
    if not isinstance(db_obj, BaseModel):
        raise TypeError("`db_obj` parameter must be a child of `nautobot.core.models.BaseModel`")
    if not isinstance(relationship_side, RelationshipSideEnum):
        raise TypeError(
            "`relationship_side` parameter must be instance of `nautobot_ssot.contrib.types.RelationshipSideEnum"
        )

    relationship_associations = RelationshipAssociation.objects.filter(
        **get_custom_relationship_association_parameters(
            relationship=relationship,
            db_obj_id=db_obj.id,
            relationship_side=relationship_side,
        )
    )
    return relationship_associations, relationship_associations.count()
