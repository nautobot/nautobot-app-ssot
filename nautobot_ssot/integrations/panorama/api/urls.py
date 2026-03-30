"""Django API urlpatterns declaration for firewall model plugin."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_ssot.integrations.panorama.api import views

router = OrderedDefaultRouter()
router.register("virtual-system", views.VirtualSystemViewSet)
router.register("logical-group", views.LogicalGroupViewSet)

urlpatterns = router.urls
