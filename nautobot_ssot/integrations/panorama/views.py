"""Plugin UI Views."""

from nautobot.apps import ui
from nautobot.core.templatetags import helpers
from nautobot.core.views import generic, mixins
from nautobot.dcim.models import Device
from nautobot.dcim.tables import InterfaceTable

from nautobot_ssot.integrations.panorama import filters, forms, tables
from nautobot_ssot.integrations.panorama.api.serializers import LogicalGroupSerializer, VirtualSystemSerializer
from nautobot_ssot.integrations.panorama.models import LogicalGroup, VirtualSystem


class VirtualSystemUIViewSet(
    mixins.ObjectDetailViewMixin,
    mixins.ObjectListViewMixin,
    mixins.ObjectEditViewMixin,
    mixins.ObjectDestroyViewMixin,
    mixins.ObjectBulkDestroyViewMixin,
):
    """ViewSet for the VirtualSystem model."""

    filterset_class = filters.VirtualSystemFilterSet
    filterset_form_class = forms.VirtualSystemFilterForm
    form_class = forms.VirtualSystemForm
    queryset = VirtualSystem.objects.all()
    serializer_class = VirtualSystemSerializer
    table_class = tables.VirtualSystemTable
    action_buttons = ("add",)

    lookup_field = "pk"

    def _process_bulk_create_form(self, form):
        """Bulk creating (CSV import) is not supported."""
        raise NotImplementedError()

    object_detail_content = ui.ObjectDetailContent(
        panels=[
            ui.ObjectFieldsPanel(
                weight=100,
                section=ui.SectionChoices.LEFT_HALF,
                fields=["name", "system_id", "device"],
            ),
            ui.ObjectsTablePanel(
                weight=100,
                section=ui.SectionChoices.RIGHT_HALF,
                table_class=InterfaceTable,
                table_attribute="interfaces",
                related_field_name="assigned_vsys",
            ),
        ]
    )


class LogicalGroupUIViewSet(
    mixins.ObjectDetailViewMixin,
    mixins.ObjectListViewMixin,
    mixins.ObjectEditViewMixin,
    mixins.ObjectDestroyViewMixin,
    mixins.ObjectBulkDestroyViewMixin,
):
    """ViewSet for the LogicalGroup model."""

    filterset_class = filters.LogicalGroupFilterSet
    filterset_form_class = forms.LogicalGroupFilterForm
    form_class = forms.LogicalGroupForm
    queryset = LogicalGroup.objects.all()
    serializer_class = LogicalGroupSerializer
    table_class = tables.LogicalGroupTable
    action_buttons = ("add",)

    lookup_field = "pk"

    def _process_bulk_create_form(self, form):
        """Bulk creating (CSV import) is not supported."""
        raise NotImplementedError()

    class LogicalGroupObjectFieldsPanel(ui.ObjectFieldsPanel):
        """Custom ObjectFieldsPanel to render m2m fields with low cardinality.

        Without these, an ObjectsTablePanel would be required, however is unecessary for these fields.
        """

        def render_value(self, key, value, context):
            """Render m2m fields."""
            if key in ("devices", "virtual_systems"):
                return helpers.render_m2m(value.all(), "/ipam/ip-addresses/", key)
            return super().render_value(key, value, context)

    object_detail_content = ui.ObjectDetailContent(
        panels=[
            ui.ObjectFieldsPanel(
                weight=100,
                section=ui.SectionChoices.LEFT_HALF,
                fields="__all__",
            ),
            LogicalGroupObjectFieldsPanel(
                weight=100,
                label="Devices",
                section=ui.SectionChoices.RIGHT_HALF,
                fields=["devices"],
            ),
            LogicalGroupObjectFieldsPanel(
                weight=200,
                label="Virtual Systems",
                section=ui.SectionChoices.RIGHT_HALF,
                fields=["virtual_systems"],
            ),
        ]
    )


class DeviceVirtualSystemTabView(generic.ObjectView):
    """Add tab to Device view for VirtualSystem."""

    queryset = Device.objects.all()
    template_name = "nautobot_ssot_panorama/device_virtual_systems.html"


class DeviceLogicalGroupTabView(generic.ObjectView):
    """Add tab to Device view for LogicalGroup."""

    queryset = Device.objects.all()
    template_name = "nautobot_ssot_panorama/device_logical_groups.html"
