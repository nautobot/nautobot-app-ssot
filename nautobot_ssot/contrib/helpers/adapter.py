"""Helper functions for use with the `NautobotAdapter` class."""

from typing import Type

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model


def get_foreign_key_value(db_obj: Type[Model], parameter_name: str):
    """Get an object's foreign key value given a parameter name with double underscores.

    Given the object from the database as well as the name of parameter in the form of
    f'{foreign_key_field_name}__{remote_field_name}'
    return the field at 'remote_field_name' on the object behind the foreign key at 'foreign_key_field_name'.

    Supports multi-level lookups (multiple `__` in name).

    :param database_object: The Django ORM database object
    :param parameter_name: The field name of the specific relationship to handle
    :return: If present, the object behind the (generic) foreign key, else None
    """
    if "__" not in parameter_name:
        raise ValueError(
            f"Invalid foreign key name: `{parameter_name}`. "
            "Foreign key attributes must have double underscore (`__`) in name"
        )

    # Default to object name and parent object if not provided
    related_model_name, *lookups = parameter_name.split("__")
    related_object = getattr(db_obj, related_model_name)

    # If the foreign key does not point to anything, return None
    if not related_object:
        return None

    # Separate lookups into their search parameters
    nested_lookups = lookups[:-1]
    final_lookup = lookups[-1]

    # For multi-level lookups, we need to recursively lookup the nested objects
    # Last object in `nested_lookups` is used for final lookup
    for lookup in nested_lookups:
        related_object = getattr(related_object, lookup)
        # If the foreign key does not point to anything, return None
        if not related_object:
            return None

    # Return the result of the last lookup directly.
    try:
        return getattr(related_object, final_lookup)
    except AttributeError:
        # If the lookup doesn't point anywhere, check whether it is using the convention for generic foreign keys.
        if final_lookup in ["app_label", "model"]:
            return getattr(ContentType.objects.get_for_model(related_object), final_lookup)
    return None
