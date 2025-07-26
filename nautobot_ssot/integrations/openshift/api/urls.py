"""API URLs for OpenShift integration."""
from rest_framework import routers
from nautobot_ssot.integrations.openshift.api.views import SSOTOpenshiftConfigViewSet

router = routers.DefaultRouter()
router.register("config/openshift", SSOTOpenshiftConfigViewSet)
app_name = "ssot"

urlpatterns = router.urls
