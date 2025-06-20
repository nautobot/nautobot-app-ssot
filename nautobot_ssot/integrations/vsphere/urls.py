"""URL patterns for nautobot-ssot-servicenow."""

from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views

router = NautobotUIViewSetRouter()
router.register("config/vsphere", viewset=views.SSOTvSphereConfigUIViewSet)

urlpatterns = router.urls
