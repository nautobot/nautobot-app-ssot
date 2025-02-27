"""Django urlpatterns declaration for nautobot_ssot app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter


from nautobot_ssot import views


app_name = "nautobot_ssot"
router = NautobotUIViewSetRouter()

router.register("sync", views.SyncUIViewSet)


urlpatterns = [
    path("docs/", RedirectView.as_view(url=static("nautobot_ssot/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
