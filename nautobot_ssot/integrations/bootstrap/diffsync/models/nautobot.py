"""Nautobot DiffSync models for bootstrap SSoT."""

import os
from datetime import datetime

import pytz
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from nautobot.circuits.models import Circuit as ORMCircuit
from nautobot.circuits.models import CircuitTermination as ORMCircuitTermination
from nautobot.circuits.models import CircuitType as ORMCircuitType
from nautobot.circuits.models import Provider as ORMProvider
from nautobot.circuits.models import ProviderNetwork as ORMProviderNetwork
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType as ORMDeviceType
from nautobot.dcim.models import InventoryItem as ORMInventoryItem
from nautobot.dcim.models import Location as ORMLocation
from nautobot.dcim.models import LocationType as ORMLocationType
from nautobot.dcim.models import Manufacturer as ORMManufacturer
from nautobot.dcim.models import Platform as ORMPlatform
from nautobot.extras.models import ComputedField as ORMComputedField
from nautobot.extras.models import Contact as ORMContact
from nautobot.extras.models import CustomField as ORMCustomField
from nautobot.extras.models import CustomFieldChoice as ORMCustomFieldChoice
from nautobot.extras.models import DynamicGroup as ORMDynamicGroup
from nautobot.extras.models import ExternalIntegration as ORMExternalIntegration
from nautobot.extras.models import GitRepository as ORMGitRepository
from nautobot.extras.models import GraphQLQuery as ORMGraphQLQuery
from nautobot.extras.models import Job as ORMJob
from nautobot.extras.models import Role as ORMRole
from nautobot.extras.models import ScheduledJob as ORMScheduledJob
from nautobot.extras.models import Secret as ORMSecret
from nautobot.extras.models import SecretsGroup as ORMSecretsGroup
from nautobot.extras.models import SecretsGroupAssociation as ORMSecretsGroupAssociation
from nautobot.extras.models import Status as ORMStatus
from nautobot.extras.models import Tag as ORMTag
from nautobot.extras.models import Team as ORMTeam
from nautobot.ipam.models import RIR as ORMRiR
from nautobot.ipam.models import VLAN as ORMVLAN
from nautobot.ipam.models import VRF as ORMVRF
from nautobot.ipam.models import Namespace as ORMNamespace
from nautobot.ipam.models import Prefix as ORMPrefix
from nautobot.ipam.models import VLANGroup as ORMVLANGroup
from nautobot.tenancy.models import Tenant as ORMTenant
from nautobot.tenancy.models import TenantGroup as ORMTenantGroup
from nautobot.users.models import User as ORMUser

try:
    from nautobot.extras.models.metadata import ObjectMetadata  # noqa: F401

    from nautobot_ssot.integrations.bootstrap.constants import SCOPED_FIELDS_MAPPING
    from nautobot_ssot.integrations.metadata_utils import add_or_update_metadata_on_object

    METADATA_FOUND = True
except (ImportError, RuntimeError):
    METADATA_FOUND = False

from nautobot_ssot.integrations.bootstrap.diffsync.models.base import (
    VLAN,
    VRF,
    Circuit,
    CircuitTermination,
    CircuitType,
    ComputedField,
    Contact,
    CustomField,
    DynamicGroup,
    ExternalIntegration,
    GitRepository,
    GraphQLQuery,
    Location,
    LocationType,
    Manufacturer,
    Namespace,
    Platform,
    Prefix,
    Provider,
    ProviderNetwork,
    RiR,
    Role,
    ScheduledJob,
    Secret,
    SecretsGroup,
    Tag,
    Team,
    Tenant,
    TenantGroup,
    VLANGroup,
)
from nautobot_ssot.integrations.bootstrap.utils import (
    # lookup_contact_for_team,
    check_sor_field,
    lookup_content_type_for_taggable_model_path,
    lookup_content_type_id,
    lookup_team_for_contact,
)
from nautobot_ssot.utils import (
    core_supports_softwareversion,
    dlm_supports_softwarelcm,
    validate_dlm_installed,
)

if core_supports_softwareversion():
    from nautobot.dcim.models import SoftwareImageFile as ORMSoftwareImage
    from nautobot.dcim.models import SoftwareVersion as ORMSoftware

    from nautobot_ssot.integrations.bootstrap.diffsync.models.base import SoftwareImageFile, SoftwareVersion

    _Software_Base_Class = SoftwareVersion
    _SoftwareImage_Base_Class = SoftwareImageFile

if dlm_supports_softwarelcm():
    from nautobot_device_lifecycle_mgmt.models import (
        SoftwareImageLCM as ORMSoftwareImage,
    )
    from nautobot_device_lifecycle_mgmt.models import (
        SoftwareLCM as ORMSoftware,
    )

    from nautobot_ssot.integrations.bootstrap.diffsync.models.base import Software, SoftwareImage

    _Software_Base_Class = Software
    _SoftwareImage_Base_Class = SoftwareImage

if validate_dlm_installed():
    from nautobot_device_lifecycle_mgmt.models import (
        ValidatedSoftwareLCM as ORMValidatedSoftware,
    )

    from nautobot_ssot.integrations.bootstrap.diffsync.models.base import ValidatedSoftware


class NautobotTenantGroup(TenantGroup):
    """Nautobot implementation of Bootstrap TenantGroup model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create TenantGroup in Nautobot from NautobotTenantGroup object."""
        _parent = None
        if ids["parent"]:
            _parent = ORMTenantGroup.objects.get(name=ids["parent"])
        adapter.job.logger.info(f"Creating Nautobot TenantGroup: {ids['name']}")
        if _parent is not None:
            new_tenant_group = ORMTenantGroup(name=ids["name"], parent=_parent, description=attrs["description"])
        else:
            new_tenant_group = ORMTenantGroup(name=ids["name"], description=attrs["description"])
        new_tenant_group.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_tenant_group.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_tenant_group.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_tenant_group, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update TenantGroup in Nautobot from NautobotTenantGroup object."""
        self.adapter.job.logger.debug(f"Updating TenantGroup {self.name} with {attrs}")
        _update_tenant_group = ORMTenantGroup.objects.get(name=self.name)
        if "description" in attrs:
            _update_tenant_group.description = attrs["description"]
        if not check_sor_field(_update_tenant_group):
            _update_tenant_group.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_tenant_group.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_tenant_group.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_tenant_group,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete TenantGroup in Nautobot from NautobotTenantGroup object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete TenantGroup: {self} - {self.uuid}")
            _nb_tenant_group = ORMTenantGroup.objects.get(id=self.uuid)
            super().delete()
            _nb_tenant_group.delete()
            return self
        except ORMTenantGroup.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find TenantGroup {self.uuid} for deletion. {err}")


class NautobotTenant(Tenant):
    """Nautobot implementation of Bootstrap Tenant model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Tenant in Nautobot from NautobotTenant object."""
        _tags = []
        _tenant_group = None
        _description = ""
        if "tags" in attrs:
            for _tag in attrs["tags"]:
                _tags.append(ORMTag.objects.get(name=_tag))
        if "tenant_group" in attrs:
            try:
                _tenant_group = ORMTenantGroup.objects.get(name=attrs["tenant_group"])
            except ORMTenantGroup.DoesNotExist:
                adapter.job.logger.warning(
                    f"Could not find TenantGroup {attrs['tenant_group']} to assign to {ids['name']}"
                )
        if "description" in attrs:
            _description = attrs["description"]
        adapter.job.logger.info(f"Creating Nautobot Tenant: {ids['name']}")
        new_tenant = ORMTenant(
            name=ids["name"],
            tenant_group=_tenant_group,
            tags=_tags,
            description=_description,
        )
        new_tenant.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_tenant.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_tenant.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_tenant, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Tenant in Nautobot from NautobotTenant object."""
        _update_tenant = ORMTenant.objects.get(name=self.name)
        if "description" in attrs:
            _update_tenant.description = attrs["description"]
        if "tenant_group" in attrs:
            try:
                _update_tenant.tenant_group = ORMTenantGroup.objects.get(name=attrs["tenant_group"])
            except ORMTenantGroup.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Could not find TenantGroup {attrs['tenant_group']} to assign to {self.name}"
                )
        if "tags" in attrs:
            # FIXME: There might be a better way to handle this that's easier on the database.
            _update_tenant.tags.clear()
            for _tag in attrs["tags"]:
                _update_tenant.tags.add(_tag)
        if not check_sor_field(_update_tenant):
            _update_tenant.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_tenant.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_tenant.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_tenant, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Tenant in Nautobot from NautobotTenant object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Tenant: {self} - {self.uuid}")
            _nb_tenant = ORMTenant.objects.get(id=self.uuid)
            super().delete()
            _nb_tenant.delete()
            return self
        except ORMTenant.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Tenant {self.uuid} for deletion. {err}")


class NautobotRole(Role):
    """Nautobot implementation of Bootstrap Role model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Role in Nautobot from NautobotRole object."""
        _content_types = []
        adapter.job.logger.info(f"Creating Nautobot Role: {ids['name']}")
        for _model in attrs["content_types"]:
            try:
                _content_types.append(lookup_content_type_for_taggable_model_path(_model))
            except ContentType.DoesNotExist:
                adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
        _new_role = ORMRole(
            name=ids["name"],
            weight=attrs["weight"],
            description=attrs["description"],
            color=attrs.get("color", "#999999"),
        )
        _new_role.validated_save()
        _new_role.content_types.set(_content_types)
        _new_role.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_role.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_role.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_role, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Role in Nautobot from NautobotRole object."""
        _content_types = []
        self.adapter.job.logger.info(f"Updating Role {self.name}")
        _update_role = ORMRole.objects.get(name=self.name)
        if "weight" in attrs:
            _update_role.weight = attrs["weight"]
        if "description" in attrs:
            _update_role.description = attrs["description"]
        if "color" in attrs:
            _update_role.color = attrs["color"]
        if "content_types" in attrs:
            for _model in attrs["content_types"]:
                self.adapter.job.logger.debug(f"Looking up {_model} in content types.")
                try:
                    _content_types.append(lookup_content_type_for_taggable_model_path(_model))
                except ContentType.DoesNotExist:
                    self.adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
            _update_role.content_types.set(_content_types)
        if not check_sor_field(_update_role):
            _update_role.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_role.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_role.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_role, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Role in Nautobot from NautobotRole object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Role: {self} - {self.uuid}")
            _role = ORMRole.objects.get(id=self.uuid)
            _role.delete()
            super().delete()
            return self
        except ORMTenant.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Role {self.uuid} for deletion. {err}")


class NautobotManufacturer(Manufacturer):
    """Nautobot implementation of Bootstrap Manufacturer model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Manufacturer in Nautobot from NautobotManufacturer object."""
        adapter.job.logger.debug(f"Creating Nautobot Manufacturer {ids['name']}")
        _new_manufacturer = ORMManufacturer(name=ids["name"], description=attrs["description"])
        _new_manufacturer.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_manufacturer.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_manufacturer.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_manufacturer, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Manufacturer in Nautobot from NautobotManufacturer object."""
        _update_manufacturer = ORMManufacturer.objects.get(name=self.name)
        self.adapter.job.logger.info(f"Updating Manufacturer {self.name}")
        if "description" in attrs:
            _update_manufacturer.description = attrs["description"]
        if not check_sor_field(_update_manufacturer):
            _update_manufacturer.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_manufacturer.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_manufacturer.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_manufacturer,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Manufacturer in Nautobot from NautobotManufacturer object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Manufacturer: {self} - {self.uuid}")
            _manufacturer = ORMManufacturer.objects.get(id=self.uuid)
            _manufacturer.delete()
            super().delete()
            return self
        except ORMManufacturer.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Manufacturer {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete Manufacturer {self.name}, as it is referenced by another object. {err}"
            )


