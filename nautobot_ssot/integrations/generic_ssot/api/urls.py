"""API URLs for Generic SSoT Integration."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_ssot.integrations.generic_ssot.api import views

router = OrderedDefaultRouter()
router.register("endpoints", views.SSOTEndpointViewSet)
router.register("sync-configs", views.SSOTSyncConfigViewSet)
router.register("sync-config-endpoints", views.SSOTSyncConfigEndpointViewSet)
router.register("field-mappings", views.SSOTFieldMappingViewSet)
router.register("endpoint-joins", views.SSOTEndpointJoinViewSet)
router.register("value-maps", views.SSOTValueMapViewSet)
router.register("data-samples", views.SSOTDataSampleViewSet)
router.register("model-introspection", views.ModelIntrospectionViewSet, basename="model-introspection")

urlpatterns = router.urls
