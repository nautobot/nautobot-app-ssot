"""Filters for OpenShift integration.

This module defines Django filtering capabilities for the OpenShift SSoT
integration. It provides search and filtering functionality for the configuration
list views, enabling users to quickly find specific configurations in environments
with many OpenShift integrations.

Architecture:
- Built on django-filter framework for declarative filtering
- Inherits from NautobotFilterSet for consistency with Nautobot patterns
- Provides both general search and specific field filtering
- Integrates with Django Q objects for complex query construction

Key Features:
- Text search across configuration names
- Automatic field filtering for all model fields
- Case-insensitive search for user-friendly behavior
- Integration with list view pagination and sorting
- Responsive filtering with AJAX support (via Nautobot framework)

Performance Considerations:
- Uses database indexes for efficient text searching
- Limits search to essential fields to avoid performance impact
- Leverages Django ORM query optimization
- Supports pagination to handle large configuration lists

User Experience:
- Simple text search box for quick filtering
- Individual field filters for precise results
- Real-time filtering feedback in the UI
- Clear search terms and filter state management
"""
import django_filters
from django.db.models import Q
from nautobot.apps.filters import NautobotFilterSet

from .models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigFilterSet(NautobotFilterSet):
    """Filter set for OpenShift configuration list views.
    
    This FilterSet provides comprehensive filtering capabilities for OpenShift
    configurations, allowing users to quickly locate specific configurations
    in environments with multiple cluster integrations.
    
    Inheritance from NautobotFilterSet provides:
    - Consistent behavior with other Nautobot object filters
    - Automatic form generation for filter UI
    - Integration with Nautobot's pagination system
    - Standard query parameter handling
    - Built-in performance optimizations
    
    Filtering Capabilities:
    1. General Search (q parameter):
       - Searches across configuration names
       - Case-insensitive for user convenience
       - Uses database ILIKE for efficient substring matching
    
    2. Automatic Field Filters:
       - All model fields available for filtering
       - Supports exact matches and Django field lookups
       - Boolean fields provide checkbox filtering
       - Foreign key fields offer dropdown selection
    
    Usage in Views:
        filterset = SSOTOpenshiftConfigFilterSet(
            request.GET, 
            queryset=SSOTOpenshiftConfig.objects.all()
        )
        filtered_configs = filterset.qs
    
    URL Parameter Examples:
    - ?q=production (search for "production" in names)
    - ?job_enabled=true (only enabled configurations)
    - ?workload_types=vms (only VM synchronization configs)
    """
    
    # General search filter - searches across multiple fields
    # Uses custom search method for multi-field searching
    q = django_filters.CharFilter(
        method="search", 
        label="Search",
        help_text="Search configuration names (case-insensitive)"
    )
    
    class Meta:
        """FilterSet metadata configuration.
        
        Defines the model this filter operates on and which fields
        are available for filtering. Using "__all__" ensures the
        filter stays synchronized with model field changes.
        """
        model = SSOTOpenshiftConfig
        fields = "__all__"  # Enable filtering on all model fields
    
    def search(self, queryset, _name, value):
        """Perform general text search across configuration fields.
        
        This method implements the search functionality for the 'q' parameter,
        providing user-friendly text searching across relevant model fields.
        
        Args:
            queryset: Base queryset to filter
            _name: Filter field name (unused - required by django-filter)
            value: Search term entered by user
            
        Returns:
            QuerySet: Filtered queryset matching search criteria
            
        Search Strategy:
        - Searches configuration names for substring matches
        - Case-insensitive using icontains lookup
        - Handles empty/whitespace-only queries gracefully
        - Could be extended to search additional fields
        
        Performance Notes:
        - Uses database-level text matching for efficiency
        - Leverages database indexes on name field
        - Returns original queryset for empty searches (no filtering overhead)
        
        Future Extensions:
        - Could add description field to search scope
        - Could implement full-text search for complex queries
        - Could add search result ranking/scoring
        """
        # Handle empty or whitespace-only search terms
        if not value.strip():
            return queryset
        
        # Perform case-insensitive substring search on configuration names
        # Using Q objects allows for future expansion to multiple fields
        return queryset.filter(
            Q(name__icontains=value)  # Case-insensitive name search
        )
        
        # Future enhancement: multi-field search
        # return queryset.filter(
        #     Q(name__icontains=value) |
        #     Q(description__icontains=value) |
        #     Q(openshift_instance__name__icontains=value)
        # )
