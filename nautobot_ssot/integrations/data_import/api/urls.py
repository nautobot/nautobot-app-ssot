"""API urls for the Data Import integration."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_ssot.integrations.data_import.api.views import ImportPlanViewSet

router = OrderedDefaultRouter()
router.register("import-plans", ImportPlanViewSet)

urlpatterns = router.urls
