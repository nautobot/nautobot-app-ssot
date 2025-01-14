"""Django API urlpatterns declaration for nautobot_ssot app."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_ssot.integrations.utils import each_enabled_integration_module

urlpatterns = []
router = OrderedDefaultRouter()
# add the name of your api endpoint, usually hyphenated model name in plural, e.g. "my-model-classes"


def _add_integrations():
    for module in each_enabled_integration_module("api.urls"):
        urlpatterns.extend(module.urlpatterns)


_add_integrations()

urlpatterns += router.urls
