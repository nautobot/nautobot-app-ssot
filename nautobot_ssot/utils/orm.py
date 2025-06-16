"""Collection of untility functions for interacting with Django ORM."""

from django.db.models import Model
from typing_extensions import Any, Type, get_type_hints, is_typeddict


def get_orm_attribute(attr_name: str, db_obj: Model) -> Any:
    """Get the value of a Django ORM foreign key attribute using the Django queryset format.

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
        return getattr(db_obj, attr_name)
    lookups = attr_name.split("__")
    if related_object := getattr(db_obj, lookups.pop(0)):
        for lookup in lookups:
            related_object = getattr(related_object, lookup)
            if not related_object:
                break
    return related_object


def load_typed_dict(typed_dict_class: Type, db_obj: Model) -> dict:
    """Convert a Django ORM object into an associated TypedDict.

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
        typed_dict[field_name] = get_orm_attribute(field_name, db_obj)
    return typed_dict
