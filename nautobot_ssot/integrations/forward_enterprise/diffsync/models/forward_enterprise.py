"""Forward Enterprise Models for Forward Enterprise integration with SSoT app."""

from typing import List, Optional

try:
    from typing import Annotated  # Python>=3.9
except ImportError:
    from typing_extensions import Annotated

from diffsync.exceptions import ObjectCrudException
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from nautobot.dcim.models import Device, DeviceType, Interface, Location, Manufacturer, Platform
from nautobot.extras.models import Role
from pydantic import Field, field_validator

from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel
from nautobot_ssot.contrib.typeddicts import ContentTypeDict, TagDict
from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.utils.location_helpers import normalize_location_name
from nautobot_ssot.integrations.forward_enterprise.utils.nautobot import (
    get_default_device_role,
    get_default_device_status,
    get_default_interface_status,
    get_status,
    normalize_interface_type,
)

from .base import ensure_not_none


class ModelQuerySetMixin:
    """Mixin only getting objects that are tagged."""

    @classmethod
    def get_queryset(cls, data):
        """Get the queryset for the model."""
        tagged = data.get("sync_forward_tagged_only")

        if tagged:
            # For models with tags (like Interface), filter by tag
            if hasattr(cls._model, "tags"):
                queryset = cls._model.objects.filter(tags__name="SSoT Synced from Forward Enterprise")
                return queryset
            # For models with custom fields but no tags, filter by system_of_record
            if hasattr(cls._model, "_custom_field_data"):
                return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

        queryset = cls._model.objects.all()
        return queryset

    @classmethod
    def _get_queryset(cls, data):
        """Get the queryset used to load the models data from Nautobot."""
        available_fields = {field.name for field in cls._model._meta.get_fields()}
        parameter_names = [
            parameter for parameter in list(cls._identifiers) + list(cls._attributes) if parameter in available_fields
        ]
        # Here we identify any foreign keys (i.e. fields with '__' in them) so that we can load them directly in the
        # first query if this function hasn't been overridden.
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]
        qs = cls.get_queryset(data=data)
        return qs.prefetch_related(*prefetch_related_parameters)


class LocationModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Location."""

    _model = Location
    _modelname = "location"
    _identifiers = ("name",)
    _attributes = (
        "location_type__name",
        "description",
        "status__name",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )

    name: str
    location_type__name: str
    description: Optional[str] = ""
    status__name: str
    tags: List[TagDict] = Field(default_factory=list)
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Location with info logging."""
        if adapter.job:
            adapter.job.logger.info("Creating Location: %s", ids["name"])
        return super().create(adapter, ids, attrs)


class ManufacturerModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Manufacturer."""

    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = ("system_of_record", "last_synced_from_sor")

    name: str
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Manufacturer with info logging."""
        if adapter.job:
            adapter.job.logger.info("Creating Manufacturer: %s", ids["name"])
        return super().create(adapter, ids, attrs)


class DeviceTypeModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a DeviceType."""

    _model = DeviceType
    _modelname = "device_type"
    _identifiers = ("model", "manufacturer__name")
    _attributes = ("tags", "system_of_record", "last_synced_from_sor")

    model: str
    manufacturer__name: str
    tags: List[TagDict] = Field(default_factory=list)
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DeviceType with info logging."""
        if adapter.job:
            adapter.job.logger.info("Creating DeviceType: %s (%s)", ids["model"], ids["manufacturer__name"])
        return super().create(adapter, ids, attrs)


class PlatformModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Platform."""

    _model = Platform
    _modelname = "platform"
    _identifiers = ("name", "manufacturer__name")
    _attributes = ("network_driver", "system_of_record", "last_synced_from_sor")

    name: str
    manufacturer__name: str
    network_driver: str
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class RoleModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Role."""

    _model = Role
    _modelname = "role"
    _identifiers = ("name",)
    _attributes = (
        "content_types",
        "color",
        "system_of_record",
        "last_synced_from_sor",
    )

    name: str
    color: Optional[str]
    content_types: List[ContentTypeDict] = Field(default_factory=list)
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def _get_queryset(cls, data=None):
        """Get the queryset for the Role model."""
        return cls._model.objects.filter(name=constants.DEFAULT_DEVICE_ROLE)


class DeviceModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Device."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "location__name",
        "location__location_type__name",
        "device_type__manufacturer__name",
        "device_type__model",
        "platform__name",
        "role__name",
        "serial",
        "status__name",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )
    _children = {"interface": "interfaces"}

    name: str
    location__name: Optional[str] = None
    location__location_type__name: Optional[str] = None
    device_type__manufacturer__name: str
    device_type__model: str
    platform__name: Optional[str] = None
    role__name: str
    serial: Optional[str] = ""
    status__name: str
    interfaces: List["InterfaceModel"] = Field(default_factory=list)
    tags: List[TagDict] = Field(default_factory=list)
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @field_validator("device_type__manufacturer__name")
    @classmethod
    def validate_manufacturer(cls, value):
        """Normalize manufacturer name without DB lookup."""
        if value is None:
            return "Unknown"
        name = str(value).strip()
        return name if name else "Unknown"

    @field_validator("device_type__model")
    @classmethod
    def validate_device_type(cls, value, _info):
        """Normalize device type model without DB lookup."""
        if value is None:
            return "Unknown"
        model = str(value).strip()
        return model if model else "Unknown"

    @field_validator("role__name")
    @classmethod
    def validate_role(cls, value):
        """Normalize role name; avoid DB lookup and use default when missing."""
        if value is None:
            return get_default_device_role()
        name = str(value).strip()
        return name if name else get_default_device_role()

    @field_validator("status__name")
    @classmethod
    def validate_status(cls, value):
        """Normalize status name; avoid DB lookup and use default when missing."""
        if value is None:
            return get_default_device_status()
        name = str(value).strip()
        return name if name else get_default_device_status()

    @field_validator("location__name")
    @classmethod
    def validate_location(cls, value):
        """Normalize location name using shared utility."""
        return normalize_location_name(value)

    @field_validator("platform__name")
    @classmethod
    def validate_platform(cls, value, _info):
        """Normalize platform name; avoid DB lookup."""
        if value is None:
            return None
        name = str(value).strip()
        return name if name else None

    @field_validator("serial")
    @classmethod
    def ensure_serial_not_none(cls, value):
        """Ensure serial is never None."""
        return ensure_not_none(value)

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device with info logging and error handling."""
        if adapter.job:
            adapter.job.logger.info("Creating Device: %s", ids["name"])
        try:
            return super().create(adapter, ids, attrs)
        except (ObjectCrudException, ValidationError, ValueError, TypeError) as exception:
            if adapter.job:
                adapter.job.logger.error("Failed to create Device %s: %s", ids["name"], exception)
                adapter.job.logger.debug("Device creation failed with attributes: %s", attrs)
            raise
        except Exception:
            if adapter.job:
                adapter.job.logger.exception("Unexpected error creating Device %s", ids["name"])
            raise

    def update(self, attrs):
        """Override update method to handle devices with broken location references."""
        try:
            # Get the device object using the _model class
            obj = self._model.objects.get(**self.get_identifiers())

            # Check if the device has a broken location reference
            try:
                if hasattr(obj, "location"):
                    _ = obj.location  # Access to trigger potential RelatedObjectDoesNotExist
            except ObjectDoesNotExist:
                # Device has a broken location reference, set to None first
                if hasattr(obj, "location"):
                    obj.location = None
                    obj.validated_save()

        except (LookupError, AttributeError, ValueError, ObjectDoesNotExist):
            # If we can't fix the location, log and continue with normal update
            pass

        # Call the parent update method
        return super().update(attrs)


class InterfaceModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing an Interface."""

    _model = Interface
    _modelname = "interface"
    _identifiers = ("name", "device__name")
    _attributes = (
        "description",
        "enabled",
        "mac_address",
        "mgmt_only",
        "mtu",
        "type",
        "status__name",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )

    device__name: str
    description: Optional[str] = ""
    enabled: bool
    mac_address: Optional[str] = ""
    mgmt_only: bool
    mtu: Optional[int]
    name: str
    type: str
    status__name: str
    tags: List[TagDict] = Field(default_factory=list)
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @field_validator("type")
    @classmethod
    def normalize_interface_type_validator(cls, value):
        """Normalize interface type to match Nautobot choices."""
        return normalize_interface_type(value)

    @field_validator("status__name")
    @classmethod
    def validate_interface_status(cls, value):
        """Validate interface status or use default."""
        if not value:
            return get_default_interface_status()
        try:
            status = get_status(value)
            return status.name
        except (AttributeError, ValueError, LookupError):
            return get_default_interface_status()

    @field_validator("description")
    @classmethod
    def ensure_description_not_none(cls, value):
        """Ensure description is never None."""
        return ensure_not_none(value)

    @field_validator("mac_address")
    @classmethod
    def ensure_mac_address_not_none(cls, value):
        """Ensure MAC address is never None."""
        return ensure_not_none(value)

    @field_validator("mtu")
    @classmethod
    def validate_mtu(cls, value):
        """Validate MTU is reasonable."""
        if value is None:
            return constants.DEFAULT_MTU  # Default MTU
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError:
                return constants.DEFAULT_MTU
        # Ensure MTU is within reasonable range
        if value < constants.MIN_MTU or value > constants.MAX_MTU:
            return constants.DEFAULT_MTU
        return value
