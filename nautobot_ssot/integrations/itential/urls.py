"""Itential SSoT URL's."""

from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_ssot.integrations.itential import views

router = NautobotUIViewSetRouter()
router.register("itential/automation-gateway", views.AutomationGatewayModelUIViewSet)

urlpatterns = router.urls
