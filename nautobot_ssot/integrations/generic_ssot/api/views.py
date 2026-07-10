"""API views for Generic SSoT Integration."""

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.api import NautobotModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response

from nautobot_ssot.integrations.generic_ssot import filters, models
from nautobot_ssot.integrations.generic_ssot.api import serializers
from nautobot_ssot.integrations.generic_ssot.utils import introspect_nautobot_model


class SSOTEndpointViewSet(NautobotModelViewSet):
    """API CRUD operations for SSOTEndpoint."""

    queryset = models.SSOTEndpoint.objects.all()
    serializer_class = serializers.SSOTEndpointSerializer
    filterset_class = filters.SSOTEndpointFilterSet


class SSOTSyncConfigViewSet(NautobotModelViewSet):
    """API CRUD operations for SSOTSyncConfig."""

    queryset = models.SSOTSyncConfig.objects.all()
    serializer_class = serializers.SSOTSyncConfigSerializer
    filterset_class = filters.SSOTSyncConfigFilterSet


class SSOTSyncConfigEndpointViewSet(NautobotModelViewSet):
    """API CRUD operations for SSOTSyncConfigEndpoint."""

    queryset = models.SSOTSyncConfigEndpoint.objects.all()
    serializer_class = serializers.SSOTSyncConfigEndpointSerializer
    filterset_class = filters.SSOTSyncConfigEndpointFilterSet


class SSOTFieldMappingViewSet(NautobotModelViewSet):
    """API CRUD operations for SSOTFieldMapping."""

    queryset = models.SSOTFieldMapping.objects.all()
    serializer_class = serializers.SSOTFieldMappingSerializer
    filterset_class = filters.SSOTFieldMappingFilterSet


class SSOTEndpointJoinViewSet(NautobotModelViewSet):
    """API CRUD operations for SSOTEndpointJoin."""

    queryset = models.SSOTEndpointJoin.objects.all()
    serializer_class = serializers.SSOTEndpointJoinSerializer
    filterset_class = filters.SSOTEndpointJoinFilterSet


class SSOTValueMapViewSet(NautobotModelViewSet):
    """API CRUD operations for SSOTValueMap."""

    queryset = models.SSOTValueMap.objects.all()
    serializer_class = serializers.SSOTValueMapSerializer
    filterset_class = filters.SSOTValueMapFilterSet


class SSOTDataSampleViewSet(NautobotModelViewSet):
    """API CRUD operations for SSOTDataSample."""

    queryset = models.SSOTDataSample.objects.all()
    serializer_class = serializers.SSOTDataSampleSerializer
    filterset_class = filters.SSOTDataSampleFilterSet


class ModelIntrospectionViewSet(NautobotModelViewSet):
    """API for introspecting Nautobot model fields."""

    queryset = ContentType.objects.filter(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"])
    serializer_class = serializers.SSOTSyncConfigSerializer  # placeholder
    http_method_names = ["get"]

    @action(detail=True, methods=["get"], url_path="fields")
    def fields(self, request, pk=None):
        """Return field metadata for a given ContentType."""
        try:
            ct = ContentType.objects.get(pk=pk)
        except ContentType.DoesNotExist:
            return Response({"error": "ContentType not found"}, status=404)

        fields_info = introspect_nautobot_model(ct)
        return Response({"content_type": str(ct), "fields": fields_info})
