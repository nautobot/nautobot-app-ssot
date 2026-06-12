"""Tests for contrib.NautobotModel."""

from typing import List, Optional

from nautobot.core.testing import TestCase
from nautobot.tenancy import models as tenancy_models

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.tests.contrib_base_classes import (
    TagDict,
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