class NautobotPlatform(Platform):
    """Nautobot implementation of Bootstrap Platform model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Platform in Nautobot from NautobotPlatform object."""
        adapter.job.logger.info(f"Creating Nautobot Platform {ids['name']}")
        try:
            _manufacturer = None
            if ids["manufacturer"]:
                _manufacturer = ORMManufacturer.objects.get(name=ids["manufacturer"])
            _new_platform = ORMPlatform(
                name=ids["name"],
                manufacturer=_manufacturer,
                network_driver=attrs["network_driver"],
                napalm_driver=attrs["napalm_driver"],
                napalm_args=attrs["napalm_arguments"],
                description=attrs["description"],
            )
            _new_platform.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
            _new_platform.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
            _new_platform.validated_save()
            if METADATA_FOUND:
                metadata = add_or_update_metadata_on_object(
                    adapter=adapter, obj=_new_platform, scoped_fields=SCOPED_FIELDS_MAPPING
                )
                metadata.validated_save()
        except ORMManufacturer.DoesNotExist:
            adapter.job.logger.warning(
                f"Manufacturer {ids['manufacturer']} does not exist in Nautobot, be sure to create it."
            )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Platform in Nautobot from NautobotPlatform object."""
        _update_platform = ORMPlatform.objects.get(name=self.name)
        if "network_driver" in attrs:
            _update_platform.network_driver = attrs["network_driver"]
        if "napalm_driver" in attrs:
            _update_platform.napalm_driver = attrs["napalm_driver"]
        if "napalm_arguments" in attrs:
            _update_platform.napalm_args = attrs["napalm_arguments"]
        if "description" in attrs:
            _update_platform.description = attrs["description"]
        _update_platform.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        if not check_sor_field(_update_platform):
            _update_platform.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_platform.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_platform, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Platform in Nautobot from NautobotPlatform object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Platform: {self} - {self.uuid}")
            _platform = ORMPlatform.objects.get(id=self.uuid)
            _platform.delete()
            super().delete()
            return self
        except ORMManufacturer.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Platform {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete Platform {self.name}, as it is referenced by another object. {err}"
            )


class NautobotLocationType(LocationType):
    """Nautobot implementation of Bootstrap LocationType model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create LocationType in Nautobot from NautobotLocationType object."""
        _content_types = []
        adapter.job.logger.info(f"Creating Nautobot LocationType: {ids['name']}")
        _parent = None
        for _model in attrs["content_types"]:
            try:
                _content_types.append(lookup_content_type_for_taggable_model_path(_model))
            except ContentType.DoesNotExist:
                adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
        if "parent" in attrs and attrs["parent"]:
            try:
                _parent = ORMLocationType.objects.get(name=attrs["parent"])
            except ORMLocationType.DoesNotExist:
                adapter.job.logger.warning(
                    f"Could not find LocationType {attrs['parent']} in Nautobot, ensure it exists."
                )
        _new_location_type = ORMLocationType(
            name=ids["name"],
            parent=_parent,
            nestable=attrs["nestable"] if not None else False,
            description=attrs["description"],
        )
        _new_location_type.validated_save()
        for _model in attrs["content_types"]:
            adapter.job.logger.debug(f"Looking up {_model} in content types.")
            try:
                _content_types.append(lookup_content_type_for_taggable_model_path(_model))
            except ContentType.DoesNotExist:
                adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
        _new_location_type.content_types.set(_content_types)
        _new_location_type.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_location_type.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_location_type.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_location_type, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update LocationType in Nautobot from NautobotLocationType object."""
        _content_types = []
        self.adapter.job.logger.info(f"Updating LocationType {self.name}")
        _update_location_type = ORMLocationType.objects.get(id=self.uuid)
        if "parent" in attrs:
            try:
                _parent = ORMLocationType.objects.get(name=attrs["parent"])
                _update_location_type.parent = _parent
            except ORMLocationType.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Parent LocationType {attrs['parent']} does not exist, ensure it exists first."
                )
        if "nestable" in attrs:
            _update_location_type.nestable = attrs["nestable"]
        if "description" in attrs:
            _update_location_type.description = attrs["description"]
        if "content_types" in attrs:
            for _model in attrs["content_types"]:
                self.adapter.job.logger.debug(f"Looking up {_model} in content types.")
                try:
                    _content_types.append(lookup_content_type_for_taggable_model_path(_model))
                except ContentType.DoesNotExist:
                    self.adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
            _update_location_type.content_types.set(_content_types)
        if not check_sor_field(_update_location_type):
            _update_location_type.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_location_type.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_location_type.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_location_type,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete LocationType in Nautobot from NautobotLocationType object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete LocationType: {self} - {self.uuid}")
            _location_type = ORMLocationType.objects.get(id=self.uuid)
            _location_type.delete()
            super().delete()
            return self
        except ORMLocationType.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find LocationType {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete LocationType {self.name}, as it is referenced by another object. {err}"
            )


class NautobotLocation(Location):
    """Nautobot implementation of Bootstrap Location model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Location in Nautobot from NautobotLocation object."""
        adapter.job.logger.info(f"Creating Nautobot Location {ids['name']}")

        try:
            _parent = None
            _tenant = None
            _timezone = None
            _tags = []
            _location_type = ORMLocationType.objects.get(name=ids["location_type"])
            _status = ORMStatus.objects.get(name=attrs["status"])
            if "parent" in attrs:
                if attrs["parent"]:
                    _parent = ORMLocation.objects.get(name=attrs["parent"])
            if "tenant" in attrs:
                if attrs["tenant"]:
                    _tenant = Tenant.objects.get(name=attrs["tenant"])
            if "time_zone" in attrs:
                _timezone = None
                if attrs["time_zone"] and attrs["time_zone"] != "":
                    _timezone = pytz.timezone(attrs["time_zone"])
            for _tag in attrs["tags"]:
                _tags.append(ORMTag.objects.get(name=_tag))
            _new_location = ORMLocation(
                name=ids["name"],
                location_type=_location_type,
                parent=_parent if not None else None,
                status=_status,
                facility=attrs["facility"],
                asn=attrs["asn"],
                time_zone=_timezone,
                description=attrs["description"],
                tenant=_tenant,
                physical_address=attrs["physical_address"],
                shipping_address=attrs["shipping_address"],
                latitude=attrs["latitude"],
                longitude=attrs["longitude"],
                contact_name=attrs["contact_name"],
                contact_phone=attrs["contact_phone"],
                contact_email=attrs["contact_email"],
                tags=_tags,
            )
            _new_location.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
            _new_location.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
            _new_location.validated_save()
            if METADATA_FOUND:
                metadata = add_or_update_metadata_on_object(
                    adapter=adapter, obj=_new_location, scoped_fields=SCOPED_FIELDS_MAPPING
                )
                metadata.validated_save()
        except ORMStatus.DoesNotExist:
            adapter.job.logger.warning(f"Status {attrs['status']} could not be found. Make sure it exists.")
        except ORMLocationType.DoesNotExist:
            adapter.job.logger.warning(
                f"LocationType {attrs['location_type']} could not be found. Make sure it exists."
            )
        except ORMTenant.DoesNotExist:
            adapter.job.logger.warning(f"Tenant {attrs['tenant']} does not exist, verify it is created.")
        except pytz.UnknownTimeZoneError:
            adapter.job.logger.warning(
                f"Timezone {attrs['time_zone']} could not be found. Verify the timezone is a valid timezone."
            )
        except ORMLocation.DoesNotExist:
            adapter.job.logger.warning(f"Parent Location {attrs['parent']} does not exist, ensure it exists first.")
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Location in Nautobot from NautobotLocation object."""
        self.adapter.job.logger.info(f"Updating Location {self.name}.")
        _parent = None
        _tenant = None
        _timezone = None
        _location_type = ORMLocationType.objects.get(name=self.location_type)
        _update_location = ORMLocation.objects.get(name=self.name, location_type=_location_type)
        if "parent" in attrs:
            if attrs["parent"]:
                _parent = ORMLocation.objects.get(name=attrs["parent"])
                _update_location.parent = _parent
        if "status" in attrs:
            _status = ORMStatus.objects.get(name=attrs["status"])
            _update_location.status = _status
        if "facility" in attrs:
            _update_location.facility = attrs["facility"]
        if "asn" in attrs:
            _update_location.asn = attrs["asn"]
        if "time_zone" in attrs:
            _timezone = None
            if attrs["time_zone"] and attrs["time_zone"] != "":
                _timezone = pytz.timezone(attrs["time_zone"])
                _update_location.time_zone = _timezone
        if "description" in attrs:
            _update_location.description = attrs["description"]
        if "tenant" in attrs:
            _tenant = Tenant.objects.get(name=attrs["tenant"])
            _update_location.tenant = _tenant
        if "physical_address" in attrs:
            _update_location.physical_address = attrs["physical_address"]
        if "shipping_address" in attrs:
            _update_location.shipping_address = attrs["shipping_address"]
        if "latitude" in attrs:
            _update_location.latitude = attrs["latitude"]
        if "longitude" in attrs:
            _update_location.longitude = attrs["longitude"]
        if "contact_name" in attrs:
            _update_location.contact_name = attrs["contact_name"]
        if "contact_phone" in attrs:
            _update_location.contact_name = attrs["contact_phone"]
        if "contact_email" in attrs:
            _update_location.contact_name = attrs["contact_email"]
        if "tags" in attrs:
            _tags = []
            for _tag in attrs["tags"]:
                _tags.append(ORMTag.get(name=_tag))
            _update_location.tags.clear()
            for _tag in _tags:
                _update_location.tags.add(_tag)
        if not check_sor_field(_update_location):
            _update_location.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_location.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_location.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_location, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Location in Nautobot from NautobotLocation object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Location: {self} - {self.uuid}")
            _location = ORMLocation.objects.get(id=self.uuid)
            _location.delete()
            super().delete()
            return self
        except ORMLocation.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Location {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete Location {self.name}, as it is referenced by another object. {err}"
            )


class NautobotTeam(Team):
    """Nautobot implementation of Team DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Team in Nautobot from NautobotTeam object."""
        adapter.job.logger.debug(f"Creating Nautobot Team {ids['name']}")
        _new_team = ORMTeam(
            name=ids["name"],
            phone=attrs["phone"],
            email=attrs["email"],
            address=attrs["address"],
        )
        _new_team.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_team.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_team.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_team, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        # TODO: Need to consider how to allow loading from teams or contacts models.
        # if "contacts" in attrs:
        #     # FIXME: There might be a better way to handle this that's easier on the database.
        #     _new_team.contacts.clear()
        #     for _contact in attrs["contacts"]:
        #         adapter.job.logger.debug(f'Looking up Contact: {_contact} for Team: {ids["name"]}.')
        #         _new_team.contact.add(lookup_contact_for_team(contact=_contact))
        #     _new_team.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Team in Nautobot from NautobotTeam object."""
        _update_team = ORMTeam.objects.get(name=self.name)
        self.adapter.job.logger.info(f"Updating Team {self.name}")
        if "phone" in attrs:
            _update_team.phone = attrs["phone"]
        if "email" in attrs:
            _update_team.email = attrs["email"]
        if "address" in attrs:
            _update_team.address = attrs["address"]
        # TODO: Need to consider how to allow loading from teams or contacts models.
        # if "contacts" in attrs:
        #     # FIXME: There might be a better way to handle this that's easier on the database.
        #     _update_team.contacts.clear()
        #     for _contact in attrs["contacts"]:
        #         self.adapter.job.logger.debug(f"Looking up Contact: {_contact} for Team: {self.name}.")
        #         _update_team.contacts.add(lookup_contact_for_team(contact=_contact))
        if not check_sor_field(_update_team):
            _update_team.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_team.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_team.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_team, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Team in Nautobot from NautobotTeam object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Team: {self} - {self.uuid}")
            _team = ORMTeam.objects.get(id=self.uuid)
            _team.delete()
            super().delete()
            return self
        except ORMTeam.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Team {self.uuid} for deletion. {err}")


class NautobotContact(Contact):
    """Nautobot implementation of Contact DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Contact in Nautobot from NautobotContact object."""
        adapter.job.logger.debug(f"Creating Nautobot Contact {ids['name']}")
        _new_contact = ORMContact(
            name=ids["name"],
            phone=attrs["phone"],
            email=attrs["email"],
            address=attrs["address"],
        )
        _new_contact.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_contact.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_contact.validated_save()
        if "teams" in attrs:
            for _team in attrs["teams"]:
                adapter.job.logger.debug(f"Looking up Team: {_team} for Contact: {ids['name']}.")
                _new_contact.teams.add(lookup_team_for_contact(team=_team))
            _new_contact.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_contact, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Contact in Nautobot from NautobotContact object."""
        _update_contact = ORMContact.objects.get(name=self.name)
        self.adapter.job.logger.info(f"Updating Contact {self.name}")
        if "phone" in attrs:
            _update_contact.phone = attrs["phone"]
        if "email" in attrs:
            _update_contact.email = attrs["email"]
        if "address" in attrs:
            _update_contact.address = attrs["address"]
        if "teams" in attrs:
            # FIXME: There might be a better way to handle this that's easier on the database.
            _update_contact.teams.clear()
            for _team in attrs["teams"]:
                self.adapter.job.logger.debug(f"Looking up Team: {_team} for Contact: {self.name}.")
                _update_contact.teams.add(lookup_team_for_contact(team=_team))
        if not check_sor_field(_update_contact):
            _update_contact.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_contact.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_contact.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_contact, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Contact in Nautobot from NautobotContact object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Team: {self} - {self.uuid}")
            _contact = ORMContact.objects.get(id=self.uuid)
            _contact.delete()
            super().delete()
            return self
        except ORMTenant.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Contact {self.uuid} for deletion. {err}")


class NautobotProvider(Provider):
    """Nautobot implementation of Provider DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Provider in Nautobot from NautobotProvider object."""
        adapter.job.logger.info(f"Creating Nautobot Provider: {ids['name']}")
        if "tags" in attrs:
            _tags = []
            for _tag in attrs["tags"]:
                _tags.append(ORMTag.get(name=_tag))
        _new_provider = ORMProvider(
            name=ids["name"],
            asn=attrs["asn"],
            account=attrs["account_number"],
            portal_url=attrs["portal_url"],
            noc_contact=attrs["noc_contact"],
            admin_contact=attrs["admin_contact"],
        )
        for _tag in attrs["tags"]:
            try:
                _new_provider.tags.add(ORMTag.objects.get(name=_tag))
            except ORMTag.DoesNotExist:
                adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        _new_provider.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_provider.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_provider.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_provider, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Provider in Nautobot from NautobotProvider object."""
        self.adapter.job.logger.debug(f"Updating Nautobot Provider {self.name}")
        _update_provider = ORMProvider.objects.get(id=self.uuid)
        if "asn" in attrs:
            _update_provider.asn = attrs["asn"]
        if "account_number" in attrs:
            _update_provider.account = attrs["account_number"]
        if "portal_url" in attrs:
            _update_provider.portal_url = attrs["portal_url"]
        if "noc_contact" in attrs:
            _update_provider.noc_contact = attrs["noc_contact"]
        if "admin_contact" in attrs:
            _update_provider.admin_contact = attrs["admin_contact"]
        if "tags" in attrs:
            # FIXME: There might be a better way to handle this that's easier on the database.
            _update_provider.tags.clear()
            for _tag in attrs["tags"]:
                try:
                    _update_provider.tags.add(ORMTag.objects.get(name=_tag))
                except ORMTag.DoesNotExist:
                    self.adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        if not check_sor_field(_update_provider):
            _update_provider.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_provider.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_provider.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_provider, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Provider in Nautobot from NautobotProvider object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Provider: {self} - {self.uuid}")
            _nb_provider = ORMProvider.objects.get(id=self.uuid)
            _nb_provider.delete()
            super().delete()
            return self
        except ORMProvider.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Provider {self.uuid} for deletion. {err}")


