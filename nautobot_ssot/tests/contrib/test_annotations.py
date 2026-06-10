"""Tests for contrib.NautobotModel."""

from typing import List, Optional
from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from nautobot.circuits import models as circuits_models
from nautobot.core.testing import TestCase
from nautobot.dcim import models as dcim_models
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras import models as extras_models
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.ipam import models as ipam_models
from nautobot.tenancy import models as tenancy_models

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.tests.contrib_base_classes import (
    NautobotTenant,
    ProviderModelCustomRelationship,
    TagDict,
    TagModel,
    TenantModelCustomRelationship,
    TestCaseWithDeviceData,
)
from nautobot_ssot.tests.test_contrib_adapter import (
    CustomRelationShipTestAdapterDestination,
    CustomRelationShipTestAdapterSource,
)


class AnnotationsSubclassingTest(TestCase):
    """Test that annotations work properly with subclassing."""

    def test_annotations_subclassing(self):
        """Test that annotations work properly with subclassing."""

        class BaseTenantModel(NautobotModel):
            """Tenant model to be subclassed."""

            _model = tenancy_models.Tenant
            _modelname = "tenant"
            _identifiers = ("name",)
            _attributes = ("tags",)

            name: str
            tags: List[TagDict]

        class Subclass(BaseTenantModel):
            """Subclassed model."""

            extra_field: Optional[str] = None

        class Adapter(NautobotAdapter):
            """Test adapter."""

            tenant = Subclass
            top_level = ["tenant"]

        tenancy_models.Tenant.objects.create(name="Test Tenant")

        adapter = Adapter(job=None)
        try:
            adapter.load()
        except KeyError as error:
            if error.args[0] == "tags":
                self.fail("Don't use `Klass.__annotations__`, prefer `typing.get_type_hints`.")
            else:
                raise error
