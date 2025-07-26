"""URL patterns for OpenShift integration."""
from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views

router = NautobotUIViewSetRouter()
router.register("config/openshift", viewset=views.SSOTOpenshiftConfigUIViewSet)

urlpatterns = router.urls
