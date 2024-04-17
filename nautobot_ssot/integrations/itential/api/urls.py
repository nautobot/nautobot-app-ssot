"""Itential SSoT API URL's."""

from nautobot.apps.api import OrderedDefaultRouter
from nautobot_ssot.integrations.itential.api import views


router = OrderedDefaultRouter()
router.register("itential/automation-gateway", views.AutomationGatewayModelViewSet)

urlpatterns = router.urls
