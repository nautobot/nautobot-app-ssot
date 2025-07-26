"""Filters for OpenShift integration."""
import django_filters
from django.db.models import Q
from nautobot.apps.filters import NautobotFilterSet

from .models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigFilterSet(NautobotFilterSet):
    """FilterSet for SSOTOpenshiftConfig model."""
    
    q = django_filters.CharFilter(method="search", label="Search")
    
    class Meta:
        """Meta attributes for filter."""
        model = SSOTOpenshiftConfig
        fields = "__all__"
    
    def search(self, queryset, _name, value):
        """String search of SSOTOpenshiftConfig records."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value))
