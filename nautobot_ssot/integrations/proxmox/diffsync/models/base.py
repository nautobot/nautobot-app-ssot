"""Proxmox VE SSoT base DiffSync model."""

from collections import defaultdict

from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone
from nautobot.dcim.models import Device
from nautobot.extras.models.customfields import CustomField, CustomFieldTypeChoices
from nautobot.extras.models.tags import Tag
from nautobot.ipam.models import IPAddress
from nautobot.virtualization.models import VirtualMachine, VMInterface

from nautobot_ssot.contrib import NautobotModel
from nautobot_ssot.integrations.proxmox.constants import (
    SSOT_CUSTOM_FIELD_KEY,
    SSOT_CUSTOM_FIELD_LABEL,
    SSOT_TAG_NAME,
    get_ssot_tag_name,
)


class ProxmoxModelDiffSync(NautobotModel):
    """Proxmox VE Model DiffSync base model.

    Tags every synced Device/VirtualMachine/VMInterface/IPAddress with the SSoT tag and stamps the
    ``last_synced_from_proxmox_on`` custom field. Also threads ``config`` through the load queryset.
    """

    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters, adapter):
        """Update the object with the parameters then apply the SSoT tag/custom field.

        Args:
            obj (Any): The Nautobot ORM object to update.
            parameters (dict[str, Any]): The parameters to update the object with.
            adapter (Adapter): The adapter used to look up related objects in the cache.
        """
        super()._update_obj_with_parameters(obj, parameters, adapter)
        if isinstance(obj, (Device, VirtualMachine, VMInterface, IPAddress)):
            tag_name = get_ssot_tag_name(getattr(adapter, "config", None))
            cls.tag_object(cls, obj, tag_name=tag_name)

    def tag_object(
        self,
        nautobot_object,
        custom_field_key=SSOT_CUSTOM_FIELD_KEY,
        tag_name=SSOT_TAG_NAME,
    ):
        """Apply the SSoT tag and custom field to the identified object.

        Args:
            nautobot_object (Any): The Nautobot ORM object to tag.
            custom_field_key (str): Key of the custom field to stamp. Defaults to ``SSOT_CUSTOM_FIELD_KEY``.
            tag_name (str): Name of the SSoT tag to apply. Defaults to ``SSOT_TAG_NAME``.
        """
        tag, _ = Tag.objects.get_or_create(name=tag_name)
        if hasattr(nautobot_object, "tags"):
            nautobot_object.tags.add(tag)
        if hasattr(nautobot_object, "cf"):
            if not any(cfield for cfield in CustomField.objects.all() if cfield.key == custom_field_key):
                custom_field_obj, _ = CustomField.objects.get_or_create(
                    type=CustomFieldTypeChoices.TYPE_DATETIME,
                    key=custom_field_key,
                    defaults={
                        "label": SSOT_CUSTOM_FIELD_LABEL,
                    },
                )
                synced_from_models = [Device, VirtualMachine, VMInterface, IPAddress]
                for model in synced_from_models:
                    custom_field_obj.content_types.add(ContentType.objects.get_for_model(model))
                custom_field_obj.validated_save()

            # Stamp at call time (not import time) with minute precision.
            nautobot_object.cf[custom_field_key] = timezone.now().isoformat(timespec="minutes")
        nautobot_object.validated_save()

    @classmethod
    def _get_queryset(cls, config, cluster_filters):
        """Get the queryset used to load the model's data from Nautobot, passing in the config object.

        Foreign-key parameters (those containing ``__``) are prefetched so they load in the first query.

        Args:
            config (SSOTProxmoxConfig): The integration configuration object.
            cluster_filters (QuerySet): Clusters the sync is scoped to, or an empty value for all.

        Returns:
            QuerySet: The prefetched queryset to load the model from.
        """
        available_fields = {field.name for field in cls._model._meta.get_fields()}
        parameter_names = [
            parameter for parameter in list(cls._identifiers) + list(cls._attributes) if parameter in available_fields
        ]
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]
        qs = cls.get_queryset(config, cluster_filters)
        return qs.prefetch_related(*prefetch_related_parameters)

    @classmethod
    def get_queryset(cls, config, cluster_filters):  # pylint: disable=unused-argument
        """Return the queryset for the model. Overridden to accept the config object.

        Args:
            config (SSOTProxmoxConfig): The integration configuration object.
            cluster_filters (QuerySet): Clusters the sync is scoped to, or an empty value for all.

        Returns:
            QuerySet: The queryset to load the model from.
        """
        return cls._model.objects.all()

    @classmethod
    def _update_obj_save_first(cls, obj, parameters, adapter):
        """Save the ORM object with ``save()`` before relationship handling.

        Works around the ``validated_save`` ordering bug for objects (like Prefix) whose validation
        depends on the object already existing. See nautobot/nautobot#6738.

        Args:
            obj (Any): The Nautobot ORM object to save.
            parameters (dict[str, Any]): The parameters to set on the object.
            adapter (Adapter): The adapter used to look up related objects in the cache.
        """
        relationship_fields = {
            "foreign_keys": defaultdict(dict),
            "many_to_many_fields": defaultdict(list),
            "custom_relationship_foreign_keys": defaultdict(dict),
            "custom_relationship_many_to_many_fields": defaultdict(dict),
        }
        for field, value in parameters.items():
            cls._handle_single_field(field, obj, value, relationship_fields, adapter)

        cls._lookup_and_set_foreign_keys(relationship_fields["foreign_keys"], obj, adapter)

        try:
            obj.save()
        except (ValidationError, ValueError) as error:
            raise ObjectCrudException(
                f"Validated save failed for Django object:\n{error}\nParameters: {parameters}"
            ) from error

        cls._lookup_and_set_custom_relationship_foreign_keys(
            relationship_fields["custom_relationship_foreign_keys"], obj, adapter
        )
        cls._set_custom_relationship_to_many_fields(
            relationship_fields["custom_relationship_many_to_many_fields"], obj, adapter
        )
        cls._set_many_to_many_fields(relationship_fields["many_to_many_fields"], obj)
