"""URL patterns for nautobot-ssot-servicenow."""

from django.urls import path
from nautobot.apps.urls import NautobotUIViewSetRouter

from . import models, views

router = NautobotUIViewSetRouter()
router.register("config/vsphere", viewset=views.SSOTvSphereConfigUIViewSet)

urlpatterns = [
    path(
        "config/vsphere/<uuid:pk>/changelog/",
        views.SSOTvSphereConfigChangeLogView.as_view(),
        name="ssotvsphereconfig_changelog",
        kwargs={"model": models.SSOTvSphereConfig},
    ),
    path(
        "config/vsphere/<uuid:pk>/notes/",
        views.SSOTvSphereConfigNotesView.as_view(),
        name="ssotvsphereconfig_notes",
        kwargs={"model": models.SSOTvSphereConfig},
    ),
]

urlpatterns += router.urls
