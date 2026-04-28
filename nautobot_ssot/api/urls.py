"""Django API urlpatterns declaration for nautobot_ssot app."""

from django.urls import path

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_ssot.api import views
from nautobot_ssot.integrations.utils import each_enabled_integration_module

urlpatterns = [
    # Scoped sync trigger — POST a scope + flags, get back diff+sync stats.
    # See nautobot_ssot.api.views.ScopedSyncTrigger for the contract.
    path("sync/scoped/", views.ScopedSyncTrigger.as_view(), name="scoped-sync-trigger"),
]
router = OrderedDefaultRouter()

router.register("history", views.SyncViewSet)
router.register("logs", views.SyncLogEntryViewSet)


def _add_integrations():
    for module in each_enabled_integration_module("api.urls"):
        urlpatterns.extend(module.urlpatterns)


_add_integrations()

app_name = "nautobot_ssot-api"
urlpatterns += router.urls
