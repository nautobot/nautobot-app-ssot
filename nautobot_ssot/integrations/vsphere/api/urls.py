"""Django urlpatterns declaration for nautobot_ssot vsphere API."""

from rest_framework import routers

from nautobot_ssot.integrations.vsphere.api.views import SSOTvSphereConfigView

router = routers.DefaultRouter()

router.register("config/vsphere", SSOTvSphereConfigView)
app_name = "ssot"  # pylint: disable=invalid-name

urlpatterns = router.urls
