# pylint: disable=R0801
"""Data models for the DiffSync integration."""

from typing import List, Optional

try:
    from typing import Annotated  # Python>=3.9
except ImportError:
    from typing_extensions import Annotated
from diffsync import DiffSyncModel
from diffsync.exceptions import ObjectCrudException
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from nautobot.dcim.models import Device, DeviceType, Interface, Location, Manufacturer, Platform
from nautobot.extras.models import Role
from nautobot.ipam.models import VLAN, VRF, IPAddress, IPAddressToInterface, Namespace, Prefix, VLANGroup
from pydantic import Field, field_validator

from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel
from nautobot_ssot.contrib.typeddicts import ContentTypeDict, TagDict, VRFDict
from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.utils.location_helpers import (
    extract_location_from_vlan_group_name,
    get_or_create_location_for_vlan_group,
    normalize_location_name,
)
from nautobot_ssot.integrations.forward_enterprise.utils.nautobot import (
    ensure_vlan_group_content_type_on_location_type,
    get_default_device_role,
    get_default_device_status,
    get_default_interface_status,
    get_status,
    normalize_interface_type,
)


def ensure_not_none(value, default=""):
    """Utility function to ensure a value is not None, providing a default."""
    return value if value is not None else default


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
    def validate_manufacturer(cls, v):
        """Normalize manufacturer name without DB lookup."""
        if v is None:
            return "Unknown"
        name = str(v).strip()
        return name if name else "Unknown"

    @field_validator("device_type__model")
    @classmethod
    def validate_device_type(cls, v, _info):
        """Normalize device type model without DB lookup."""
        if v is None:
            return "Unknown"
        model = str(v).strip()
        return model if model else "Unknown"

    @field_validator("role__name")
    @classmethod
    def validate_role(cls, v):
        """Normalize role name; avoid DB lookup and use default when missing."""
        if v is None:
            return get_default_device_role()
        name = str(v).strip()
        return name if name else get_default_device_role()

    @field_validator("status__name")
    @classmethod
    def validate_status(cls, v):
        """Normalize status name; avoid DB lookup and use default when missing."""
        if v is None:
            return get_default_device_status()
        name = str(v).strip()
        return name if name else get_default_device_status()

    @field_validator("location__name")
    @classmethod
    def validate_location(cls, v):
        """Normalize location name using shared utility."""
        return normalize_location_name(v)

    @field_validator("platform__name")
    @classmethod
    def validate_platform(cls, v, _info):
        """Normalize platform name; avoid DB lookup."""
        if v is None:
            return None
        name = str(v).strip()
        return name if name else None

    @field_validator("serial")
    @classmethod
    def ensure_serial_not_none(cls, v):
        """Ensure serial is never None."""
        return ensure_not_none(v)

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device with info logging and error handling."""
        if adapter.job:
            adapter.job.logger.info("Creating Device: %s", ids["name"])
        try:
            return super().create(adapter, ids, attrs)
        except (ObjectCrudException, ValidationError, ValueError, TypeError) as e:
            if adapter.job:
                adapter.job.logger.error("Failed to create Device %s: %s", ids["name"], e)
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
    def normalize_interface_type_validator(cls, v):
        """Normalize interface type to match Nautobot choices."""
        return normalize_interface_type(v)

    @field_validator("status__name")
    @classmethod
    def validate_interface_status(cls, v):
        """Validate interface status or use default."""
        if not v:
            return get_default_interface_status()
        try:
            status = get_status(v)
            return status.name
        except (AttributeError, ValueError, LookupError):
            return get_default_interface_status()

    @field_validator("description")
    @classmethod
    def ensure_description_not_none(cls, v):
        """Ensure description is never None."""
        return ensure_not_none(v)

    @field_validator("mac_address")
    @classmethod
    def ensure_mac_address_not_none(cls, v):
        """Ensure MAC address is never None."""
        return ensure_not_none(v)

    @field_validator("mtu")
    @classmethod
    def validate_mtu(cls, v):
        """Validate MTU is reasonable."""
        if v is None:
            return constants.DEFAULT_MTU  # Default MTU
        if isinstance(v, str):
            try:
                v = int(v)
            except ValueError:
                return constants.DEFAULT_MTU
        # Ensure MTU is within reasonable range
        if v < constants.MIN_MTU or v > constants.MAX_MTU:
            return constants.DEFAULT_MTU
        return v


# IPAM Models for Forward Enterprise
class PrefixModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise Prefixes."""

    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name")
    _attributes = ("description", "status__name", "vrfs", "system_of_record")
    _children = {}

    network: str
    prefix_length: int
    namespace__name: str
    description: Optional[str] = ""
    status__name: str = "Active"
    vrfs: List[VRFDict] = Field(default_factory=list)
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None


class IPAddressModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise IP Addresses."""

    _modelname = "ipaddress"
    _identifiers = ("host", "mask_length")
    _attributes = ("status__name", "parent__network", "parent__prefix_length", "system_of_record")
    _children = {}

    host: str
    mask_length: int
    status__name: str = "Active"
    parent__network: str
    parent__prefix_length: int
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None


class IPAssignmentModel(DiffSyncModel):
    """IPAssignment model for Forward Enterprise, mapping IP addresses to interfaces."""

    _modelname = "ipassignment"
    _identifiers = ("interface__device__name", "interface__name", "ip_address__host")
    _attributes = ()

    interface__device__name: str
    interface__name: str
    ip_address__host: str


class VRFModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise VRFs."""

    _modelname = "vrf"
    _identifiers = ("name", "namespace__name")
    _attributes = ("description", "rd", "tenant__name", "system_of_record")
    _children = {}

    name: str
    namespace__name: str
    description: Optional[str] = ""
    rd: Optional[str] = ""
    tenant__name: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None

    @field_validator("name")
    @classmethod
    def validate_vrf_name(cls, v):
        """Validate VRF name is present."""
        if not v:
            raise ValueError("VRF name cannot be empty")
        return v

    @field_validator("namespace__name")
    @classmethod
    def validate_namespace(cls, v):
        """Ensure namespace is set."""
        return v if v else "Global"

    @field_validator("description")
    @classmethod
    def ensure_description_not_none(cls, v):
        """Ensure description is never None."""
        return ensure_not_none(v)

    @field_validator("rd")
    @classmethod
    def ensure_rd_not_none(cls, v):
        """Ensure RD is never None."""
        return ensure_not_none(v)


# Nautobot IPAM Model Classes (for target adapter)


