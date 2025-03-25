"""Diffsync models for Cradlepoint integration."""

import datetime

try:
    from typing import Annotated
except ModuleNotFoundError:
    from typing_extensions import Annotated

from diffsync.enum import DiffSyncModelFlags
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device, DeviceType
from nautobot.extras.models.customfields import CustomField, CustomFieldTypeChoices
from nautobot.extras.models.roles import Role
from nautobot.extras.models.statuses import Status
from nautobot.extras.models.tags import Tag
from typing_extensions import List, Optional, TypedDict

from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel
from nautobot_ssot.integrations.cradlepoint.constants import DEFAULT_MANUFACTURER

TODAY = datetime.date.today().isoformat()


class ContentTypeDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    app_label: str
    model: str


class CradlepointDiffSync(NautobotModel):
    """Cradlepoint diffsync base class."""

    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters, adapter):
        """Update the object with the parameters.

        Args:
            obj (Any): The object to update.
            parameters (dict[str, Any]): The parameters to update the object with.
            adapter (Adapter): The adapter to use to update the object.
        """
        super()._update_obj_with_parameters(obj, parameters, adapter)
        if isinstance(obj, (Device)):
            cls.tag_object(cls, obj)

    def tag_object(
        self,
        nautobot_object,
        custom_field_key="last_synced_from_cradlepoint_on",
        tag_name="SSoT Synced from Cradlepoint",
    ):
        """Apply the given tag and custom field to the identified object.

        Args:
            nautobot_object (Any): Nautobot ORM Object
            custom_field (str): Name of custom field to update
            tag_name (Optional[str], optional): Tag name. Defaults to "SSoT Synced From Cradlepoint".
        """

        def _tag_object(nautobot_object):
            """Apply custom field and tag to object, if applicable."""
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            if hasattr(nautobot_object, "tags"):
                nautobot_object.tags.add(tag)
            if hasattr(nautobot_object, "cf"):
                if not any(
                    cfield
                    for cfield in CustomField.objects.all()
                    if cfield.key == custom_field_key
                ):
                    custom_field_obj, _ = CustomField.objects.get_or_create(
                        type=CustomFieldTypeChoices.TYPE_DATE,
                        key=custom_field_key,
                        defaults={
                            "label": "Last synced from Cradlepoint on",
                        },
                    )
                    synced_from_models = [Device]
                    for model in synced_from_models:
                        custom_field_obj.content_types.add(
                            ContentType.objects.get_for_model(model)
                        )
                    custom_field_obj.validated_save()

                # Update custom field date stamp
                nautobot_object.cf[custom_field_key] = TODAY
            nautobot_object.validated_save()

        _tag_object(nautobot_object)


class CradlepointStatus(NautobotModel):
    """Diffsync model for Status."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Status
    _modelname = "status"
    _identifiers = ("name",)
    _attributes = ("content_types",)

    name: str
    content_types: List[ContentTypeDict] = []

    class Config:
        """Pydantic configuration for the model."""

        protected_namespaces = ()


class CradlepointRole(NautobotModel):
    """Diffsync model for Role."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Role
    _modelname = "device_role"
    _identifiers = ("name",)
    _attributes = ("content_types",)

    name: str
    content_types: List[ContentTypeDict] = []

    class Config:
        """Pydantic configuration for the model."""

        protected_namespaces = ()


class CradlepointDeviceType(NautobotModel):
    """Diffsync model for Device Type."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = DeviceType
    _modelname = "device_type"
    _identifiers = ("model", "manufacturer__name")
    _attributes = ()

    model: str
    manufacturer__name: str

    class Config:
        """Pydantic configuration for the model."""

        protected_namespaces = ()


class CradlepointDevice(CradlepointDiffSync):
    """DiffSync model for Cradlepoint device."""

    # TODO: Possibly make a flag in settings to determine if we want to skip unmatched devices
    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "device_type__model",
        "location__name",
        "role__name",
        "status__name",
        "serial",
        "cradlepoint_id_number",
        "device_latitude",
        "device_longitude",
        "device_altitude",
        "device_gps_method",
        "device_accuracy",
    )
    _children = {}

    name: str
    device_type__model: str
    location__name: str
    role__name: str
    status__name: str
    serial: str
    cradlepoint_id_number: Annotated[
        Optional[str], CustomFieldAnnotation(key="cradlepoint_id_number")
    ] = None
    device_latitude: Annotated[
        Optional[str], CustomFieldAnnotation(key="device_latitude")
    ] = None

    device_longitude: Annotated[
        Optional[str], CustomFieldAnnotation(key="device_longitude")
    ] = None

    device_altitude: Annotated[
        Optional[str], CustomFieldAnnotation(key="device_altitude")
    ] = None

    device_gps_method: Annotated[
        Optional[str], CustomFieldAnnotation(key="device_gps_method")
    ] = None

    device_accuracy: Annotated[
        Optional[int], CustomFieldAnnotation(key="device_accuracy")
    ] = None

    class Config:
        """Pydantic configuration for the model."""

        protected_namespaces = ()

    @classmethod
    def get_queryset(cls):
        """Get queryset for Cradlepoint devices by filtering on Manufacturer."""
        return Device.objects.filter(
            device_type__manufacturer__name=DEFAULT_MANUFACTURER
        )
