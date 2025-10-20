"""Views implementation for SSOT Infoblox."""

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

from .api.serializers import SSOTInfobloxConfigSerializer
from .filters import SSOTInfobloxConfigFilterSet
from .forms import SSOTInfobloxConfigFilterForm, SSOTInfobloxConfigForm
from .models import SSOTInfobloxConfig
from .tables import SSOTInfobloxConfigTable


class SSOTInfobloxConfigUIViewSet(
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectEditViewMixin,
    ObjectChangeLogViewMixin,
    ObjectNotesViewMixin,
):  # pylint: disable=abstract-method
    """SSOTInfobloxConfig UI ViewSet."""

    queryset = SSOTInfobloxConfig.objects.all()
    table_class = SSOTInfobloxConfigTable
    filterset_class = SSOTInfobloxConfigFilterSet
    filterset_form_class = SSOTInfobloxConfigFilterForm
    form_class = SSOTInfobloxConfigForm
    serializer_class = SSOTInfobloxConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)

    breadcrumbs = Breadcrumbs(
        items={
            "list": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:config", label="SSOT Configs"),
                ModelBreadcrumbItem(model=SSOTInfobloxConfig),
            ],
            "detail": [
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:dashboard", label="Single Source of Truth"),
                ViewNameBreadcrumbItem(view_name="plugins:nautobot_ssot:config", label="SSOT Configs"),
                ModelBreadcrumbItem(model=SSOTInfobloxConfig),
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
                    "infoblox_instance",
                    "default_status",
                    "infoblox_wapi_version",
                    "job_enabled",
                    "enable_sync_to_infoblox",
                    "import_subnets",
                    "import_ip_addresses",
                    "import_vlans",
                    "import_vlan_views",
                    "import_ipv4",
                    "import_ipv6",
                    "fixed_address_type",
                    "dns_record_type",
                    "infoblox_deletable_models",
                    "nautobot_deletable_models",
                ],
            ),
            ObjectTextPanel(
                weight=200,
                section=SectionChoices.RIGHT_HALF,
                label="Infoblox Sync Filters",
                object_field="infoblox_sync_filters",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
            ObjectTextPanel(
                weight=300,
                section=SectionChoices.RIGHT_HALF,
                label="Infoblox Network View Namespace Map",
                object_field="infoblox_network_view_to_namespace_map",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
            ObjectTextPanel(
                weight=400,
                section=SectionChoices.RIGHT_HALF,
                label="Infoblox Network View to DNS View Mapping",
                object_field="infoblox_dns_view_mapping",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
            ObjectTextPanel(
                weight=500,
                section=SectionChoices.RIGHT_HALF,
                label="Extensible Attributes/Custom Fields to Ignore",
                object_field="cf_fields_ignore",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
        ]
    )
