"""Django urlpatterns declaration for nautobot_ssot infoblox API."""

from rest_framework import routers

from nautobot_ssot.integrations.infoblox.api.views import SSOTInfobloxConfigView

router = routers.DefaultRouter()

router.register("config/infoblox", SSOTInfobloxConfigView)
app_name = "ssot"  # pylint: disable=invalid-name

urlpatterns = router.urls