class NautobotVRFModel(NautobotModel):
    """Nautobot VRF model."""

    _model = VRF
    _modelname = "vrf"
    _identifiers = ("name", "namespace__name")
    _attributes = ("rd", "description", "system_of_record", "last_synced_from_sor")

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of VRFs that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    name: str
    namespace__name: str
    description: Optional[str] = ""
    rd: Optional[str] = ""
    tenant__name: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create or update VRF, handling constraint violations gracefully."""
        if adapter.job:
            adapter.job.logger.info("Creating VRF: %s (Namespace: %s)", ids["name"], ids["namespace__name"])
        try:
            # Try to get existing VRF first
            namespace = Namespace.objects.get(name=ids["namespace__name"])
            existing_vrf = VRF.objects.filter(name=ids["name"], namespace=namespace).first()

            if existing_vrf:
                # Update any changed attributes, avoiding constraint violations
                for attr_name, attr_value in attrs.items():
                    if attr_name == "rd" and attr_value:
                        # Check if RD already exists for another VRF
                        rd_exists = VRF.objects.filter(rd=attr_value).exclude(pk=existing_vrf.pk).exists()
                        if not rd_exists:
                            existing_vrf.rd = attr_value
                    elif hasattr(existing_vrf, attr_name.replace("__", ".")):
                        setattr(existing_vrf, attr_name.replace("__", "."), attr_value)

                try:
                    existing_vrf.validated_save()
                except (ValueError, TypeError, AttributeError) as e:
                    if adapter.job:
                        adapter.job.logger.warning("Could not update VRF %s: %s", ids["name"], e)

                # Return DiffSync model instance for the existing VRF
                return cls(adapter=adapter, **ids, **attrs)

            # VRF doesn't exist, create normally with validation
            return super().create(adapter, ids, attrs)

        except (AttributeError, TypeError, ValueError, Namespace.DoesNotExist) as e:
            if adapter.job:
                adapter.job.logger.warning("Error in VRF create method: %s, falling back to default create", e)
            return super().create(adapter, ids, attrs)


class NautobotPrefixModel(NautobotModel):
    """Nautobot Prefix model for creating Prefixes in Nautobot."""

    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name")
    _attributes = (
        "description",
        "vrfs",
        "tenant__name",
        "status__name",
        "system_of_record",
        "last_synced_from_sor",
    )

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of Prefixes that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    network: str
    prefix_length: int
    namespace__name: str
    description: Optional[str] = ""
    vrfs: List[VRFDict] = Field(default_factory=list)
    tenant__name: Optional[str] = None
    status__name: str = "Active"
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):  # pylint: disable=too-many-branches
        """Create prefix with proper VRF assignment handling and graceful duplicate handling."""
        if adapter.job:
            adapter.job.logger.info("Creating Prefix: %s/%s", ids["network"], ids["prefix_length"])
        try:  # pylint: disable=too-many-branches, too-many-nested-blocks
            # Remove vrfs from attrs temporarily to avoid contrib model processing
            vrfs = attrs.pop("vrfs", [])

            # Create the prefix without VRFs first
            new_prefix_obj = super().create(adapter, ids, attrs)

            # Handle VRF assignment manually if VRFs are specified
            # pylint: disable=too-many-nested-blocks
            if vrfs:
                try:
                    # Get the actual Django model instance
                    django_prefix = Prefix.objects.get(
                        network=ids["network"],
                        prefix_length=ids["prefix_length"],
                        namespace__name=ids["namespace__name"],
                    )

                    # Process each VRF string in format "vrf_name__namespace_name"
                    for vrf_str in vrfs:
                        if "__" in vrf_str:
                            vrf_name, vrf_namespace = vrf_str.split("__")
                            try:
                                namespace = Namespace.objects.get(name=vrf_namespace)
                                vrf_obj = VRF.objects.get(name=vrf_name, namespace=namespace)
                                django_prefix.vrfs.add(vrf_obj)
                                if adapter.job:
                                    adapter.job.logger.info(
                                        f"Assigned VRF {vrf_name} to prefix {ids['network']}/{ids['prefix_length']}"
                                    )
                            except (Namespace.DoesNotExist, VRF.DoesNotExist) as e:
                                if adapter.job:
                                    adapter.job.logger.warning(f"Could not assign VRF {vrf_str} to prefix: {e}")
                        else:
                            if adapter.job:
                                adapter.job.logger.warning(
                                    f"Invalid VRF format: {vrf_str}, expected 'vrf_name__namespace_name'"
                                )

                except (KeyError, AttributeError, TypeError, ValueError) as e:
                    if adapter.job:
                        adapter.job.logger.warning(f"Error assigning VRFs to prefix: {e}")

            return new_prefix_obj

        except ObjectCrudException as e:
            # Check if this is a duplicate prefix error
            error_msg = str(e).lower()
            if "prefix" in error_msg and "already exists" in error_msg:
                # Prefix already exists, which is normal in sync scenarios
                # Return None to indicate no object was created (this is normal for DiffSync)
                return None

            # Re-raise if it's a different error
            raise
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            if adapter.job:
                adapter.job.logger.warning(f"Error in prefix create method: {e}, falling back to default create")
            return super().create(adapter, ids, attrs)


class NautobotIPAddressModel(NautobotModel):
    """Nautobot IPAddress model for creating IP addresses in Nautobot."""

    _model = IPAddress
    _modelname = "ipaddress"
    _identifiers = ("host", "mask_length")
    _attributes = (
        "description",
        "status__name",
        "role",
        "dns_name",
        "tenant__name",
        "parent__network",
        "parent__prefix_length",
        "system_of_record",
        "last_synced_from_sor",
    )

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of IP Addresses that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    host: str
    mask_length: int
    description: Optional[str] = ""
    status__name: str = "Active"
    role: Optional[str] = None
    dns_name: Optional[str] = ""
    tenant__name: Optional[str] = None
    parent__network: str
    parent__prefix_length: int
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IP address with graceful duplicate handling."""
        if adapter.job:
            adapter.job.logger.info("Creating IP Address: %s/%s", ids["host"], ids["mask_length"])
        try:
            # Try to create the IP address normally
            return super().create(adapter, ids, attrs)
        except ObjectCrudException as e:
            # Check if this is a duplicate IP address error
            error_msg = str(e).lower()
            if "ip address" in error_msg and "already exists" in error_msg:
                # IP address already exists, which is normal in sync scenarios
                # Return None to indicate no object was created (this is normal for DiffSync)
                return None

            # Re-raise if it's a different error
            raise
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            if adapter.job:
                adapter.job.logger.warning(f"Error in IP address create method: {e}, falling back to default create")
            return super().create(adapter, ids, attrs)


class NautobotIPAssignmentModel(NautobotModel):
    """Nautobot IPAddressToInterface model for assigning IPs to interfaces."""

    _model = IPAddressToInterface
    _modelname = "ipassignment"
    _identifiers = ("interface__device__name", "interface__name", "ip_address__host")
    _attributes = ()

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of IP assignments with Forward Enterprise system of record."""
        # Filter by IP addresses that belong to Forward Enterprise
        return cls._model.objects.filter(ip_address___custom_field_data__system_of_record="Forward Enterprise")

    interface__device__name: str
    interface__name: str
    ip_address__host: str

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface assignment with graceful duplicate handling.

        Args:
            adapter: The DiffSync adapter
            ids: Dictionary of identifier values
            attrs: Dictionary of attribute values

        Returns:
            Created model instance or None if duplicate exists
        """
        try:
            return super().create(adapter, ids, attrs)
        except ObjectCrudException as e:
            if "already exists" in str(e).lower():
                # IP assignment already exists, return None silently
                # Return None to indicate no object was created (this is normal for DiffSync)
                return None

            # Re-raise if it's a different error
            raise
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            if adapter.job:
                adapter.job.logger.warning(f"Error in IP assignment create method: {e}, falling back to default create")
            return super().create(adapter, ids, attrs)


