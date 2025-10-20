"""Views implementation for SSOT vSphere."""

# pylint: disable=duplicate-code
from nautobot.apps.ui import (
    Breadcrumbs,
    ModelBreadcrumbItem,
    ObjectDetailContent,
    ObjectFieldsPanel,
    ObjectTextPanel,
    SectionChoices,
    ViewNameBreadcrumbItem,
)
from nautobot.apps.views import (
    ObjectChangeLogViewMixin,
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectEditViewMixin,
    ObjectListViewMixin,
    ObjectNotesViewMixin,
)

from .api.serializers import SSOTvSphereConfigSerializer
from .filters import SSOTvSphereConfigFilterSet
from .forms import SSOTvSphereConfigFilterForm, SSOTvSphereConfigForm
from .models import SSOTvSphereConfig
from .tables import SSOTvSphereConfigTable


class SSOTvSphereConfigUIViewSet(
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectEditViewMixin,
    ObjectChangeLogViewMixin,
    ObjectNotesViewMixin,
):  # pylint: disable=abstract-method
    """SSOTvSphereConfig UI ViewSet."""

    queryset = SSOTvSphereConfig.objects.all()
    table_class = SSOTvSphereConfigTable
    filterset_class = SSOTvSphereConfigFilterSet
    filterset_form_class = SSOTvSphereConfigFilterForm
    form_class = SSOTvSphereConfigForm
    serializer_class = SSOTvSphereConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)

    breadcrumbs = Breadcrumbs(
        items={
            "list": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:config", label="SSOT Configs"),
                ModelBreadcrumbItem(model=SSOTvSphereConfig),
            ],
            "detail": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:config", label="SSOT Configs"),
                ModelBreadcrumbItem(model=SSOTvSphereConfig),
            ],
        }
    )
    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields=[
                    "name",
                    "description",
                    "vsphere_instance",
                    "default_ignore_link_local",
                    "use_clusters",
                    "primary_ip_sort_by",
                    "sync_tagged_only",
                    "default_clustergroup_name",
                    "default_cluster_name",
                    "default_cluster_type",
                ],
            ),
            ObjectTextPanel(
                weight=200,
                section=SectionChoices.RIGHT_HALF,
                label="vSphere Virtual Machine Status Mappings",
                object_field="default_vm_status_map",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
            ObjectTextPanel(
                weight=300,
                section=SectionChoices.RIGHT_HALF,
                label="vSphere Virtual Machine IP Status Mappings",
                object_field="default_ip_status_map",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
            ObjectTextPanel(
                weight=400,
                section=SectionChoices.RIGHT_HALF,
                label="vSphere Virtual Machine Interface Status Mappings",
                object_field="default_vm_interface_map",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
        ]
    )
