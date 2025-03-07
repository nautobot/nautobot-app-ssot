"""Django urlpatterns declaration for SSOT Cardlepoint vsphere API."""

from rest_framework import routers

from nautobot_ssot.integrations.cradlepoint.api.views import SSOTCradlepointConfigView

router = routers.DefaultRouter()

router.register("config/cradlepoint", SSOTCradlepointConfigView)
app_name = "ssot"  # pylint: disable=invalid-name

urlpatterns = router.urls
