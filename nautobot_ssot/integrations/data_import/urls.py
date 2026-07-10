"""URLs for the Data Import integration."""

from django.urls import path
from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_ssot.integrations.data_import import views

router = NautobotUIViewSetRouter()
router.register("import-plans", views.ImportPlanUIViewSet)

urlpatterns = router.urls + [
    path(
        "import-plans/<uuid:pk>/builder/",
        views.ImportPlanBuilderView.as_view(),
        name="importplan_builder",
    ),
    path(
        "import-plans/<uuid:pk>/builder/upload-csv/",
        views.BuilderUploadCSVView.as_view(),
        name="importplan_builder_upload_csv",
    ),
    path(
        "import-plans/<uuid:pk>/builder/fetch-sample/",
        views.BuilderFetchSampleView.as_view(),
        name="importplan_builder_fetch_sample",
    ),
    path(
        "import-plans/<uuid:pk>/builder/introspect/",
        views.BuilderIntrospectView.as_view(),
        name="importplan_builder_introspect",
    ),
    path(
        "import-plans/<uuid:pk>/builder/save/",
        views.BuilderSaveView.as_view(),
        name="importplan_builder_save",
    ),
    path(
        "import-plans/<uuid:pk>/builder/dry-run/",
        views.BuilderDryRunView.as_view(),
        name="importplan_builder_dry_run",
    ),
]