# VLAN Models for Forward Enterprise


class VLANModel(DiffSyncModel):
    """DiffSync model for Forward Enterprise VLANs."""

    _modelname = "vlan"
    _identifiers = ("vid", "name", "vlan_group__name")
    _attributes = ("description", "status__name", "tenant__name", "role", "system_of_record")
    _children = {}

    vid: int
    name: str
    vlan_group__name: str
    description: Optional[str] = ""
    status__name: str = "Active"
    tenant__name: Optional[str] = None
    role: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None

    @field_validator("vid")
    @classmethod
    def validate_vid(cls, v):
        """Validate VLAN ID is within valid range."""
        if not isinstance(v, int) or v < constants.MIN_VLAN_ID or v > constants.MAX_VLAN_ID:
            raise ValueError(f"VLAN ID must be between {constants.MIN_VLAN_ID} and {constants.MAX_VLAN_ID}, got {v}")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Ensure VLAN name is present."""
        if not v or not v.strip():
            raise ValueError("VLAN name cannot be empty")
        return v.strip()


class NautobotVLANModel(NautobotModel):
    """Nautobot VLAN model for creating VLANs in Nautobot."""

    _model = VLAN
    _modelname = "vlan"
    _identifiers = ("vid", "name", "vlan_group__name")
    _attributes = (
        "description",
        "status__name",
        "tenant__name",
        "role",
        "system_of_record",
        "last_synced_from_sor",
    )

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of VLANs that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    vid: int
    name: str
    vlan_group__name: str = constants.DEFAULT_VLAN_GROUP_NAME
    description: Optional[str] = ""
    status__name: str = "Active"
    tenant__name: Optional[str] = None
    role: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements, too-many-nested-blocks
        """Create VLAN with proper VLAN group handling."""
        if adapter.job:
            adapter.job.logger.info("Creating VLAN: %s (VID: %s)", ids["name"], ids["vid"])
        try:
            # Ensure VLAN groups are allowed content types on Site location type,
            ensure_vlan_group_content_type_on_location_type("Site")

            # Get VLAN group name
            vlan_group_name = ids.get("vlan_group__name", "Forward Enterprise")

            # Extract location name from VLAN group name and get/create location
            location_name = extract_location_from_vlan_group_name(vlan_group_name)
            location, _ = get_or_create_location_for_vlan_group(location_name, adapter.job)

            # Get or create VLAN group for Forward Enterprise
            vlan_group_defaults = {"description": f"VLANs imported from Forward Enterprise for {vlan_group_name}"}
            if location:
                vlan_group_defaults["location"] = location

            vlan_group, created = VLANGroup.objects.get_or_create(
                name=vlan_group_name,
                defaults=vlan_group_defaults,
            )

            if created and adapter.job:
                adapter.job.logger.info(
                    f"Created VLAN group: {vlan_group_name} at location: {location_name if location else 'Unknown'}"
                )

            # Remove vlan_group__name from attrs as we'll set it directly
            attrs_copy = attrs.copy()
            attrs_copy.pop("vlan_group__name", None)

            # Create the VLAN with proper duplicate handling
            try:
                new_vlan_obj = super().create(adapter, ids, attrs_copy)
            except ObjectCrudException as e:
                # Check if this is a duplicate VLAN error
                error_msg = str(e).lower()
                if "vlan with this" in error_msg and "already exists" in error_msg:
                    # Return None to indicate no object was created (this is normal for DiffSync)
                    return None

                # Re-raise if it's a different error
                raise

            # Set the VLAN group on the actual Django model
            if new_vlan_obj:
                try:
                    new_vlan = VLAN.objects.get(vid=ids["vid"], name=ids["name"], vlan_group=vlan_group)
                    new_vlan.vlan_group = vlan_group
                    new_vlan.validated_save()
                except VLAN.DoesNotExist:
                    if adapter.job:
                        adapter.job.logger.warning(
                            f"Could not set VLAN group for VLAN {ids['vid']} in group {vlan_group_name}"
                        )

            return new_vlan_obj

        except (KeyError, AttributeError, TypeError, ValueError) as e:
            if adapter.job:
                adapter.job.logger.warning(f"Error in VLAN create method: {e}, falling back to default create")
            return super().create(adapter, ids, attrs)
