"""URL patterns for nautobot-ssot-servicenow."""

from django.urls import path
from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views
from . import models

router = NautobotUIViewSetRouter()
router.register("config/infoblox", viewset=views.SSOTInfobloxConfigUIViewSet)

urlpatterns = [
    path(
        "config/infoblox/<uuid:pk>/changelog/",
        views.SSOTInfobloxConfigChangeLogView.as_view(),
        name="ssotinfobloxconfig_changelog",
        kwargs={"model": models.SSOTInfobloxConfig},
    ),
    path(
        "config/infoblox/<uuid:pk>/notes/",
        views.SSOTInfobloxConfigNotesView.as_view(),
        name="ssotinfobloxconfig_notes",
        kwargs={"model": models.SSOTInfobloxConfig},
    ),
]

urlpatterns += router.urls
