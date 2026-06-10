"""Base classes for contrib testing."""

from typing import Annotated, List, Optional
from unittest import skip
from unittest.mock import MagicMock

import nautobot.circuits.models as circuits_models
import nautobot.dcim.models as dcim_models
import nautobot.extras.models as extras_models
import nautobot.ipam.models as ipam_models
import nautobot.tenancy.models as tenancy_models
from diffsync.exceptions import ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated
from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TestCase
from nautobot.dcim.choices import InterfaceTypeChoices
from typing_extensions import TypedDict

from nautobot_ssot.contrib import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    NautobotAdapter,
    NautobotModel,
    RelationshipSideEnum,
)
from nautobot_ssot.contrib.typeddicts import (
    ContentTypeDict,
    TagDict,
    IPAddressDict,
    TenantDict,
    CustomRelationshipDict,
)




class NautobotTenant(NautobotModel):
    """A tenant model for testing the `NautobotModel` base class."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group__name", "tags")

    name: str
    description: Optional[str] = None
    tenant_group__name: Optional[str] = None
    tags: List[TagDict] = []



class NautobotTenantGroup(NautobotModel):
    """A tenant group model for testing the `NautobotModel` base class."""

    _model = tenancy_models.TenantGroup
    _modelname = "tenant_group"
    _identifiers = ("name",)
    _attributes = ("description",)
    _children = {"tenant": "tenants"}

    name: str
    description: str
    tenants: List[NautobotTenant] = []


class TagModel(NautobotModel):
    """A model for testing the 'NautobotModel' class."""

    _model = extras_models.Tag
    _identifiers = ("name",)
    _attributes = ("content_types",)

    name: str
    content_types: List[ContentTypeDict] = []



class NautobotIPAddress(NautobotModel):
    """IP Address test model."""

    _model = ipam_models.IPAddress
    _modelname = "ip_address"
    _identifiers = (
        "host",
        "mask_length",
    )
    _attributes = (
        "status__name",
        "parent__network",
        "parent__prefix_length",
    )

    host: str
    mask_length: int
    status__name: str
    parent__network: str
    parent__prefix_length: str


class NautobotInterface(NautobotModel):
    """Interface test model."""

    _model = dcim_models.Interface
    _modelname = "interface"
    _identifiers = (
        "name",
        "device__name",
    )
    _attributes = ("ip_addresses",)

    name: str
    device__name: str
    ip_addresses: List[IPAddressDict] = []


class NautobotDevice(NautobotModel):
    """Device test model."""

    _model = dcim_models.Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "primary_ip4__host",
        "primary_ip4__mask_length",
        "role__name",
    )

    name: str
    role__name: str
    primary_ip4__host: Optional[str] = None
    primary_ip4__mask_length: Optional[int] = None


class NautobotCable(NautobotModel):
    """Model for cables between device interfaces.

    Note: This model doesn't support terminating to things other than device interfaces because of the way is is
    implemented.
    """

    _model = dcim_models.Cable
    _modelname = "cable"
    _identifiers = (
        "termination_a__name",
        "termination_a__device__name",
        "termination_b__name",
        "termination_b__device__name",
    )
    _attributes = (
        "termination_a__app_label",
        "termination_a__model",
        "termination_b__app_label",
        "termination_b__model",
    )

    termination_a__app_label: str
    termination_a__model: str
    termination_a__name: str
    termination_a__device__name: str

    termination_b__app_label: str
    termination_b__model: str
    termination_b__name: str
    termination_b__device__name: str



class TenantModelCustomRelationship(NautobotModel):
    """Tenant model for testing custom relationship support."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("provider__name",)

    name: str
    provider__name: Annotated[
        Optional[str], CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.DESTINATION)
    ] = None


class ProviderModelCustomRelationship(NautobotModel):
    """Provider model for testing custom relationship support."""

    _model = circuits_models.Provider
    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = ("tenants",)

    name: str
    tenants: Annotated[
        List[TenantDict], CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.SOURCE)
    ] = []


class TenantModelCustomManyTomanyRelationship(NautobotModel):
    """Model for testing sorting custom relationships."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tenants",)

    name: str
    tenants: List[TenantDict] = []


