"""URL patterns for nautobot-ssot-servicenow."""

from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views

router = NautobotUIViewSetRouter()
router.register("config/infoblox", viewset=views.SSOTInfobloxConfigUIViewSet)

urlpatterns = []

urlpatterns += router.urls
