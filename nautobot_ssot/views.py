"""Views for nautobot_ssot."""

from nautobot.apps.views import NautobotUIViewSet

from nautobot_ssot import filters, forms, models, tables
from nautobot_ssot.api import serializers


class SyncUIViewSet(NautobotUIViewSet):
    """ViewSet for Sync views."""

    bulk_update_form_class = forms.SyncBulkEditForm
    filterset_class = filters.SyncFilterSet
    filterset_form_class = forms.SyncFilterForm
    form_class = forms.SyncForm
    lookup_field = "pk"
    queryset = models.Sync.objects.all()
    serializer_class = serializers.SyncSerializer
    table_class = tables.SyncTable
