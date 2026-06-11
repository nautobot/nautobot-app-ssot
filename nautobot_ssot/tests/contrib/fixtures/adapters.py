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
from nautobot_ssot.tests.contrib.fixtures.models import (
    NautobotTenant,
    NautobotTenantGroup,
    TagModel,
    NautobotIPAddress,
    NautobotInterface,
    NautobotDevice,
    NautobotCable,
    TenantModelCustomManyTomanyRelationship,
    ProviderModelCustomRelationship,
    TenantModelCustomRelationship,
)





class TestAdapter(NautobotAdapter):
    """An adapter for testing the `BaseAdapter` base class."""

    top_level = ("tenant_group",)
    tenant_group = NautobotTenantGroup
    tenant = NautobotTenant


class TestNautobotAdapter(NautobotAdapter):
    """"""

    top_level = []

    


