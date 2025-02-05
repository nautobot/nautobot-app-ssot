"""Django urlpatterns declaration for nautobot_ssot_uisp app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter


# Uncomment the following line if you have views to import
# from nautobot_ssot_uisp import views


router = NautobotUIViewSetRouter()

# Here is an example of how to register a viewset, you will want to replace views.NautobotSsotUispUIViewSet with your viewset
# router.register("nautobot_ssot_uisp", views.NautobotSsotUispUIViewSet)


urlpatterns = [
    path("docs/", RedirectView.as_view(url=static("nautobot_ssot_uisp/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
