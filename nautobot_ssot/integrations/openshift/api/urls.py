"""API URLs for OpenShift integration."""
from nautobot.core.api.routers import OrderedDefaultRouter
from nautobot_ssot.integrations.openshift.api.views import SSOTOpenshiftConfigViewSet

router = OrderedDefaultRouter()
router.register("config", SSOTOpenshiftConfigViewSet)

urlpatterns = router.urls
