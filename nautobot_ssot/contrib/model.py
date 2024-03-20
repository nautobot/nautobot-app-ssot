"""Base model module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from collections import defaultdict
from uuid import UUID

from typing import Optional

from diffsync import DiffSyncModel
from diffsync.exceptions import ObjectCrudException, ObjectNotUpdated, ObjectNotDeleted, ObjectNotCreated
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, MultipleObjectsReturned
from django.db.models import Model, ProtectedError
from nautobot.extras.models import Relationship, RelationshipAssociation
from nautobot.extras.choices import RelationshipTypeChoices

from typing_extensions import get_type_hints
from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)


class NautobotModel(DiffSyncModel):
    """
    Base model for any diffsync models interfacing with Nautobot through the ORM.

    This provides the `create`, `update` and `delete` operations in a generic fashion, meaning you don't have to
    implement them yourself.

    In order to accomplish this, the `_model` field has to be set on subclasses to map them to the corresponding ORM
    model class.
    """

    _model: Model

    pk: Optional[UUID]

    @classmethod
    def _get_queryset(cls):
        """Get the queryset used to load the models data from Nautobot."""
        available_fields = {field.name for field in cls._model._meta.get_fields()}
        parameter_names = [
            parameter for parameter in list(cls._identifiers) + list(cls._attributes) if parameter in available_fields
        ]
        # Here we identify any foreign keys (i.e. fields with '__' in them) so that we can load them directly in the
        # first query if this function hasn't been overridden.
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]
        qs = cls.get_queryset()
        return qs.prefetch_related(*prefetch_related_parameters)

    @classmethod
    def get_queryset(cls):
        """Get the queryset used to load the models data from Nautobot."""
        return cls._model.objects.all()

    @classmethod
    def _check_field(cls, name):
        """Check whether the given field name is defined on the diffsync (pydantic) model."""
        if name not in cls.__fields__:
            raise ObjectCrudException(f"Field {name} is not defined on the model.")

    def get_from_db(self):
        """Get the ORM object for this diffsync object from the database using the primary key."""
        try:
            return self.diffsync.get_from_orm_cache({"pk": self.pk}, self._model)
        except self._model.DoesNotExist as error:
            raise ObjectCrudException(f"No such {self._model._meta.verbose_name} instance with PK {self.pk}") from error

    def update(self, attrs):
        """Update the ORM object corresponding to this diffsync object."""
        try:
            obj = self.get_from_db()
            self._update_obj_with_parameters(obj, attrs, self.diffsync)
        except ObjectCrudException as error:
            raise ObjectNotUpdated(error) from error
        return super().update(attrs)

    def delete(self):
        """Delete the ORM object corresponding to this diffsync object."""
        try:
            obj = self.get_from_db()
        except ObjectCrudException as error:
            raise ObjectNotDeleted(error) from error
        try:
            obj.delete()
        except ProtectedError as error:
            raise ObjectNotDeleted(f"Couldn't delete {obj} as it is referenced by another object") from error
        return super().delete()

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create the ORM object corresponding to this diffsync object."""
        # Only diffsync cares about the distinction between ids and attrs, we do not.
        # Therefore, we merge the two into parameters.
        parameters = ids.copy()
        parameters.update(attrs)

        # This is in fact callable, because it is a model
        obj = cls._model()  # pylint: disable=not-callable

        try:
            cls._update_obj_with_parameters(obj, parameters, diffsync)
        except ObjectCrudException as error:
            raise ObjectNotCreated(error) from error

        return super().create(diffsync, ids, attrs)

    @classmethod
    def _handle_single_field(
        cls, field, obj, value, relationship_fields, diffsync
    ):  # pylint: disable=too-many-arguments,too-many-locals, too-many-branches
        """Set a single field on a Django object to a given value, or, for relationship fields, prepare setting.

        :param field: The name of the field to set.
        :param obj: The Django ORM object to set the field on.
        :param value: The value to set the field to.
        :param relationship_fields: Helper dictionary containing information on relationship fields.
            This is mutated over the course of this function.
        :param diffsync: The related diffsync adapter used for looking up things in the cache.
        """
        # Use type hints at runtime to determine which fields are custom fields
        type_hints = get_type_hints(cls, include_extras=True)

        cls._check_field(field)

        # Handle custom fields. See CustomFieldAnnotation docstring for more details.
        custom_relationship_annotation = None
        metadata_for_this_field = getattr(type_hints[field], "__metadata__", [])
        for metadata in metadata_for_this_field:
            if isinstance(metadata, CustomFieldAnnotation):
                obj.cf[metadata.key] = value
                return
            if isinstance(metadata, CustomRelationshipAnnotation):
                custom_relationship_annotation = metadata
                break

        # Prepare handling of foreign keys and custom relationship foreign keys.
        # Example: If field is `tenant__group__name`, then
        # `foreign_keys["tenant"]["group__name"] = value` or
        # `custom_relationship_foreign_keys["tenant"]["group__name"] = value`
        # Also, the model class will be added to the dictionary for normal foreign keys, so we can later use it
        # for querying:
        # `foreign_keys["tenant"]["_model_class"] = nautobot.tenancy.models.Tenant
        # For custom relationship foreign keys, we add the annotation instead:
        # `custom_relationship_foreign_keys["tenant"]["_annotation"] = CustomRelationshipAnnotation(...)
        if "__" in field:
            related_model, lookup = field.split("__", maxsplit=1)
            # Custom relationship foreign keys
            if custom_relationship_annotation:
                relationship_fields["custom_relationship_foreign_keys"][related_model][lookup] = value
                relationship_fields["custom_relationship_foreign_keys"][related_model][
                    "_annotation"
                ] = custom_relationship_annotation
            # Normal foreign keys
            else:
                django_field = cls._model._meta.get_field(related_model)
                relationship_fields["foreign_keys"][related_model][lookup] = value
                # Add a special key to the dictionary to point to the related model's class
                relationship_fields["foreign_keys"][related_model]["_model_class"] = django_field.related_model
            return

        # Prepare handling of custom relationship many-to-many fields.
        if custom_relationship_annotation:
            relationship = diffsync.get_from_orm_cache({"label": custom_relationship_annotation.name}, Relationship)
            if custom_relationship_annotation.side == RelationshipSideEnum.DESTINATION:
                related_object_content_type = relationship.source_type
            else:
                related_object_content_type = relationship.destination_type
            related_model_class = related_object_content_type.model_class()
            if (
                relationship.type == RelationshipTypeChoices.TYPE_ONE_TO_MANY
                and custom_relationship_annotation.side == RelationshipSideEnum.DESTINATION
            ):
                relationship_fields["custom_relationship_foreign_keys"][field] = {
                    **value,
                    "_annotation": custom_relationship_annotation,
                }
            else:
                relationship_fields["custom_relationship_many_to_many_fields"][field] = {
                    "objects": [diffsync.get_from_orm_cache(parameters, related_model_class) for parameters in value],
                    "annotation": custom_relationship_annotation,
                }

            return

        django_field = cls._model._meta.get_field(field)

        # Prepare handling of many-to-many fields. If we are dealing with a many-to-many field,
        # we get all the related objects here to later set them once the object has been saved.
        if django_field.many_to_many or django_field.one_to_many:
            try:
                relationship_fields["many_to_many_fields"][field] = [
                    diffsync.get_from_orm_cache(parameters, django_field.related_model) for parameters in value
                ]
            except django_field.related_model.DoesNotExist as error:
                raise ObjectCrudException(
                    f"Unable to populate many to many relationship '{django_field.name}' with parameters {value}, at least one related object not found."
                ) from error
            except MultipleObjectsReturned as error:
                raise ObjectCrudException(
                    f"Unable to populate many to many relationship '{django_field.name}' with parameters {value}, at least one related object found twice."
                ) from error
            return

        # As the default case, just set the attribute directly
        setattr(obj, field, value)

    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters, diffsync):
        """Update a given Nautobot ORM object with the given parameters."""
        relationship_fields = {
            # Example: {"group": {"name": "Group Name", "_model_class": TenantGroup}}
            "foreign_keys": defaultdict(dict),
            # Example: {"tags": [Tag-1, Tag-2]}
            "many_to_many_fields": defaultdict(list),
            # Example: TODO
            "custom_relationship_foreign_keys": defaultdict(dict),
            # Example: TODO
            "custom_relationship_many_to_many_fields": defaultdict(dict),
        }
        for field, value in parameters.items():
            cls._handle_single_field(field, obj, value, relationship_fields, diffsync)

        # Set foreign keys
        cls._lookup_and_set_foreign_keys(relationship_fields["foreign_keys"], obj, diffsync=diffsync)

        # Save the object to the database
        try:
            obj.validated_save()
        except ValidationError as error:
            raise ObjectCrudException(f"Validated save failed for Django object. Parameters: {parameters}") from error

        # Handle relationship association creation. This needs to be after object creation, because relationship
        # association objects rely on both sides already existing.
        cls._lookup_and_set_custom_relationship_foreign_keys(
            relationship_fields["custom_relationship_foreign_keys"], obj, diffsync
        )
        cls._set_custom_relationship_to_many_fields(
            relationship_fields["custom_relationship_many_to_many_fields"], obj, diffsync
        )

        # Set many-to-many fields after saving.
        cls._set_many_to_many_fields(relationship_fields["many_to_many_fields"], obj)

    @classmethod
    def _set_custom_relationship_to_many_fields(cls, custom_relationship_many_to_many_fields, obj, diffsync):
        for _, dictionary in custom_relationship_many_to_many_fields.items():
            annotation = dictionary.pop("annotation")
            objects = dictionary.pop("objects")
            # TODO: Deduplicate this code
            relationship = diffsync.get_from_orm_cache({"label": annotation.name}, Relationship)
            parameters = {
                "relationship": relationship,
                "source_type": relationship.source_type,
                "destination_type": relationship.destination_type,
            }
            associations = []
            if annotation.side == RelationshipSideEnum.SOURCE:
                parameters["source_id"] = obj.id
                for object_to_relate in objects:
                    association_parameters = parameters.copy()
                    association_parameters["destination_id"] = object_to_relate.id
                    try:
                        association = diffsync.get_from_orm_cache(association_parameters, RelationshipAssociation)
                    except RelationshipAssociation.DoesNotExist:
                        association = RelationshipAssociation(**parameters, destination_id=object_to_relate.id)
                        association.validated_save()
                    associations.append(association)
            else:
                parameters["destination_id"] = obj.id
                for object_to_relate in objects:
                    association_parameters = parameters.copy()
                    association_parameters["source_id"] = object_to_relate.id
                    try:
                        association = diffsync.get_from_orm_cache(association_parameters, RelationshipAssociation)
                    except RelationshipAssociation.DoesNotExist:
                        association = RelationshipAssociation(**parameters, source_id=object_to_relate.id)
                        association.validated_save()
                    associations.append(association)
            # Now we need to clean up any associations that we're not `get_or_create`'d in order to achieve
            # declarativeness.
            # TODO: This may benefit from an ORM cache with `filter` capabilities, but I guess the gain in most cases
            # would be fairly minor.
            for existing_association in RelationshipAssociation.objects.filter(**parameters):
                if existing_association not in associations:
                    existing_association.delete()

    @classmethod
    def _set_many_to_many_fields(cls, many_to_many_fields, obj):
        """
        Given a dictionary, set many-to-many relationships on an object.

        This will always use `set`, thereby replacing any elements that are already part of the relationship.

        Example dictionary:
        {
            "relationship_field_name": [<Object 1>, <Object 2>],
            ...
        }
        """
        for field_name, related_objects in many_to_many_fields.items():
            many_to_many_field = getattr(obj, field_name)
            many_to_many_field.set(related_objects)

    @classmethod
    def _lookup_and_set_custom_relationship_foreign_keys(cls, custom_relationship_foreign_keys, obj, diffsync):
        for _, related_model_dict in custom_relationship_foreign_keys.items():
            annotation = related_model_dict.pop("_annotation")
            # TODO: Deduplicate this code
            try:
                relationship = diffsync.get_from_orm_cache({"label": annotation.name}, Relationship)
            except Relationship.DoesNotExist as error:
                raise ObjectCrudException(f"No such relationship with label '{annotation.name}'") from error
            parameters = {
                "relationship": relationship,
                "source_type": relationship.source_type,
                "destination_type": relationship.destination_type,
            }
            if annotation.side == RelationshipSideEnum.SOURCE:
                parameters["source_id"] = obj.id
                related_model_class = relationship.destination_type.model_class()
                try:
                    destination_object = diffsync.get_from_orm_cache(related_model_dict, related_model_class)
                except related_model_class.DoesNotExist as error:
                    raise ObjectCrudException(
                        f"Couldn't resolve custom relationship {relationship.name}, no such {related_model_class._meta.verbose_name} object with parameters {related_model_dict}."
                    ) from error
                except related_model_class.MultipleObjectsReturned as error:
                    raise ObjectCrudException(
                        f"Couldn't resolve custom relationship {relationship.name}, multiple {related_model_class._meta.verbose_name} objects with parameters {related_model_dict}."
                    ) from error
                RelationshipAssociation.objects.update_or_create(
                    **parameters,
                    defaults={"destination_id": destination_object.id},
                )
            else:
                parameters["destination_id"] = obj.id
                source_object = diffsync.get_from_orm_cache(related_model_dict, relationship.source_type.model_class())
                RelationshipAssociation.objects.update_or_create(**parameters, defaults={"source_id": source_object.id})

    @classmethod
    def _lookup_and_set_foreign_keys(cls, foreign_keys, obj, diffsync):
        """
        Given a list of foreign keys as dictionaries, look up and set foreign keys on an object.

        Dictionary should be in the form of:
        [
          {"field_1": "value_1", "field_2": "value_2"},
          ...
        ]
        where each item in the list corresponds to the parameters needed to uniquely identify a foreign key object.
        """
        for field_name, related_model_dict in foreign_keys.items():
            related_model = related_model_dict.pop("_model_class")
            # Generic foreign keys will not have this dictionary field. As such, we need to retrieve the appropriate
            # model class through other means.
            if not related_model:
                try:
                    app_label = related_model_dict.pop("app_label")
                    model = related_model_dict.pop("model")
                except KeyError as error:
                    raise ValueError(
                        f"Missing annotation for '{field_name}__app_label' or '{field_name}__model - this is required"
                        f"for generic foreign keys."
                    ) from error
                try:
                    related_model_content_type = diffsync.get_from_orm_cache(
                        {"app_label": app_label, "model": model}, ContentType
                    )
                    related_model = related_model_content_type.model_class()
                except ContentType.DoesNotExist as error:
                    raise ObjectCrudException(f"Unknown content type '{app_label}.{model}'.") from error
            # Set the foreign key to 'None' when none of the fields are set to anything
            if not any(related_model_dict.values()):
                setattr(obj, field_name, None)
                continue
            try:
                related_object = diffsync.get_from_orm_cache(related_model_dict, related_model)
            except related_model.DoesNotExist as error:
                raise ObjectCrudException(
                    f"Couldn't find '{related_model._meta.verbose_name}' instance behind '{field_name}' with: {related_model_dict}."
                ) from error
            except MultipleObjectsReturned as error:
                raise ObjectCrudException(
                    f"Found multiple instances for {field_name} wit: {related_model_dict}"
                ) from error
            setattr(obj, field_name, related_object)