class NautobotProviderNetwork(ProviderNetwork):
    """Nautobot implementation of ProviderNetwork DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create ProviderNetwork in Nautobot from NautobotProviderNetwork object."""
        adapter.job.logger.info(f"Creating Nautobot ProviderNetwork: {ids['name']}")
        if "tags" in attrs:
            _tags = []
            for _tag in attrs["tags"]:
                _tags.append(ORMTag.get(name=_tag))
        _new_provider_network = ORMProviderNetwork(
            name=ids["name"],
            provider=ORMProvider.objects.get(name=ids["provider"]),
            description=attrs["description"],
            comments=attrs["comments"],
        )
        for _tag in attrs["tags"]:
            try:
                _new_provider_network.tags.add(ORMTag.objects.get(name=_tag))
            except ORMTag.DoesNotExist:
                adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        _new_provider_network.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_provider_network.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_provider_network.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_provider_network, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ProviderNetwork in Nautobot from NautobotProviderNetwork object."""
        self.adapter.job.logger.debug(f"Updating Nautobot ProviderNetwork {self.name}")
        _update_provider_network = ORMProviderNetwork.objects.get(id=self.uuid)
        if "description" in attrs:
            _update_provider_network.description = attrs["description"]
        if "comments" in attrs:
            _update_provider_network.comments = attrs["comments"]
        if "tags" in attrs:
            # FIXME: There might be a better way to handle this that's easier on the database.
            _update_provider_network.tags.clear()
            for _tag in attrs["tags"]:
                try:
                    _update_provider_network.tags.add(ORMTag.objects.get(name=_tag))
                except ORMTag.DoesNotExist:
                    self.adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        _update_provider_network.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        if not check_sor_field(_update_provider_network):
            _update_provider_network.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_provider_network.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_provider_network,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete ProviderNetwork in Nautobot from NautobotProviderNetwork object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete ProviderNetwork: {self} - {self.uuid}")
            _nb_provider_network = ORMProviderNetwork.objects.get(id=self.uuid)
            _nb_provider_network.delete()
            super().delete()
            return self
        except ORMProviderNetwork.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find ProviderNetwork {self.uuid} for deletion. {err}")


class NautobotCircuitType(CircuitType):
    """Nautobot implementation of CircuitType DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create CircuitType in Nautobot from NautobotCircuitType object."""
        adapter.job.logger.info(f"Creating Nautobot CircuitType: {ids['name']}")
        _new_circuit_type = ORMCircuitType(
            name=ids["name"],
            description=attrs["description"],
        )
        _new_circuit_type.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_circuit_type.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_circuit_type.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_circuit_type, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update CircuitType in Nautobot from NautobotCircuitType object."""
        self.adapter.job.logger.debug(f"Updating Nautobot CircuitType {self.name}")
        _update_circuit_type = ORMCircuitType.objects.get(id=self.uuid)
        if "description" in attrs:
            _update_circuit_type.description = attrs["description"]
        _update_circuit_type.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        if not check_sor_field(_update_circuit_type):
            _update_circuit_type.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_circuit_type.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_circuit_type,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete CircuitType in Nautobot from NautobotCircuitType object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Circuittype: {self} - {self.uuid}")
            _nb_circuit_type = ORMCircuitType.objects.get(id=self.uuid)
            _nb_circuit_type.delete()
            super().delete()
            return self
        except ORMCircuitType.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find CircuitType {self.uuid} for deletion. {err}")


