"""URL patterns for nautobot_ssot Proxmox VE integration."""

from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views

router = NautobotUIViewSetRouter()
router.register("config/proxmox", viewset=views.SSOTProxmoxConfigUIViewSet)

urlpatterns = router.urls
