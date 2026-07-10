"""URL patterns for Generic SSoT Integration."""

from django.urls import path
from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_ssot.integrations.generic_ssot import views

router = NautobotUIViewSetRouter()
router.register(
    "generic-ssot/endpoints",
    views.SSOTEndpointUIViewSet,
    basename="ssotendpoint",
)
router.register("generic-ssot/sync-configs", views.SSOTSyncConfigUIViewSet, basename="ssotsyncconfig")
router.register(
    "generic-ssot/sync-config-endpoints",
    views.SSOTSyncConfigEndpointUIViewSet,
    basename="ssotsyncconfigendpoint",
)
router.register(
    "generic-ssot/field-mappings",
    views.SSOTFieldMappingUIViewSet,
    basename="ssotfieldmapping",
)
router.register(
    "generic-ssot/endpoint-joins",
    views.SSOTEndpointJoinUIViewSet,
    basename="ssotendpointjoin",
)

urlpatterns = router.urls + [
    # Primary field mapping builder (Nautobot model fields → JMESPath).
    path(
        "generic-ssot/sync-configs/<uuid:pk>/build-field-mappings/",
        views.ModelCentricMappingBuilderView.as_view(),
        name="ssotsyncconfig_build_field_mappings",
    ),
    # Model selection (workflow step, stub).
    path(
        "generic-ssot/sync-configs/<uuid:pk>/select-models/",
        views.ModelSelectionView.as_view(),
        name="ssotsyncconfig_select_models",
    ),
    # Endpoint join builder (workflow step, stub).
    path(
        "generic-ssot/sync-configs/<uuid:pk>/endpoint-joins/",
        views.EndpointJoinBuilderView.as_view(),
        name="ssotsyncconfig_endpoint_joins",
    ),
]
