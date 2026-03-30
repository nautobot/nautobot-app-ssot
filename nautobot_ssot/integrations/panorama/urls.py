"""Plugin URLS."""

from django.urls import path
from nautobot.core.views.routers import NautobotUIViewSetRouter
from nautobot.extras.views import ObjectChangeLogView, ObjectNotesView

from nautobot_ssot.integrations.panorama.models import LogicalGroup, VirtualSystem
from nautobot_ssot.integrations.panorama.views import (
    DeviceLogicalGroupTabView,
    DeviceVirtualSystemTabView,
    LogicalGroupUIViewSet,
    VirtualSystemUIViewSet,
)

router = NautobotUIViewSetRouter()
router.register("virtual-system", VirtualSystemUIViewSet)
router.register("logical-group", LogicalGroupUIViewSet)
urlpatterns = [
    path(
        "virtual-system/<uuid:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="virtualsystem_changelog",
        kwargs={"model": VirtualSystem},
    ),
    path(
        "virtual-system/<uuid:pk>/notes/",
        ObjectNotesView.as_view(),
        name="virtualsystem_notes",
        kwargs={"model": VirtualSystem},
    ),
    path(
        "virtual-system/<uuid:pk>/device/",
        DeviceVirtualSystemTabView.as_view(),
        name="virtualsystem_device_tab",
    ),
    path(
        "logical-group/<uuid:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="logicalgroup_changelog",
        kwargs={"model": LogicalGroup},
    ),
    path(
        "logical-group/<uuid:pk>/notes/",
        ObjectNotesView.as_view(),
        name="logicalgroup_notes",
        kwargs={"model": LogicalGroup},
    ),
    path(
        "logical-group/<uuid:pk>/device/",
        DeviceLogicalGroupTabView.as_view(),
        name="logicalgroup_device_tab",
    ),
]
urlpatterns += router.urls
