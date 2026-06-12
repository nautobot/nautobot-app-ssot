"""Base classes for contrib testing."""



from nautobot_ssot.contrib import (
    NautobotAdapter,
)
from nautobot_ssot.tests.contrib.fixtures.models import (
    NautobotTenant,
    NautobotTenantGroup,
)


class TestAdapter(NautobotAdapter):
    """An adapter for testing the `BaseAdapter` base class."""

    top_level = ("tenant_group",)
    tenant_group = NautobotTenantGroup
    tenant = NautobotTenant


class TestNautobotAdapter(NautobotAdapter):
    """"""

    top_level = []