class NautobotCircuit(Circuit):
    """Nautobot implementation of Circuit DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Circuit in Nautobot from NautobotCircuit object."""
        adapter.job.logger.info(f"Creating Nautobot Circuit: {ids['circuit_id']}")
        if "tags" in attrs:
            _tags = []
            for _tag in attrs["tags"]:
                _tags.append(ORMTag.get(name=_tag))
        _provider = ORMProvider.objects.get(name=ids["provider"])
        _circuit_type = ORMCircuitType.objects.get(name=attrs["circuit_type"])
        _status = ORMStatus.objects.get(name=attrs["status"])
        _tenant = None
        if "tenant" in attrs:
            if attrs["tenant"] is not None:
                _tenant = ORMTenant.objects.get(name=attrs["tenant"])
        _new_circuit = ORMCircuit(
            cid=ids["circuit_id"],
            provider=_provider,
            circuit_type=_circuit_type,
            status=_status,
            install_date=(attrs["date_installed"] if attrs["date_installed"] is not None else None),
            commit_rate=attrs["commit_rate_kbps"],
            description=attrs["description"],
            tenant=_tenant,
        )
        for _tag in attrs["tags"]:
            try:
                _new_circuit.tags.add(ORMTag.objects.get(name=_tag))
            except ORMTag.DoesNotExist:
                adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        _new_circuit.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_circuit.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_circuit.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_circuit, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Circuit in Nautobot from NautobotCircuit object."""
        self.adapter.job.logger.debug(f"Updating Nautobot Circuit {self.circuit_id}")
        _update_circuit = ORMCircuit.objects.get(id=self.uuid)
        if "circuit_type" in attrs:
            _circuit_type = ORMCircuitType.objects.get(name=attrs["circuit_type"])
            _update_circuit.circuit_type = _circuit_type
        if "status" in attrs:
            _status = ORMStatus.objects.get(name=attrs["status"])
            _update_circuit.status = _status
        if "date_installed" in attrs:
            _update_circuit.install_date = attrs["date_installed"]
        if "commit_rate_kbps" in attrs:
            _update_circuit.commit_rate = attrs["commit_rate_kbps"]
        if "description" in attrs:
            _update_circuit.description = attrs["description"]
        if "tenant" in attrs:
            _tenant = ORMTenant.objects.get(name=attrs["tenant"])
            _update_circuit.tenant = _tenant
        if "tags" in attrs:
            # FIXME: There might be a better way to handle this that's easier on the database.
            _update_circuit.tags.clear()
            for _tag in attrs["tags"]:
                try:
                    _update_circuit.tags.add(ORMTag.objects.get(name=_tag))
                except ORMTag.DoesNotExist:
                    self.adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        if "terminations" in attrs:
            # TODO: Implement circuit terminations
            pass
        if not check_sor_field(_update_circuit):
            _update_circuit.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_circuit.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_circuit.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_circuit, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Circuit in Nautobot from NautobotCircuit object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete Circuit: {self} - {self.uuid}")
            _circuit = ORMCircuit.objects.get(id=self.uuid)
            _circuit.delete()
            super().delete()
            return self
        except ORMProvider.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Circuit {self.uuid} for deletion. {err}")


class NautobotCircuitTermination(CircuitTermination):
    """Nautobot implementation of CircuitTermination DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create CircuitTermination in Nautobot from NautobotCircuitTermination object."""
        adapter.job.logger.info(f"Creating Nautobot CircuitTermination {ids['name']}")
        _name_parts = ids["name"].split("__", 2)
        _circuit_id = _name_parts[0]
        _provider_name = _name_parts[1]
        _term_side = _name_parts[2]
        try:
            _provider = ORMProvider.objects.get(name=_provider_name)
        except ORMProvider.DoesNotExist:
            adapter.job.logger.warning(f"Provider {_provider_name} does not exist in Nautobot. Please create it.")
        try:
            _circuit = ORMCircuit.objects.get(cid=_circuit_id, provider=_provider)
        except ORMCircuit.DoesNotExist:
            adapter.job.logger.warning(f"Circuit {_circuit_id} does not exist in Nautobot. Please create it.")
        if "tags" in attrs:
            _tags = []
            for _tag in attrs["tags"]:
                _tags.append(ORMTag.get(name=_tag))
        if attrs["termination_type"] == "Provider Network":
            try:
                _provider_network = ORMProviderNetwork.objects.get(name=attrs["provider_network"])
            except ORMProviderNetwork.DoesNotExist:
                adapter.job.logger.warning(
                    f"ProviderNetwork {attrs['provider_network']} does not exist in Nautobot. Please create it."
                )
            _new_circuit_termination = ORMCircuitTermination(
                provider_network=_provider_network,
                circuit=_circuit,
                term_side=_term_side,
                xconnect_id=attrs["cross_connect_id"],
                pp_info=attrs["patch_panel_or_ports"],
                description=attrs["description"],
                upstream_speed=attrs["upstream_speed_kbps"],
                port_speed=attrs["port_speed_kbps"],
            )
        if attrs["termination_type"] == "Location":
            try:
                _location = ORMLocation.objects.get(name=attrs["location"])
            except ORMLocation.DoesNotExist:
                adapter.job.logger.warning(
                    f"Location {attrs['location']} does not exist in Nautobot. Please create it."
                )
            _new_circuit_termination = ORMCircuitTermination(
                location=_location,
                circuit=_circuit,
                term_side=_term_side,
                xconnect_id=attrs["cross_connect_id"],
                pp_info=attrs["patch_panel_or_ports"],
                description=attrs["description"],
                upstream_speed=attrs["upstream_speed_kbps"],
                port_speed=attrs["port_speed_kbps"],
            )
        for _tag in _tags:
            try:
                _new_circuit_termination.tags.add(ORMTag.objects.get(name=_tag))
            except ORMTag.DoesNotExist:
                adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        _new_circuit_termination.custom_field_data.update(
            {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
        )
        _new_circuit_termination.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_circuit_termination.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter,
                obj=_new_circuit_termination,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update CircuitTermination in Nautobot from NautobotCircuitTermination object."""
        self.adapter.job.logger.debug(f"Updating Nautobot CircuitTermination {self.name}")
        _update_circuit_termination = ORMCircuitTermination.objects.get(id=self.uuid)
        if "location" in attrs:
            try:
                _location = ORMLocation.objects.get(name=attrs["location"])
                if _update_circuit_termination.provider_network:
                    _update_circuit_termination.provider_network = None
                _update_circuit_termination.location = _location
            except ORMLocation.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Location {attrs['location']} does not exist in Nautobot. Please create it."
                )
        if "provider_network" in attrs:
            try:
                _provider_network = ORMProviderNetwork.objects.get(name=attrs["provider_network"])
                if _update_circuit_termination.location:
                    _update_circuit_termination.location = None
                _update_circuit_termination.provider_network = _provider_network
            except ORMProviderNetwork.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"ProviderNetwork {attrs['provider_network']} does not exist in Nautobot. Please create it."
                )
        if "port_speed_kbps" in attrs:
            _update_circuit_termination.port_speed = attrs["port_speed_kbps"]
        if "upstream_speed_kbps" in attrs:
            _update_circuit_termination.upstream_speed = attrs["upstream_speed_kbps"]
        if "cross_connect_id" in attrs:
            _update_circuit_termination.xconnect_id = attrs["cross_connect_id"]
        if "patch_panel_or_ports" in attrs:
            _update_circuit_termination.pp_info = attrs["patch_panel_or_ports"]
        if "description" in attrs:
            _update_circuit_termination.description = attrs["description"]
        if "tags" in attrs:
            # FIXME: There might be a better way to handle this that's easier on the database.
            _update_circuit_termination.tags.clear()
            for _tag in attrs["tags"]:
                try:
                    _update_circuit_termination.tags.add(ORMTag.objects.get(name=_tag))
                except ORMTag.DoesNotExist:
                    self.adapter.job.logger.warning(f"Tag {_tag} does not exist in Nautobot.")
        _update_circuit_termination.custom_field_data.update(
            {"last_synced_from_sor": datetime.today().date().isoformat()}
        )
        if not check_sor_field(_update_circuit_termination):
            _update_circuit_termination.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_circuit_termination.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_circuit_termination,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete CircuitTermination in Nautobot from NautobotCircuitTermination object."""
        try:
            self.adapter.job.logger.debug(f"Attempting to delete CircuitTermination: {self} - {self.uuid}")
            _nb_circuit_termination = ORMCircuitTermination.objects.get(id=self.uuid)
            _nb_circuit_termination.delete()
            super().delete()
            return self
        except ORMCircuitTermination.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find ProviderNetwork {self.uuid} for deletion. {err}")


class NautobotNamespace(Namespace):
    """Nautobot implementation of Nautobot Namespace model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Namespace in Nautobot from NautobotNamespace object."""
        adapter.job.logger.info(f"Creating Nautobot Namespace {ids['name']}")
        new_namespace = ORMNamespace(
            name=ids["name"],
            description=attrs["description"],
        )
        new_namespace.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_namespace.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_namespace.validated_save()
        if "location" in attrs:
            try:
                _location = ORMLocation.objects.get(name=attrs["location"])
                new_namespace.location = _location
                new_namespace.validated_save()
            except ORMLocation.DoesNotExist:
                adapter.job.logger.warning(
                    f"Nautobot Location {attrs['location']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_namespace, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Namespace in Nautobot from NautobotNamespace object."""
        self.adapter.job.logger.debug(f"Updating Nautobot Namespace {self.name}.")
        _update_namespace = ORMNamespace.objects.get(id=self.uuid)
        if "description" in attrs:
            _update_namespace.description = attrs["description"]
        if "location" in attrs:
            try:
                _location = ORMLocation.objects.get(name=attrs["location"])
                _update_namespace.location = _location
            except ORMLocation.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Nautobot Location {attrs['location']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        if not check_sor_field(_update_namespace):
            _update_namespace.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_namespace.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_namespace.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_namespace,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Namespace in Nautobot from NautobotNamespace object."""
        self.adapter.job.logger.debug(f"Delete Nautobot Namespace {self.uuid}")
        try:
            _namespace = ORMNamespace.objects.get(id=self.uuid)
            super().delete()
            _namespace.delete()
            return self
        except ORMNamespace.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Namespace {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete Namespace {self.name} due to existing references. Error: {err}."
            )


class NautobotRiR(RiR):
    """Nautobot implementation of Nautobot RiR model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create RiR in Nautobot from NautobotRiR object."""
        adapter.job.logger.info(f"Creating Nautobot RiR: {ids['name']}")
        new_rir = ORMRiR(
            name=ids["name"],
            is_private=attrs["private"],
            description=attrs["description"],
        )
        new_rir.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_rir.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_rir.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_rir, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update RiR in Nautobot from NautobotRiR object."""
        self.adapter.job.logger.info(f"Updating Nautobot RiR {self.name}")
        _update_rir = ORMRiR.objects.get(id=self.uuid)
        if "private" in attrs:
            _update_rir.is_private = attrs["private"]
        if "description" in attrs:
            _update_rir.description = attrs["description"]
        if not check_sor_field(_update_rir):
            _update_rir.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_rir.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_rir.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_rir, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete RiR in Nautobot from NautobotRiR object."""
        self.adapter.job.logger.debug(f"Delete Nautobot Namespace {self.uuid}")
        try:
            _rir = ORMRiR.objects.get(id=self.uuid)
            super().delete()
            _rir.delete()
            return self
        except ORMRiR.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find RiR {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete RiR {self.name} due to existing references. Error: {err}."
            )


class NautobotVLANGroup(VLANGroup):
    """Nautobot implementation of Nautobot VLANGroup model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create VLANGroup in Nautobot from NautobotVLANGroup object."""
        adapter.job.logger.info(f"Creating Nautobot VLANGroup: {ids['name']}")
        try:
            _location = ORMLocation.objects.get(name=attrs["location"])
        except ORMLocation.DoesNotExist:
            _location = None
            adapter.job.logger.warning(
                f"Nautobot Location {attrs['location']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
            )
        new_vlan_group = ORMVLANGroup(
            name=ids["name"],
            location=_location,
            description=attrs["description"],
        )
        new_vlan_group.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_vlan_group.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_vlan_group.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_vlan_group, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VLANGroup in Nautobot from NautobotVLANGroup object."""
        self.adapter.job.logger.info(f"Updating Nautobot VLANGroup {self.name}")
        _update_vlan_group = ORMVLANGroup.objects.get(id=self.uuid)
        if "location" in attrs:
            try:
                _location = ORMLocation.objects.get(name=attrs["location"])
            except ORMLocation.DoesNotExist:
                _location = None
                self.adapter.job.logger.warning(
                    f"Nautobot Location {attrs['location']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
            _update_vlan_group.location = _location
        if "description" in attrs:
            _update_vlan_group.description = attrs["description"]
        if not check_sor_field(_update_vlan_group):
            _update_vlan_group.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_vlan_group.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_vlan_group.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_vlan_group,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete VLANGroup in Nautobot from NautobotVLANGroup object."""
        self.adapter.job.logger.debug(f"Delete Nautobot VLANGroup {self.uuid}")
        try:
            _vlan_group = ORMVLANGroup.objects.get(id=self.uuid)
            super().delete()
            _vlan_group.delete()
            return self
        except ORMRiR.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find VLANGroup {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete VLANGroup {self.name} due to existing references. Error: {err}."
            )
        return self


class NautobotVLAN(VLAN):
    """Nautobot implementation of Nautobot VLAN model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create VLAN in Nautobot from NautobotVLAN object."""
        adapter.job.logger.info(f"Creating Nautobot VLAN: {ids['name']}")
        try:
            _vlan_group = ORMVLANGroup.objects.get(name=ids["vlan_group"])
        except ORMVLANGroup.DoesNotExist:
            _vlan_group = None
            if ids["vlan_group"]:
                adapter.job.logger.warning(
                    f"Nautobot VLANGroup {ids['vlan_group']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            _status = ORMStatus.objects.get(name=attrs["status"])
        except ORMStatus.DoesNotExist:
            _status = ORMStatus.objects.get(name="Active")
            adapter.job.logger.warning(
                f"Nautobot Status {attrs['status']} does not exist. Make sure it is created manually or defined in global_settings.yaml. Defaulting to Status Active."
            )
        try:
            _role = ORMRole.objects.get(name=attrs["role"])
        except ORMRole.DoesNotExist:
            _role = None
            if attrs["role"]:
                adapter.job.logger.warning(
                    f"Nautobot Role {attrs['role']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            _tenant = ORMTenant.objects.get(name=attrs["tenant"])
        except ORMTenant.DoesNotExist:
            _tenant = None
            if attrs["tenant"]:
                adapter.job.logger.warning(
                    f"Nautobot Tenant {attrs['tenant']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            if "tags" in attrs:
                _tags = []
                for tag in attrs["tags"]:
                    _tags.append(ORMTag.objects.get(name=tag))
        except ORMTag.DoesNotExist:
            adapter.job.logger.warning(
                f"Nautobot Tag {attrs['tags']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
            )
        new_vlan = ORMVLAN(
            name=ids["name"],
            vid=ids["vid"],
            vlan_group=_vlan_group,
            status=_status,
            role=_role,
            tenant=_tenant,
            description=attrs["description"],
        )
        if attrs.get("tags"):
            new_vlan.validated_save()
            new_vlan.tags.clear()
            for _tag in attrs["tags"]:
                new_vlan.tags.add(ORMTag.objects.get(name=_tag))
        new_vlan.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_vlan.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_vlan.validated_save()
        try:
            if "locations" in attrs:
                _locations = []
                for _location in attrs["locations"]:
                    _locations.append(ORMLocation.objects.get(name=_location))
        except ORMLocation.DoesNotExist:
            _location = None
            adapter.job.logger.warning(
                f"Nautobot Location {attrs['location']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
            )
        if _locations:
            for _location in _locations:
                new_vlan.locations.add(_location)
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_vlan, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()

        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VLAN in Nautobot from NautobotVLAN object."""
        self.adapter.job.logger.info(f"Updating Nautobot VLAN: {self.name}__{self.vid}")
        _update_vlan = ORMVLAN.objects.get(id=self.uuid)
        if "description" in attrs:
            _update_vlan.description = attrs["description"]
        if "status" in attrs:
            try:
                _status = ORMStatus.objects.get(name=attrs["status"])
            except ORMStatus.DoesNotExist:
                _status = ORMStatus.objects.get(name="Active")
                self.adapter.job.logger.warning(
                    f"Nautobot Status {attrs['status']} does not exist. Make sure it is created manually or defined in global_settings.yaml. Defaulting to Status Active."
                )
            _update_vlan.status = _status
        if "role" in attrs:
            try:
                _role = ORMRole.objects.get(name=attrs["role"])
            except ORMRole.DoesNotExist:
                _role = None
                if attrs["role"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot Role {attrs['role']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            _update_vlan.role = _role
        if "tenant" in attrs:
            try:
                _tenant = ORMTenant.objects.get(name=attrs["tenant"])
            except ORMTenant.DoesNotExist:
                _tenant = None
                if attrs["tenant"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot Tenant {attrs['tenant']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            _update_vlan.tenant = _tenant
        if "tags" in attrs:
            try:
                if "tags" in attrs:
                    _tags = []
                    for tag in attrs["tags"]:
                        _tags.append(ORMTag.objects.get(name=tag))
            except ORMTag.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Nautobot Tag {attrs['tags']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        if attrs.get("tags"):
            _update_vlan.validated_save()
            # TODO: Probably a better way to handle this that's easier on the database.
            _update_vlan.tags.clear()
            for _tag in attrs["tags"]:
                _update_vlan.tags.add(ORMTag.objects.get(name=_tag))
        if "locations" in attrs:
            # TODO: Probably a better way to handle this that's easier on the database.
            _update_vlan.locations.clear()
            try:
                _locations = []
                for _location in attrs["locations"]:
                    _locations.append(ORMLocation.objects.get(name=_location))
            except ORMLocation.DoesNotExist:
                _location = None
                self.adapter.job.logger.warning(
                    f"Nautobot Location {attrs['location']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
            if _locations:
                for _location in _locations:
                    _update_vlan.locations.add(_location)
        if not check_sor_field(_update_vlan):
            _update_vlan.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_vlan.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_vlan.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_vlan, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()

        return super().update(attrs)

    def delete(self):
        """Delete VLAN in Nautobot from NautobotVLAN object."""
        self.adapter.job.logger.debug(f"Delete Nautobot VLAN {self.uuid}")
        try:
            _vlan = ORMVLAN.objects.get(id=self.uuid)
            super().delete()
            _vlan.delete()
            return self
        except ORMVLAN.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find VLAN {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete VLAN {self.name} due to existing references. Error: {err}."
            )


class NautobotVRF(VRF):
    """Nautobot implementation of Nautobot VRF model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create VRF in Nautobot from NautobotVRF object."""
        adapter.job.logger.info(f"Creating Nautobot VRF: {ids['name']}")
        try:
            _tenant = ORMTenant.objects.get(name=attrs["tenant"])
        except ORMTenant.DoesNotExist:
            _tenant = None
            if attrs["tenant"]:
                adapter.job.logger.warning(
                    f"Nautobot Tenant {attrs['tenant']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            _namespace = ORMNamespace.objects.get(name=ids["namespace"])
        except ORMNamespace.DoesNotExist:
            _namespace = ORMNamespace.objects.get(name="Global")
            adapter.job.logger.warning(
                f"Nautobot Namespace {ids['namespace']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
            )
        new_vrf = ORMVRF(
            name=ids["name"],
            namespace=_namespace,
            rd=attrs["route_distinguisher"],
            tenant=_tenant,
            description=attrs["description"],
        )
        if attrs.get("tags"):
            new_vrf.validated_save()
            new_vrf.tags.clear()
            for _tag in attrs["tags"]:
                new_vrf.tags.add(ORMTag.objects.get(name=_tag))
        new_vrf.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_vrf.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_vrf.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_vrf, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VRF in Nautobot from NautobotVRF object."""
        self.adapter.job.logger.info(f"Creating Nautobot VRF: {self.name}")
        _update_vrf = ORMVRF.objects.get(id=self.uuid)
        if "tenant" in attrs:
            try:
                _tenant = ORMTenant.objects.get(name=attrs["tenant"])
            except ORMTenant.DoesNotExist:
                _tenant = None
                if attrs["tenant"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot Tenant {attrs['tenant']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            _update_vrf.tenant = _tenant
        if "description" in attrs:
            _update_vrf.description = attrs["description"]
        if "route_distinguisher" in attrs:
            _update_vrf.rd = attrs["route_distinguisher"]
        if attrs.get("tags"):
            _update_vrf.tags.clear()
            for _tag in attrs["tags"]:
                _update_vrf.tags.add(ORMTag.objects.get(name=_tag))
        if not check_sor_field(_update_vrf):
            _update_vrf.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_vrf.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_vrf.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_vrf, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete VRF in Nautobot from NautobotVRF object."""
        self.adapter.job.logger.debug(f"Delete Nautobot VRF {self.uuid}")
        try:
            _vrf = ORMVRF.objects.get(id=self.uuid)
            super().delete()
            _vrf.delete()
            return self
        except ORMVRF.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find VRF {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete VRF {self.name} due to existing references. Error: {err}."
            )


class NautobotPrefix(Prefix):
    """Nautobot implementation of Nautobot Prefix model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Nautobot from NautobotPrefix object."""
        adapter.job.logger.info(f"Creating Nautobot Prefix: {ids['network']} in Namespace: {ids['namespace']}")
        try:
            _namespace = ORMNamespace.objects.get(name=ids["namespace"])
        except ORMNamespace.DoesNotExist:
            _namespace = ORMNamespace.objects.get(name="Global")
            adapter.job.logger.warning(
                f"Nautobot Namespace {ids['namespace']} does not exist. Defaulting to Global Namespace."
            )
        try:
            if attrs["vlan"]:
                _vlan_name, _vlan_id, _vlan_group_name = attrs["vlan"].split("__", 2)
                _vlan_group = ORMVLANGroup.objects.get(name=_vlan_group_name)
                _vlan = ORMVLAN.objects.get(
                    name=_vlan_name,
                    vid=_vlan_id,
                    vlan_group=_vlan_group if _vlan_group != "None" else None,
                )
            else:
                _vlan = None
        except ORMVLANGroup.DoesNotExist:
            _vlan = None
            if attrs["vlan"]:
                adapter.job.logger.warning(
                    f"Nautobot VLANGroup {attrs['vlan']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        except ORMVLAN.DoesNotExist:
            _vlan = None
            if attrs["vlan"]:
                adapter.job.logger.warning(
                    f"Nautobot VLAN {attrs['vlan']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            _status = ORMStatus.objects.get(name=attrs["status"])
        except ORMStatus.DoesNotExist:
            _status = ORMStatus.objects.get(name="Active")
            adapter.job.logger.warning(
                f"Nautobot Status {attrs['status']} does not exist. Make sure it is created manually or defined in global_settings.yaml. Defaulting to Status Active."
            )
        try:
            _role = ORMRole.objects.get(name=attrs["role"])
        except ORMRole.DoesNotExist:
            _role = None
            if attrs["role"]:
                adapter.job.logger.warning(
                    f"Nautobot Role {attrs['role']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            _tenant = ORMTenant.objects.get(name=attrs["tenant"])
        except ORMTenant.DoesNotExist:
            _tenant = None
            if attrs["tenant"]:
                adapter.job.logger.warning(
                    f"Nautobot Tenant {attrs['tenant']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            _rir = ORMRiR.objects.get(name=attrs["rir"])
        except ORMRiR.DoesNotExist:
            _rir = None
            if attrs["rir"]:
                adapter.job.logger.warning(
                    f"Nautobot RiR {attrs['rir']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        try:
            if "tags" in attrs:
                _tags = []
                for tag in attrs["tags"]:
                    _tags.append(ORMTag.objects.get(name=tag))
        except ORMTag.DoesNotExist:
            adapter.job.logger.warning(
                f"Nautobot Tag {attrs['tags']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
            )

        network_parts = ids["network"].strip().split("/")
        if len(network_parts) != 2:
            adapter.job.logger.error(
                f"Invalid network format: {ids['network']}. Expected format: network/prefix_length"
            )
            return None

        try:
            network_address = network_parts[0].strip()
            prefix_length = int(network_parts[1].strip())

            # Validate network address format
            if not network_address or prefix_length < 0 or prefix_length > 128:
                adapter.job.logger.Warning(
                    f"Invalid network address or prefix length: {ids['network']} skipping. Format should be network/prefix_length."
                )
                return None

            new_prefix = ORMPrefix(
                network=network_address,
                prefix_length=prefix_length,
                namespace=_namespace,
                type=attrs["prefix_type"] if attrs["prefix_type"] else "Network",
                status=_status,
                role=_role,
                rir=_rir,
                tenant=_tenant,
                date_allocated=attrs["date_allocated"],
                description=attrs["description"],
                vlan=_vlan,
            )
            if attrs.get("tags"):
                new_prefix.validated_save()
                new_prefix.tags.clear()
                for _tag in attrs["tags"]:
                    new_prefix.tags.add(ORMTag.objects.get(name=_tag))
            new_prefix.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
            new_prefix.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
            new_prefix.validated_save()
            try:
                if "locations" in attrs:
                    _locations = []
                    if attrs["locations"]:
                        for _location in attrs["locations"]:
                            _locations.append(ORMLocation.objects.get(name=_location))
            except ORMLocation.DoesNotExist:
                _location = None
                adapter.job.logger.warning(
                    f"Nautobot Location {attrs['locations']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
            if _locations:
                for _location in _locations:
                    new_prefix.locations.add(_location)
            try:
                if "vrfs" in attrs:
                    _vrfs = []
                    if attrs["vrfs"]:
                        for _vrf in attrs["vrfs"]:
                            _vrf_name, _vrf_namespace = _vrf.split("__")
                            _namespace = ORMNamespace.objects.get(name=_vrf_namespace)
                            _vrfs.append(ORMVRF.objects.get(name=_vrf_name, namespace=_namespace))
                if _vrfs:
                    for _vrf in _vrfs:
                        adapter.job.logger.debug(f"Assigning VRF {_vrf} to Prefix {new_prefix}")
                        new_prefix.vrfs.add(_vrf)
            except ORMNamespace.DoesNotExist:
                _vrf = None
                if attrs["vrfs"]:
                    adapter.job.logger.warning(
                        f"Nautobot Namespace {attrs['vrfs']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            except ORMVRF.DoesNotExist:
                _vrf = None
                adapter.job.logger.warning(
                    f"Nautobot VRF {attrs['vrfs']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
            if METADATA_FOUND:
                metadata = add_or_update_metadata_on_object(
                    adapter=adapter, obj=new_prefix, scoped_fields=SCOPED_FIELDS_MAPPING
                )
                metadata.validated_save()
            return super().create(adapter=adapter, ids=ids, attrs=attrs)
        except ValueError:
            adapter.job.logger.error(
                f"Invalid network format: {ids['network']}. Expected format: network/prefix_length"
            )
            return None

    def update(self, attrs):
        """Update Prefix in Nautobot from NautobotPrefix object."""
        self.adapter.job.logger.info(f"Updating Nautobot Prefix: {self.network} in Namespace: {self.namespace}")
        _update_prefix = ORMPrefix.objects.get(id=self.uuid)
        if "prefix_type" in attrs:
            _update_prefix.prefix_type = attrs["prefix_type"]
        if "description" in attrs:
            _update_prefix.description = attrs["description"]
        if "vlan" in attrs:
            try:
                if attrs["vlan"]:
                    _vlan_name, _vlan_id, _vlan_group_name = attrs["vlan"].split("__", 2)
                    _vlan_group = ORMVLANGroup.objects.get(name=_vlan_group_name)
                    _vlan = ORMVLAN.objects.get(
                        name=_vlan_name,
                        vid=_vlan_id,
                        vlan_group=_vlan_group if _vlan_group != "None" else None,
                    )
                else:
                    _vlan = None
            except ORMVLANGroup.DoesNotExist:
                _vlan = None
                if attrs["vlan"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot VLANGroup {attrs['vlan']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            except ORMVLAN.DoesNotExist:
                _vlan = None
                if attrs["vlan"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot VLAN {attrs['vlan']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            _update_prefix.vlan = _vlan
        if "status" in attrs:
            try:
                _status = ORMStatus.objects.get(name=attrs["status"])
            except ORMStatus.DoesNotExist:
                _status = ORMStatus.objects.get(name="Active")
                self.adapter.job.logger.warning(
                    f"Nautobot Status {attrs['status']} does not exist. Make sure it is created manually or defined in global_settings.yaml. Defaulting to Status Active."
                )
            _update_prefix.status = _status
        if "role" in attrs:
            try:
                _role = ORMRole.objects.get(name=attrs["role"])
            except ORMRole.DoesNotExist:
                _role = None
                if attrs["role"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot Role {attrs['role']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            _update_prefix.role = _role
        if "tenant" in attrs:
            try:
                _tenant = ORMTenant.objects.get(name=attrs["tenant"])
            except ORMTenant.DoesNotExist:
                _tenant = None
                if attrs["tenant"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot Tenant {attrs['tenant']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            _update_prefix.tenant = _tenant
        if "rir" in attrs:
            try:
                _rir = ORMRiR.objects.get(name=attrs["rir"])
            except ORMRiR.DoesNotExist:
                _rir = None
                if attrs["rir"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot RiR {attrs['rir']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            _update_prefix.rir = _rir
        if "date_allocated" in attrs:
            _update_prefix.date_allocated = attrs["date_allocated"]
        if "tags" in attrs:
            _update_prefix.validated_save()
            _update_prefix.tags.clear()
            try:
                for tag in attrs["tags"]:
                    _tag = ORMTag.objects.get(name=tag)
                    _update_prefix.tags.add(_tag)
            except ORMTag.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Nautobot Tag {attrs['tags']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        if "locations" in attrs:
            try:
                _locations = []
                if attrs["locations"]:
                    for _location in attrs["locations"]:
                        _locations.append(ORMLocation.objects.get(name=_location))
                else:
                    _update_prefix.locations.clear()
            except ORMLocation.DoesNotExist:
                _location = None
                self.adapter.job.logger.warning(
                    f"Nautobot Location {attrs['locations']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
            if _locations:
                _update_prefix.locations.clear()
                for _location in _locations:
                    _update_prefix.locations.add(_location)
        if "vrfs" in attrs:
            try:
                _vrfs = []
                if attrs["vrfs"]:
                    for _vrf in attrs["vrfs"]:
                        _vrf_name, _vrf_namespace = _vrf.split("__")
                        _namespace = ORMNamespace.objects.get(name=_vrf_namespace)
                        _vrfs.append(ORMVRF.objects.get(name=_vrf_name, namespace=_namespace))
                else:
                    _update_prefix.vrfs.clear()
                if _vrfs:
                    for _vrf in _vrfs:
                        _update_prefix.vrfs.clear()
                        self.adapter.job.logger.debug(f"Assigning VRF {_vrf} to Prefix {_update_prefix}")
                        _update_prefix.vrfs.add(_vrf)
            except ORMNamespace.DoesNotExist:
                _vrf = None
                if attrs["vrfs"]:
                    self.adapter.job.logger.warning(
                        f"Nautobot Namespace {attrs['vrfs']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                    )
            except ORMVRF.DoesNotExist:
                _vrf = None
                self.adapter.job.logger.warning(
                    f"Nautobot VRF {attrs['vrfs']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        if not check_sor_field(_update_prefix):
            _update_prefix.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_prefix.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_prefix.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_prefix, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()

        return super().update(attrs)

    def delete(self):
        """Delete Prefix in Nautobot from NautobotPrefix object."""
        self.adapter.job.logger.debug(f"Delete Nautobot VRF {self.uuid}")
        try:
            _prefix = ORMPrefix.objects.get(id=self.uuid)
            super().delete()
            _prefix.delete()
            return self
        except ORMPrefix.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Prefix {self.uuid} for deletion. {err}")
        except ProtectedError as err:
            self.adapter.job.logger.warning(
                f"Unable to delete Prefix {self.name} due to existing references. Error: {err}."
            )


class NautobotSecret(Secret):
    """Nautobot implementation of Bootstrap Secret model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Secret in Nautobot from NautobotSecret object."""
        adapter.job.logger.info(f"Creating Nautobot Secret: {ids['name']}")
        new_secret = ORMSecret(name=ids["name"], provider=attrs["provider"], parameters=attrs["parameters"])
        new_secret.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_secret.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_secret.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_secret, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Secret in Nautobot from NautobotSecret object."""
        _update_secret = ORMSecret.objects.get(id=self.uuid)
        if "provider" in attrs:
            _update_secret.provider = attrs["provider"]
        if "parameters" in attrs:
            _update_secret.parameters["variable"] = attrs["parameters"]["variable"]
        _update_secret.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        if not check_sor_field(_update_secret):
            _update_secret.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_secret.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_secret, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Secret in Nautobot from NautobotSecret object."""
        self.adapter.job.logger.debug(f"Delete secret uuid: {self.uuid}")
        try:
            secr = ORMSecret.objects.get(id=self.uuid)
            super().delete()
            secr.delete()
            return self
        except ORMSecret.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Secret {self.uuid} for deletion. {err}")


class NautobotSecretsGroup(SecretsGroup):
    """Nautobot implementation of Bootstrap SecretsGroup model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create SecretsGroup in Nautobot from NautobotSecretsGroup object."""
        adapter.job.logger.info(f"Creating Nautobot SecretsGroup: {ids['name']}")
        _new_secrets_group = ORMSecretsGroup(name=ids["name"])
        _new_secrets_group.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_secrets_group.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_secrets_group.validated_save()

        for _secret in attrs["secrets"]:
            try:
                _orm_secret = ORMSecret.objects.get(name=_secret["name"])
                _new_secrets_group.secrets.add(_orm_secret)
                _new_secrets_group.validated_save()
                _sga = _new_secrets_group.secrets_group_associations.get(secret__id=_orm_secret.id)
                _sga.access_type = _secret["access_type"]
                _sga.secret_type = _secret["secret_type"]
                _sga.validated_save()
                if METADATA_FOUND:
                    metadata = add_or_update_metadata_on_object(
                        adapter=adapter,
                        obj=_new_secrets_group,
                        scoped_fields=SCOPED_FIELDS_MAPPING,
                    )
                    metadata.validated_save()
                return super().create(adapter=adapter, ids=ids, attrs=attrs)
            except ORMSecret.DoesNotExist:
                adapter.job.logger.warning(
                    f"Secret - {_secret['name']} does not exist in Nautobot, ensure it is created."
                )

    def update(self, attrs):
        """Update SecretsGroup in Nautobot from NautobotSecretsGroup object."""
        self.adapter.job.logger.info(f"Updating SecretsGroup {self.name}")
        _update_group = ORMSecretsGroup.objects.get(name=self.name)
        if "secrets" in attrs:
            for _secret in attrs["secrets"]:
                try:
                    _orm_secret = ORMSecret.objects.get(name=_secret["name"])
                    try:
                        _sga = _update_group.secrets_group_associations.get(secret__id=_orm_secret.id)
                    except ORMSecretsGroupAssociation.DoesNotExist:
                        _sga = ORMSecretsGroupAssociation(
                            secrets_group=_update_group,
                            secret=_orm_secret,
                        )
                    _sga.access_type = _secret["access_type"]
                    _sga.secret_type = _secret["secret_type"]
                    _sga.validated_save()
                except ORMSecret.DoesNotExist:
                    self.adapter.job.logger.warning(
                        f"Secret - {_secret['name']} does not exist in Nautobot, ensure it is created."
                    )
                    return None

        if not check_sor_field(_update_group):
            _update_group.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_group.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_group.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_group, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete SecretsGroup in Nautobot from NautobotSecretsGroup object."""
        self.adapter.job.logger.debug(f"Delete SecretsGroup uuid: {self.uuid}")
        try:
            secr = ORMSecretsGroup.objects.get(id=self.uuid)
            super().delete()
            secr.delete()
            return self
        except ORMSecretsGroup.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find SecretsGroup {self.uuid} for deletion. {err}")


class NautobotGitRepository(GitRepository):
    """Nautobot implementation of Bootstrap GitRepository model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create GitRepository in Nautobot from NautobotGitRepository object."""
        adapter.job.logger.info(f"Creating Nautobot Git Repository: {ids['name']}")
        _secrets_group = None
        if attrs.get("secrets_group"):
            _secrets_group = ORMSecretsGroup.objects.get(name=attrs["secrets_group"])
        new_gitrepository = ORMGitRepository(
            name=ids["name"],
            remote_url=attrs["url"],
            branch=attrs["branch"],
            secrets_group=_secrets_group,
            provided_contents=attrs["provided_contents"],
        )
        new_gitrepository.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        new_gitrepository.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_gitrepository.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_gitrepository, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update GitRepository in Nautobot from NautobotSecretsGroup object."""
        self.adapter.job.logger.info(f"Updating GitRepository {self.name}")
        _update_git_repo = ORMGitRepository.objects.get(name=self.name)
        if attrs.get("url"):
            _update_git_repo.remote_url = attrs["url"]
        if attrs.get("branch"):
            _update_git_repo.branch = attrs["branch"]
        if attrs.get("secrets_group"):
            _secrets_group = ORMSecretsGroup.objects.get(name=attrs["secrets_group"])
            _update_git_repo.secrets_group = _secrets_group
        if attrs.get("provided_contents"):
            _update_git_repo.provided_contents = attrs["provided_contents"]
        if not check_sor_field(_update_git_repo):
            _update_git_repo.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_git_repo.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_git_repo.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_git_repo, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete GitRepository in Nautobot from NautobotGitRepository object."""
        self.adapter.job.logger.debug(f"Delete GitRepository uuid: {self.uuid}")
        try:
            git_repo = ORMGitRepository.objects.get(id=self.uuid)
            super().delete()
            git_repo.delete()
            return self
        except ORMGitRepository.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find GitRepository {self.uuid} for deletion. {err}")


class NautobotDynamicGroup(DynamicGroup):
    """Nautobot implementation of Bootstrap DynamicGroup model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DynamicGroup in Nautobot from NautobotDynamicGroup object."""
        adapter.job.logger.info(f"Creating Nautobot Dynamic Group: {ids['name']}")
        _content_type_id = lookup_content_type_id(nb_model="dynamic_groups", model_path=ids["content_type"])
        if _content_type_id is None:
            adapter.job.logger.warning(
                f"Could not find ContentType for {ids['label']} with ContentType {ids['content_type']}"
            )
        _content_type = ContentType.objects.get_for_id(id=_content_type_id)
        _new_nb_dg = ORMDynamicGroup(
            name=ids["name"],
            content_type=_content_type,
            filter=attrs["dynamic_filter"],
            description=attrs["description"],
        )
        _new_nb_dg.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_nb_dg.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})

        try:
            _new_nb_dg.validated_save()
        except ValidationError:
            if attrs.get("dynamic_filter"):
                _new_nb_dg.filter = attrs["dynamic_filter"]
            if attrs.get("description"):
                _new_nb_dg.description = attrs["description"]
            _new_nb_dg.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
            _new_nb_dg.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_nb_dg, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update DynamicGroups in Nautobot from NautobotDynamicGroup object."""
        self.adapter.job.logger.info(f"Updating DynamicGroup {self.name}")
        _update_dyn_group = ORMDynamicGroup.objects.get(name=self.name)
        if attrs.get("dynamic_filter"):
            _update_dyn_group.filter = attrs["dynamic_filter"]
        if attrs.get("description"):
            _update_dyn_group.description = attrs["description"]
        if not check_sor_field(_update_dyn_group):
            _update_dyn_group.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_dyn_group.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_dyn_group.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_dyn_group,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete DynamicGroup in Nautobot from NautobotDynamicGroup object."""
        self.adapter.job.logger.debug(f"Delete DynamicGroup uuid: {self.name}")
        try:
            dyn_group = ORMDynamicGroup.objects.get(name=self.name)
            super().delete()
            dyn_group.delete()
            return self
        except ORMDynamicGroup.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find DynamicGroup {self.name} for deletion. {err}")


class NautobotComputedField(ComputedField):
    """Nautobot implementation of Bootstrap ComputedField model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create ComputedField in Nautobot from NautobotComputedField object."""
        adapter.job.logger.info(f"Creating Nautobot Computed Field: {ids['label']}")
        _content_type_id = lookup_content_type_id(nb_model="custom_fields", model_path=attrs["content_type"])
        if _content_type_id is None:
            adapter.job.logger.warning(
                f"Could not find ContentType for {ids['label']} with ContentType {attrs['content_type']}"
            )
        _content_type = ContentType.objects.get_for_id(id=_content_type_id)
        _new_computed_field = ORMComputedField(
            label=ids["label"], content_type=_content_type, template=attrs["template"]
        )
        _new_computed_field.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_computed_field, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ComputedField in Nautobot from NautobotComputedField object."""
        self.adapter.job.logger.info(f"Updating ComputedField {self.label}")
        comp_field = ORMComputedField.objects.get(label=self.label)
        if attrs.get("content_type"):
            _content_type_id = lookup_content_type_id(nb_model="custom_fields", model_path=attrs["content_type"])
            if _content_type_id is None:
                self.adapter.job.logger.warning(
                    f"Could not find ContentType for {self['label']} with ContentType {attrs['content_type']}"
                )
            _content_type = ContentType.objects.get_for_id(id=_content_type_id)
            comp_field.content_type = _content_type
        if attrs.get("template"):
            comp_field.template = attrs["template"]
        comp_field.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=comp_field, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete ComputedField in Nautobot from NautobotComputedField object."""
        self.adapter.job.logger.debug(f"Delete ComputedField: {self.label}")
        try:
            comp_field = ORMComputedField.objects.get(label=self.label)
            super().delete()
            comp_field.delete()
            return self
        except ORMComputedField.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find ComputedField {self.label} for deletion. {err}")


class NautobotCustomField(CustomField):
    """Nautobot implementation of Bootstrap CustomField model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create CustomField in Nautobot from NautobotCustomField object."""
        _content_types = []
        adapter.job.logger.info(f"Creating Nautobot Custom Field: {ids['label']}")

        for _model in attrs["content_types"]:
            try:
                _content_types.append(lookup_content_type_for_taggable_model_path(_model))
            except ContentType.DoesNotExist:
                adapter.job.logger.error(f"Unable to find ContentType for {_model}.")

        _new_custom_field = ORMCustomField(
            label=ids["label"],
            description=attrs["description"],
            required=attrs["required"],
            type=attrs["type"],
            grouping=attrs["grouping"],
            weight=attrs["weight"],
            default=attrs["default"],
            filter_logic=attrs["filter_logic"],
            advanced_ui=attrs["advanced_ui"],
            validation_minimum=attrs["validation_minimum"],
            validation_maximum=attrs["validation_maximum"],
            validation_regex=attrs["validation_regex"],
        )
        _new_custom_field.validated_save()
        _new_custom_field.content_types.set(_content_types)

        for choice in attrs["custom_field_choices"]:
            _new_cf = ORMCustomFieldChoice(
                value=choice["value"], weight=choice["weight"], custom_field=_new_custom_field
            )
            _new_cf.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_custom_field, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()

        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update CustomField in Nutobot from NautobotCustomField object."""
        self.adapter.job.logger.info(f"Updating CustomField {self.label}")
        cust_field = ORMCustomField.objects.get(label=self.label)
        _content_types = []
        if attrs.get("content_types"):
            for _model in attrs["content_types"]:
                try:
                    _content_types.append(lookup_content_type_for_taggable_model_path(_model))
                except ContentType.DoesNotExist:
                    self.adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
            cust_field.content_types.set(_content_types)
        if "description" in attrs:
            cust_field.description = attrs["description"]
        if "required" in attrs:
            cust_field.required = attrs["required"]
        if "type" in attrs:
            self.adapter.job.logger.error("Custom Field Type cannot be changed once created.")
        if "grouping" in attrs:
            cust_field.grouping = attrs["grouping"]
        if "weight" in attrs:
            cust_field.weight = attrs["weight"]
        if "default" in attrs:
            cust_field.default = attrs["default"]
        if "filter_logic" in attrs:
            cust_field.filter_logic = attrs["filter_logic"]
        if "advanced_ui" in attrs:
            cust_field.advanced_ui = attrs["advanced_ui"]
        if "validation_minimum" in attrs:
            cust_field.validation_minimum = attrs["validation_minimum"]
        if "validation_maximum" in attrs:
            cust_field.validation_maximum = attrs["validation_maximum"]
        if "validation_regex" in attrs:
            cust_field.validation_regex = attrs["validaton_regex"]
        if "custom_field_choices" in attrs:
            cust_field.custom_field_choices.all().delete()
            for choice in attrs["custom_field_choices"]:
                _new_cf = ORMCustomFieldChoice(value=choice["value"], weight=choice["weight"], custom_field=cust_field)
                _new_cf.validated_save()

        cust_field.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=cust_field, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete CustomField in Nautobot from NautobotCustomField object."""
        self.adapter.job.logger.debug(f"Delete CustomField: {self.label}")
        try:
            cust_field = ORMCustomField.objects.get(label=self.label)
            super().delete()
            cust_field.delete()
            return self
        except ORMCustomField.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find CustomField {self.label} for deletion. {err}")


class NautobotTag(Tag):
    """Nautobot implementation of Bootstrap Tag model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Tag in Nautobot from NautobotTag object."""
        _content_types = []
        adapter.job.logger.info(f"Creating Nautobot Tag: {ids['name']}")
        for _model in attrs["content_types"]:
            adapter.job.logger.debug(f"Looking up {_model} in content types.")
            try:
                _content_types.append(lookup_content_type_for_taggable_model_path(_model))
            except ContentType.DoesNotExist:
                adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
        _color = attrs.get("color", "#999999")
        _new_tag = ORMTag(
            name=ids["name"],
            color=_color,
            description=attrs["description"],
        )
        _new_tag.validated_save()
        _new_tag.content_types.set(_content_types)
        _new_tag.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_tag.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_tag.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_tag, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Tag in Nautobot from NautobotTag object."""
        self.adapter.job.logger.info(f"Updating Tag {self.name}")
        _update_tag = ORMTag.objects.get(name=self.name)
        if attrs.get("color"):
            _update_tag.color = attrs["color"]
        if attrs.get("content_types"):
            _content_types = []
            for _model in attrs["content_types"]:
                self.adapter.job.logger.debug(f"Looking up {_model} in content types.")
                try:
                    _content_types.append(lookup_content_type_for_taggable_model_path(_model))
                except ContentType.DoesNotExist:
                    self.adapter.job.logger.error(f"Unable to find ContentType for {_model}.")
            _update_tag.content_types.set(_content_types)
        if attrs.get("description"):
            _update_tag.description = attrs["description"]
        if not check_sor_field(_update_tag):
            _update_tag.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_tag.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_tag.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_tag, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Tag in Nautobot from NautobotTag object."""
        self.adapter.job.logger.debug(f"Delete Tag: {self.name}")
        try:
            _tag = ORMTag.objects.get(name=self.name)
            super().delete()
            _tag.delete()
            return self
        except ORMTag.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Tag {self.name} for deletion. {err}")


class NautobotGraphQLQuery(GraphQLQuery):
    """Nautobot implementation of Bootstrap GraphQLQuery model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create GraphQLQuery in Nautobot from NautobotGraphQLQuery object."""
        adapter.job.logger.info(f"Creating Nautobot GraphQLQuery: {ids['name']}")
        _new_query = ORMGraphQLQuery(name=ids["name"], query=attrs["query"])
        _new_query.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_query, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update GraphQLQuery in Nautobot from NautobotGraphQLQuery object."""
        self.adapter.job.logger.info(f"Updating GraphQLQuery: {self.name}.")
        _query = ORMGraphQLQuery.objects.get(name=self.name)
        if attrs.get("query"):
            _query.query = attrs["query"]
        _query.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_query, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete GraphQLQuery in Nautobot from NautobotGraphQLQuery object."""
        self.adapter.job.logger.debug(f"Delete GraphQLQuery: {self.name}")
        try:
            _query = ORMGraphQLQuery.objects.get(name=self.name)
            super().delete()
            _query.delete()
            return self
        except ORMGraphQLQuery.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find GraphQLQuery {self.name} for deletion. {err}")


class NautobotScheduledJob(ScheduledJob):
    """Nautobot implementation of Bootstrap Scheduled model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create ScheduledJob in Nautobot from NautobotScheduledJob object."""
        adapter.job.logger.info(f"Creating Scheduled Job ({ids['name']})")
        job_kwargs = attrs["job_vars"] if attrs.get("job_vars") else {}
        try:
            job_model = ORMJob.objects.get(name=attrs["job_model"])
            user = ORMUser.objects.get(username=attrs["user"])
        except ORMJob.DoesNotExist:
            adapter.job.logger.error(f"Job ({attrs['job_model']}) not found, unable to create Job, skipping.")
            return
        except ORMUser.DoesNotExist:
            adapter.job.logger.error(f"User ({attrs['user']}) not found, unable to create Job, skipping.")
            return
        if attrs.get("start_time"):
            if datetime.fromisoformat(attrs["start_time"]) < timezone.now():
                adapter.job.logger.error(f"Cannot create Scheduled Job ({ids['name']}) with a start time in the past.")
                return

        profile = attrs.get("profile")
        task_queue = attrs.get("task_queue")
        celery_kwargs = {
            "nautobot_job_profile": profile,
            "queue": task_queue,
        }
        if job_model.soft_time_limit > 0:
            celery_kwargs["soft_time_limit"] = job_model.soft_time_limit
        if job_model.time_limit > 0:
            celery_kwargs["time_limit"] = job_model.time_limit

        scheduled_job = ORMScheduledJob(
            name=ids["name"],
            task=job_model.class_path,
            job_model=job_model,
            user=user,
            interval=attrs.get("interval"),
            start_time=attrs.get("start_time"),
            crontab=attrs.get("crontab"),
            approval_required=attrs.get("approval_required"),
            kwargs=job_kwargs,
            celery_kwargs=celery_kwargs,
            enabled=attrs.get("enabled"),
        )
        scheduled_job.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=scheduled_job, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()

        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ScheduledJob in Nautobot from NautobotScheduledJob object."""
        self.adapter.job.logger.info(f"Updating Scheduled Job ({self.name})")
        job = ORMScheduledJob.objects.get(name=self.name)

        if attrs.get("job_model"):
            try:
                job.job_model = ORMJob.objects.get(name=attrs["job_model"])
            except ORMJob.DoesNotExist:
                self.adapter.job.logger.error(
                    f"Job ({attrs['job_model']}) does not exist, unable to update ({self.name})"
                )

        if attrs.get("user"):
            try:
                job.user = ORMUser.objects.get(username=attrs["user"])
            except ORMUser.DoesNotExist:
                self.adapter.job.logger.error(f"User ({attrs['user']}) does not exist, unable to update ({self.name})")

        if attrs.get("start_time"):
            if datetime.fromisoformat(attrs["start_time"]) < timezone.now():
                self.adapter.job.logger.error(
                    f"Cannot update Scheduled Job ({self.name}) with a start time in the past."
                )
                return
            job.start_time = datetime.fromisoformat(attrs["start_time"])

        if attrs.get("interval"):
            job.interval = attrs["interval"]
        if attrs.get("crontab"):
            job.crontab = attrs["crontab"]
        if attrs.get("job_vars"):
            job.kwargs = attrs["job_vars"]
        if "profile" in attrs:
            job.celery_kwargs["nautobot_job_profile"] = attrs["profile"]
        if "approval_required" in attrs:
            job.approval_required = attrs["approval_required"]
        if "task_queue" in attrs:
            job.celery_kwargs["queue"] = attrs["task_queue"]
        if "enabled" in attrs:
            job.enabled = attrs["enabled"]

        job.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=job, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()

        return super().update(attrs)

    def delete(self):
        """Delete ScheduledJob in Nautobot from NautobotScheduledJob object."""
        try:
            scheduled_job = ORMScheduledJob.objects.get(name=self.name)
            self.adapter.job.logger.warning(f"Deleting Scheduled Job ({self.name})")
            super().delete()
            scheduled_job.delete()
            return self
        except ORMScheduledJob.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Scheduled Job ({self.name}) for deletion. {err}")

    from django.utils.dateparse import parse_datetime


class NautobotSoftware(_Software_Base_Class):
    """Nautobot implementation of Bootstrap Software model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Software in Nautobot from NautobotSoftware object."""
        adapter.job.logger.info(f"Creating Software: {ids['platform']} - {ids['version']}.")
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating Software: {ids['platform']} - {ids['version']} with attrs: {attrs}.")
        _tags = []
        for tag in attrs["tags"]:
            _tags.append(ORMTag.objects.get(name=tag))
        if core_supports_softwareversion():
            _status = ORMStatus.objects.get(name=attrs["status"])
        _platform = ORMPlatform.objects.get(name=ids["platform"])
        if dlm_supports_softwarelcm():
            _new_software = ORMSoftware(
                version=ids["version"],
                alias=attrs["alias"],
                device_platform=_platform,
                end_of_support_date=attrs["eos_date"],
                long_term_support=attrs["long_term_support"],
                pre_release=attrs["pre_release"],
                documentation_url=attrs["documentation_url"],
            )
        elif core_supports_softwareversion():
            _new_software = ORMSoftware(
                version=ids["version"],
                alias=attrs["alias"],
                status=_status,
                platform=_platform,
                end_of_support_date=attrs["eos_date"],
                long_term_support=attrs["long_term_support"],
                pre_release=attrs["pre_release"],
                documentation_url=attrs["documentation_url"],
            )
        else:
            adapter.job.logger.error(
                f"Software model not found so skipping creation of {ids['version']} for {ids['platform']}."
            )
            return None
        adapter.job.logger.info(f"Creating Nautobot Software object {ids['platform']} - {ids['version']}.")
        if attrs.get("tags"):
            _new_software.validated_save()
            _new_software.tags.clear()
            for tag in attrs["tags"]:
                _new_software.tags.add(ORMTag.objects.get(name=tag))
        _new_software.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_software.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_software.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_software, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Software in Nautobot from NautobotSoftware object."""
        if self.adapter.job.debug:
            self.adapter.job.logger.debug(f"Updating Software: {self.platform} - {self.version}.")
        _platform = ORMPlatform.objects.get(name=self.platform)
        if dlm_supports_softwarelcm():
            _update_software = ORMSoftware.objects.get(version=self.version, device_platform=_platform)
        if core_supports_softwareversion():
            _update_software = ORMSoftware.objects.get(version=self.version, platform=_platform)
        self.adapter.job.logger.info(f"Updating Software: {self.platform} - {self.version}.")
        if "alias" in attrs:
            _update_software.alias = attrs["alias"]
        if "status" in attrs:
            _update_software.status = ORMStatus.objects.get(name=attrs["status"])
        if attrs.get("release_date"):
            _update_software.release_date = attrs["release_date"]
        if attrs.get("eos_date"):
            if core_supports_softwareversion():
                _update_software.end_of_support_date = attrs["eos_date"]
            else:
                _update_software.end_of_support = attrs["eos_date"]
        if attrs.get("long_term_support"):
            _update_software.long_term_support = attrs["long_term_support"]
        if attrs.get("pre_release"):
            _update_software.pre_release = attrs["pre_release"]
        if attrs.get("documentation_url"):
            _update_software.documentation_url = attrs["documentation_url"]
        if not attrs.get("documentation_url"):
            if attrs.get("documentation_url") == "":
                _update_software.documentation_url = ""
        if attrs.get("tags"):
            _update_software.tags.clear()
            for tag in attrs["tags"]:
                _update_software.tags.add(ORMTag.objects.get(name=tag))
        if not check_sor_field(_update_software):
            _update_software.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _update_software.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_software.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_software, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Software in Nautobot from NautobotSoftware object."""
        try:
            _platform = ORMPlatform.objects.get(name=self.platform)
            _software = ORMSoftware.objects.get(version=self.version, device_platform=_platform)
            super().delete()
            _software.delete()
            return self
        except ORMSoftware.DoesNotExist as err:
            self.adapter.job.logger.warning(
                f"Unable to find Software {self.platform} - {self.version} for deletion. {err}"
            )


class NautobotSoftwareImage(_SoftwareImage_Base_Class):
    """Nautobot implementation of Bootstrap SoftwareImage model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create SoftwareImage in Nautobot from NautobotSoftwareImage object."""
        if core_supports_softwareversion():
            adapter.job.logger.info(f"Creating Software Image: {attrs['platform']} - {ids['software_version']}.")
        else:
            adapter.job.logger.info(f"Creating Software Image File: {attrs['platform']} - {ids['software']}.")
        _tags = []
        _device_types = []
        if attrs["device_types"] is not None:
            for dt in attrs["device_types"]:
                _device_types.append(ORMDeviceType.objects.get(model=dt))
        if core_supports_softwareversion():
            _status = ORMStatus.objects.get(name=attrs.get(attrs["status"], "Active"))
        else:
            _status = ORMStatus.objects.get(name="Active")
        if attrs["tags"] is not None:
            for tag in attrs["tags"]:
                _tags.append(ORMTag.objects.get(name=tag))
        _platform = ORMPlatform.objects.get(name=attrs["platform"])
        if core_supports_softwareversion():
            if adapter.job.debug:
                adapter.job.logger.debug(f"Getting Software: {ids['software_version']}.")
            _software = ORMSoftware.objects.get(version=ids["software_version"].split(" - ")[1], platform=_platform)
        else:
            if adapter.job.debug:
                adapter.job.logger.debug(f"Getting Software: {attrs['software_version']} - {attrs['platform']}.")
            _software = ORMSoftware.objects.get(version=attrs["software_version"], device_platform=_platform)
        if core_supports_softwareversion():
            _new_soft_image = ORMSoftwareImage(
                software_version=_software,
                status=_status,
                image_file_size=attrs["file_size"],
                image_file_name=ids["image_file_name"],
                image_file_checksum=attrs["image_file_checksum"],
                hashing_algorithm=attrs["hashing_algorithm"],
                download_url=attrs["download_url"],
                default_image=attrs["default_image"],
            )
        else:
            _new_soft_image = ORMSoftwareImage(
                software=_software,
                image_file_name=attrs["file_name"],
                image_file_checksum=attrs["image_file_checksum"],
                hashing_algorithm=attrs["hashing_algorithm"],
                download_url=attrs["download_url"],
                default_image=attrs["default_image"],
            )
        if attrs.get("tags"):
            _new_soft_image.validated_save()
            _new_soft_image.tags.clear()
            for tag in attrs["tags"]:
                _new_soft_image.tags.add(ORMTag.objects.get(name=tag))
        if attrs.get("device_types") and core_supports_softwareversion():
            _new_soft_image.device_types.set(_device_types)
        _new_soft_image.custom_field_data.update({"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")})
        _new_soft_image.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _new_soft_image.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=_new_soft_image, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update SoftwareImage in Nautobot from NautobotSoftwareImage object."""
        if core_supports_softwareversion():
            self.adapter.job.logger.info(f"Updating Software Image: {self.software_version}.")
        else:
            self.adapter.job.logger.info(f"Updating Software Image File: {self.platform} - {self.software}.")
        _platform = ORMPlatform.objects.get(name=self.platform)
        if core_supports_softwareversion():
            _software = ORMSoftware.objects.get(version=self.software_version.split(" - ")[1], platform=_platform)
        else:
            _software = ORMSoftware.objects.get(version=self.software_version, device_platform=_platform)
        if core_supports_softwareversion():
            _update_soft_image = ORMSoftwareImage.objects.get(software_version=_software)
        else:
            _update_soft_image = ORMSoftwareImage.objects.get(software=_software)
        if attrs.get("platform"):
            _update_soft_image.platform = _platform
        if "status" in attrs:
            _update_soft_image.status = ORMStatus.objects.get(name=attrs["status"])
        if attrs.get("file_size"):
            _update_soft_image.image_file_size = attrs["file_size"]
        if attrs.get("device_types"):
            _update_soft_image.device_types.clear()
            for dt in attrs["device_types"]:
                _update_soft_image.device_types.add(ORMDeviceType.objects.get(model=dt))
        if attrs.get("software_version"):
            _update_soft_image.software_version = attrs["software_version"]
        if attrs.get("file_name"):
            _update_soft_image.image_file_name = attrs["file_name"]
        if attrs.get("image_file_checksum"):
            _update_soft_image.image_file_checksum = attrs["image_file_checksum"]
        if attrs.get("hashing_algorithm"):
            _update_soft_image.hashing_algorithm = attrs["hashing_algorithm"]
        if attrs.get("download_url"):
            _update_soft_image.download_url = attrs["download_url"]
        if attrs.get("default_image"):
            _update_soft_image.default_image = attrs["default_image"]
        if attrs.get("tags"):
            _update_soft_image.tags.clear()
            if attrs["tags"] is not None:
                for tag in attrs["tags"]:
                    _update_soft_image.tags.add(ORMTag.objects.get(name=tag))
        if not check_sor_field(_update_soft_image):
            _update_soft_image.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_soft_image.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _update_soft_image.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter,
                obj=_update_soft_image,
                scoped_fields=SCOPED_FIELDS_MAPPING,
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete SoftwareImage in Nautobot from NautobotSoftwareImage object."""
        try:
            _platform = ORMPlatform.objects.get(name=self.platform)
            _software = ORMSoftware.objects.get(version=self.software_version, device_platform=_platform)
            _soft_image = ORMSoftwareImage.objects.get(software=_software)
            super().delete()
            _soft_image.delete()
            return self
        except ORMSoftwareImage.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find SoftwareImage {self.software} for deletion. {err}")


if validate_dlm_installed():

    class NautobotValidatedSoftware(ValidatedSoftware):
        """Nautobot implementation of Bootstrap ValidatedSoftware model."""

        @classmethod
        def create(cls, adapter, ids, attrs):
            """Create ValidatedSoftware in Nautobot from NautobotValidatedSoftware object."""
            adapter.job.logger.info(f"Creating Validated Software: {attrs['software_version']}.")

            _devices = []  # noqa: F841
            _device_types = []  # noqa: F841
            _device_roles = []  # noqa: F841
            _inventory_items = []  # noqa: F841
            _object_tags = []  # noqa: F841
            try:
                _platform = ORMPlatform.objects.get(name=attrs["platform"])
                if dlm_supports_softwarelcm():
                    _software = ORMSoftware.objects.get(version=attrs["software_version"], device_platform=_platform)
                if core_supports_softwareversion():
                    _software = ORMSoftware.objects.get(version=attrs["software_version"], platform=_platform)
            except ORMPlatform.DoesNotExist:
                adapter.job.logger.warning(
                    f"Platform ({attrs['platform']}) not found, unable to create Validated Software."
                )
                return None
            except ORMSoftware.DoesNotExist:
                adapter.job.logger.warning(
                    f"Software ({attrs['software_version']}) not found, unable to create Validated Software."
                )
                return None

            _new_validated_software = ORMValidatedSoftware(
                software=_software,
                start=ids["valid_since"] if not None else datetime.today().date(),
                end=ids["valid_until"],
                preferred=attrs["preferred_version"],
            )
            _new_validated_software.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
            _new_validated_software.custom_field_data.update(
                {"last_synced_from_sor": datetime.today().date().isoformat()}
            )
            _new_validated_software.validated_save()
            if "devices" in attrs:
                if attrs["devices"]:
                    for _dev in attrs["devices"]:
                        _devices.append(ORMDevice.objects.get(name=_dev))
                    _new_validated_software.devices.set(_devices)
            if "device_types" in attrs:
                if attrs["device_types"]:
                    for _dev_type in attrs["device_types"]:
                        _device_types.append(ORMDeviceType.objects.get(model=_dev_type))
                    _new_validated_software.device_types.set(_device_types)
            if "device_roles" in attrs:
                if attrs["device_roles"]:
                    for _dev_role in attrs["device_roles"]:
                        _device_roles.append(ORMRole.objects.get(name=_dev_role))
                    _new_validated_software.device_roles.set(_device_roles)
            if "inventory_items" in attrs:
                if attrs["inventory_items"]:
                    for _inv_item in attrs["inventory_items"]:
                        _inventory_items.append(ORMInventoryItem.objects.get(name=_inv_item))
                    _new_validated_software.inventory_items.set(_inventory_items)
            if "object_tags" in attrs:
                if attrs["object_tags"]:
                    for _obj_tag in attrs["object_tags"]:
                        _object_tags.append(ORMTag.objects.get(name=_obj_tag))
                    _new_validated_software.object_tags.set(_object_tags)
            if "tags" in attrs:
                if attrs["tags"] is not None:
                    for _tag in attrs["tags"]:
                        _new_validated_software.tags.add(ORMTag.objects.get(name=_tag))
            _new_validated_software.validated_save()
            if METADATA_FOUND:
                metadata = add_or_update_metadata_on_object(
                    adapter=adapter,
                    obj=_new_validated_software,
                    scoped_fields=SCOPED_FIELDS_MAPPING,
                )
                metadata.validated_save()
            return super().create(adapter=adapter, ids=ids, attrs=attrs)

        def update(self, attrs):
            """Update ValidatedSoftware in Nautobot from NautobotValidatedSoftware object."""
            self.adapter.job.logger.info(f"Updating Validated Software: {self.software_version}.")

            _tags = []  # noqa: F841
            _devices = []  # noqa: F841
            _device_types = []  # noqa: F841
            _device_roles = []  # noqa: F841
            _inventory_items = []  # noqa: F841
            _object_tags = []  # noqa: F841
            try:
                _platform = ORMPlatform.objects.get(name=self.platform)
                if dlm_supports_softwarelcm():
                    _software = ORMSoftware.objects.get(version=self.software_version, device_platform=_platform)
                if core_supports_softwareversion():
                    _software = ORMSoftware.objects.get(version=self.software_version, platform=_platform)
            except ORMPlatform.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Platform ({attrs['platform']}) not found, unable to create Validated Software."
                )
                return None
            except ORMSoftware.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Software ({attrs['software_version']}) not found, unable to create Validated Software."
                )
                return None
            self.adapter.job.logger.info(f"Updating Validated Software - {self} with attrs {attrs}.")
            _update_validated_software = ORMValidatedSoftware.objects.get(
                software=_software, start=self.valid_since, end=self.valid_until
            )
            if attrs.get("preferred_version"):
                _update_validated_software.preferred_version = attrs["preferred_version"]
            if "tags" in attrs:
                _update_validated_software.tags.clear()
                if attrs["tags"] is not None:
                    for _tag in attrs["tags"]:
                        _update_validated_software.tags.add(ORMTag.objects.get(name=_tag))
            if "devices" in attrs:
                # FIXME: There might be a better way to handle this that's easier on the database.
                _update_validated_software.devices.clear()
                if attrs["devices"]:
                    for _dev in attrs["devices"]:
                        _devices.append(ORMDevice.objects.get(name=_dev))
                    _update_validated_software.devices.set(_devices)
            if "device_types" in attrs:
                # FIXME: There might be a better way to handle this that's easier on the database.
                _update_validated_software.device_types.clear()
                if attrs["device_types"]:
                    for _dev_type in attrs["device_types"]:
                        _device_types.append(ORMDeviceType.objects.get(model=_dev_type))
                    _update_validated_software.device_types.set(_device_types)
            if "device_roles" in attrs:
                # FIXME: There might be a better way to handle this that's easier on the database.
                _update_validated_software.device_roles.clear()
                if attrs["device_roles"]:
                    for _dev_role in attrs["device_roles"]:
                        _device_roles.append(ORMRole.objects.get(name=_dev_role))
                    _update_validated_software.device_roles.set(_device_roles)
            if "inventory_items" in attrs:
                # FIXME: There might be a better way to handle this that's easier on the database.
                _update_validated_software.inventory_items.clear()
                if attrs["inventory_items"]:
                    for _inv_item in attrs["inventory_items"]:
                        _inventory_items.append(ORMInventoryItem.objects.get(name=_inv_item))
                    _update_validated_software.inventory_items.set(_inventory_items)
            if "object_tags" in attrs:
                # FIXME: There might be a better way to handle this that's easier on the database.
                _update_validated_software.object_tags.clear()
                if attrs["object_tags"]:
                    for _obj_tag in attrs["object_tags"]:
                        _object_tags.append(ORMTag.objects.get(name=_obj_tag))
                    _update_validated_software.object_tags.set(_object_tags)
            if not check_sor_field(_update_validated_software):
                _update_validated_software.custom_field_data.update(
                    {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
                )
            _update_validated_software.custom_field_data.update(
                {"last_synced_from_sor": datetime.today().date().isoformat()}
            )
            _update_validated_software.validated_save()
            if METADATA_FOUND:
                metadata = add_or_update_metadata_on_object(
                    adapter=self.adapter,
                    obj=_update_validated_software,
                    scoped_fields=SCOPED_FIELDS_MAPPING,
                )
                metadata.validated_save()
            return super().update(attrs)

        def delete(self):
            """Delete ValidatedSoftware in Nautobot from NautobotValidatedSoftware object."""
            try:
                _validated_software = ORMValidatedSoftware.objects.get(id=self.uuid)
                super().delete()
                _validated_software.delete()
                return self
            except ORMValidatedSoftware.DoesNotExist as err:
                self.adapter.job.logger.warning(f"Unable to find ValidatedSoftware {self} for deletion. {err}")


class NautobotExternalIntegration(ExternalIntegration):
    """Nautobot implementation of Bootstrap ExternalIntegration model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create ExternalIntegration in Nautobot from NautobotExternalIntegration object."""
        adapter.job.logger.info(f"Creating Nautobot External Integration: {ids['name']}")
        _secrets_group = None
        if attrs.get("secrets_group"):
            _secrets_group = ORMSecretsGroup.objects.get(name=attrs["secrets_group"])
        _tags = []
        for tag in attrs["tags"]:
            _tags.append(ORMTag.objects.get(name=tag))
        new_externalintegration = ORMExternalIntegration(
            name=ids["name"],
            remote_url=attrs["remote_url"],
            timeout=attrs["timeout"],
            verify_ssl=attrs["verify_ssl"],
            secrets_group=_secrets_group,
            headers=attrs["headers"],
            http_method=attrs["http_method"],
            ca_file_path=attrs["ca_file_path"],
            extra_config=attrs["extra_config"],
            tags=_tags,
        )
        new_externalintegration.custom_field_data.update(
            {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
        )
        new_externalintegration.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_externalintegration.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=adapter, obj=new_externalintegration, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ExternalIntegration in Nautobot from NautobotExternalIntegration object."""
        self.adapter.job.logger.info(f"Updating ExternalIntegration {self.name}")
        _update_externalintegration = ORMExternalIntegration.objects.get(id=self.uuid)
        if attrs.get("remote_url"):
            _update_externalintegration.remote_url = attrs["remote_url"]
        if attrs.get("timeout"):
            _update_externalintegration.timeout = attrs["timeout"]
        if attrs.get("verify_ssl"):
            _update_externalintegration.verify_ssl = attrs["verify_ssl"]
        if attrs.get("secrets_group"):
            _secrets_group = ORMSecretsGroup.objects.get(name=attrs["secrets_group"])
            _update_externalintegration.secrets_group = _secrets_group
        if attrs.get("headers"):
            _update_externalintegration.headers = attrs["headers"]
        if attrs.get("http_method"):
            _update_externalintegration.http_method = attrs["http_method"]
        if attrs.get("ca_file_path"):
            _update_externalintegration.ca_file_path = attrs["ca_file_path"]
        if attrs.get("extra_config"):
            _update_externalintegration.extra_config = attrs["extra_config"]
        if "tags" in attrs:
            try:
                _tags = []
                for tag in attrs["tags"]:
                    _tags.append(ORMTag.objects.get(name=tag))
            except ORMTag.DoesNotExist:
                self.adapter.job.logger.warning(
                    f"Nautobot Tag {attrs['tags']} does not exist. Make sure it is created manually or defined in global_settings.yaml"
                )
        if attrs.get("tags"):
            _update_externalintegration.validated_save()
            # TODO: Probably a better way to handle this that's easier on the database.
            _update_externalintegration.tags.clear()
            for _tag in attrs["tags"]:
                _update_externalintegration.tags.add(ORMTag.objects.get(name=_tag))
        if not check_sor_field(_update_externalintegration):
            _update_externalintegration.custom_field_data.update(
                {"system_of_record": os.getenv("SYSTEM_OF_RECORD", "Bootstrap")}
            )
        _update_externalintegration.custom_field_data.update(
            {"last_synced_from_sor": datetime.today().date().isoformat()}
        )
        _update_externalintegration.validated_save()
        if METADATA_FOUND:
            metadata = add_or_update_metadata_on_object(
                adapter=self.adapter, obj=_update_externalintegration, scoped_fields=SCOPED_FIELDS_MAPPING
            )
            metadata.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete ExternalIntegration in Nautobot from NautobotExternalIntegration object."""
        self.adapter.job.logger.debug(f"Delete ExternalIntegration uuid: {self.uuid}")
        try:
            git_repo = ORMExternalIntegration.objects.get(id=self.uuid)
            super().delete()
            git_repo.delete()
            return self
        except ORMExternalIntegration.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find ExternalIntegration {self.uuid} for deletion. {err}")
