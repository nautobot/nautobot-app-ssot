"""Views implementation for SSOT Proxmox VE."""

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

from .api.serializers import SSOTProxmoxConfigSerializer
from .filters import SSOTProxmoxConfigFilterSet
from .forms import SSOTProxmoxConfigFilterForm, SSOTProxmoxConfigForm
from .models import SSOTProxmoxConfig
from .tables import SSOTProxmoxConfigTable


class SSOTProxmoxConfigUIViewSet(
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectEditViewMixin,
    ObjectChangeLogViewMixin,
    ObjectNotesViewMixin,
):  # pylint: disable=abstract-method
    """SSOTProxmoxConfig UI ViewSet."""

    queryset = SSOTProxmoxConfig.objects.all()
    table_class = SSOTProxmoxConfigTable
    filterset_class = SSOTProxmoxConfigFilterSet
    filterset_form_class = SSOTProxmoxConfigFilterForm
    form_class = SSOTProxmoxConfigForm
    serializer_class = SSOTProxmoxConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)

    breadcrumbs = Breadcrumbs(
        items={
            "list": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:config", label="SSOT Configs"),
                ModelBreadcrumbItem(model=SSOTProxmoxConfig),
            ],
            "detail": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:config", label="SSOT Configs"),
                ModelBreadcrumbItem(model=SSOTProxmoxConfig),
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
                    "proxmox_instance",
                    "default_ignore_link_local",
                    "use_clusters",
                    "sync_lxc",
                    "sync_nodes_as_devices",
                    "sync_proxmox_tags",
                    "primary_ip_sort_by",
                    "default_clustergroup_name",
                    "default_cluster_name",
                    "default_cluster_type",
                    "default_location",
                    "default_device_type",
                    "default_device_role",
                ],
            ),
            ObjectTextPanel(
                weight=200,
                section=SectionChoices.RIGHT_HALF,
                label="Proxmox VE Virtual Machine Status Mappings",
                object_field="default_vm_status_map",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
            ObjectTextPanel(
                weight=300,
                section=SectionChoices.RIGHT_HALF,
                label="Proxmox VE Virtual Machine IP Status Mappings",
                object_field="default_ip_status_map",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
        ]
    )
