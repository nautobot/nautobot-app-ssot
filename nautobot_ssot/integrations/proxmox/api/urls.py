"""Django urlpatterns declaration for nautobot_ssot Proxmox VE API."""

from rest_framework import routers

from nautobot_ssot.integrations.proxmox.api.views import SSOTProxmoxConfigView

router = routers.DefaultRouter()

router.register("config/proxmox", SSOTProxmoxConfigView)
app_name = "ssot"  # pylint: disable=invalid-name

urlpatterns = router.urls
