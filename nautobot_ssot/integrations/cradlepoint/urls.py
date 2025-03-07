"""URL patterns for SSOT Cradlepoint."""

from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views

router = NautobotUIViewSetRouter()
router.register("config/cradlepoint", viewset=views.SSOTCradlepointConfigUIViewSet)

urlpatterns = router.urls
