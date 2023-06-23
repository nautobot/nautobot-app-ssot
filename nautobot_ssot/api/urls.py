"""API URL paths for SSoT."""
from nautobot.core.api.routers import OrderedDefaultRouter

from nautobot_ssot.api import views


router = OrderedDefaultRouter()
router.APIRootView = views.SSOTRootView
router.register("syncs", views.SyncViewSet)
router.register("logs", views.SyncLogEntryViewSet)
urlpatterns = router.urls
