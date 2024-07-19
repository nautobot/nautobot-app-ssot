"""Django urlpatterns declaration for nautobot_ssot API."""

from nautobot_ssot.integrations.utils import each_enabled_integration_module

app_name = "ssot"  # pylint: disable=invalid-name
urlpatterns = []


def _add_integrations():
    for module in each_enabled_integration_module("api.urls"):
        urlpatterns.extend(module.urlpatterns)


_add_integrations()
