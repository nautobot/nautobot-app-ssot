"""Itential SSoT API URL's."""

from nautobot.apps.api import OrderedDefaultRouter
from nautobot_ssot.integrations.itential.api import views


router = OrderedDefaultRouter(view_name="Itential SSoT")
router.register("models", views.AutomationGatewayModelViewSet)

urlpatterns = router.urls
