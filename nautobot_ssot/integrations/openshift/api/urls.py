# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""API URLs for OpenShift integration.

This module defines Django REST Framework URL routing for the OpenShift SSoT
integration's API endpoints. It uses DRF's router pattern to automatically
generate all necessary RESTful URLs from ViewSet registrations.

Architecture Overview:
- Uses rest_framework.routers.DefaultRouter for automatic URL generation
- Follows RESTful URL conventions for predictable routing patterns
- Integrates seamlessly with Nautobot's API infrastructure
- Provides complete CRUD operations via ViewSet patterns

URL Pattern Generation:
The DefaultRouter automatically creates the following URL patterns:
- GET    /api/plugins/nautobot-ssot/config/openshift/           (list configurations)
- POST   /api/plugins/nautobot-ssot/config/openshift/           (create configuration)
- GET    /api/plugins/nautobot-ssot/config/openshift/{id}/      (retrieve specific config)
- PUT    /api/plugins/nautobot-ssot/config/openshift/{id}/      (complete update)
- PATCH  /api/plugins/nautobot-ssot/config/openshift/{id}/      (partial update)
- DELETE /api/plugins/nautobot-ssot/config/openshift/{id}/      (delete configuration)
- GET    /api/plugins/nautobot-ssot/config/openshift/{id}/options/ (API metadata)

Benefits of Router Pattern:
1. Consistent URL structure across all Nautobot APIs
2. Automatic generation reduces boilerplate code and human error
3. Built-in support for standard REST operations and HTTP methods
4. Integration with Django REST Framework's advanced features
5. Automatic handling of HTTP method routing (GET, POST, PUT, DELETE)
6. Support for content negotiation and API versioning

Security Integration:
- All URLs inherit Nautobot's authentication requirements
- Permission checking handled at the ViewSet level (not URL level)
- CSRF protection enabled for state-changing operations (POST, PUT, DELETE)
- Integration with Nautobot's audit logging system for API calls

API Documentation Integration:
- Automatically generates OpenAPI/Swagger documentation
- Provides interactive API browsing via Django REST Framework's browsable API
- Facilitates integration with API clients and automation tools
- Supports API schema generation for client code generation

Router Configuration Details:
- Uses DefaultRouter (not SimpleRouter) for full REST feature support
- Includes format suffix patterns (.json, .xml, etc.)
- Generates hyperlinked API responses for resource relationships
- Provides API root view at the router's base URL
"""

from rest_framework import routers
from nautobot_ssot.integrations.openshift.api.views import SSOTOpenshiftConfigViewSet

# Initialize Django REST Framework's DefaultRouter
# DefaultRouter provides more features than SimpleRouter:
# - API root view listing all endpoints
# - Format suffix support (.json, .xml, etc.)
# - Trailing slash handling (with/without)
# - Automatic OPTIONS responses for API introspection
router = routers.DefaultRouter()

# Register the OpenShift configuration ViewSet with the router
# This creates the complete set of RESTful API endpoints for SSOTOpenshiftConfig
#
# URL Pattern Breakdown:
# - Base path: "config/openshift" 
#   - Results in: /api/plugins/nautobot-ssot/config/openshift/
#   - Follows pattern: /api/plugins/{plugin-name}/{resource-path}/
#
# - ViewSet: SSOTOpenshiftConfigViewSet
#   - Handles all CRUD operations for OpenShift configurations
#   - Includes filtering, pagination, and search capabilities
#   - Provides field-level validation and error handling
#
# Generated Endpoints:
# 1. Collection endpoints (no ID):
#    - GET /config/openshift/     → list all configurations
#    - POST /config/openshift/    → create new configuration
#
# 2. Resource endpoints (with ID):
#    - GET /config/openshift/{id}/    → retrieve specific configuration
#    - PUT /config/openshift/{id}/    → replace entire configuration
#    - PATCH /config/openshift/{id}/  → update specific fields
#    - DELETE /config/openshift/{id}/ → delete configuration
#
# 3. Metadata endpoints:
#    - OPTIONS /config/openshift/     → API schema and allowed methods
#    - HEAD /config/openshift/       → headers only (for caching)
router.register(
    "config/openshift",              # URL prefix for this resource
    SSOTOpenshiftConfigViewSet,      # ViewSet handling business logic
    basename="ssotopenshiftconfig"   # Base name for URL reversal
)

# App name for URL namespacing
# Used in URL reversal patterns and namespace resolution
# Must match the app_name used in parent URLconf inclusion
app_name = "ssot"

# Export the generated URL patterns for inclusion in the main plugin URLconf
# These patterns are included by the parent urls.py using include()
# Pattern: include('nautobot_ssot.integrations.openshift.api.urls')
urlpatterns = router.urls

# =====================================================================
# URL PATTERN EXAMPLES FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. Complete URL Examples:
#    Base URL: https://nautobot.example.com/api/plugins/nautobot-ssot/
#    
#    List configs:     GET    .../config/openshift/
#    Create config:    POST   .../config/openshift/
#    Get config:       GET    .../config/openshift/uuid-here/
#    Update config:    PATCH  .../config/openshift/uuid-here/
#    Delete config:    DELETE .../config/openshift/uuid-here/
#
# 2. Django URL Reversal:
#    from django.urls import reverse
#    
#    # List view
#    url = reverse('plugins-api:nautobot_ssot-api:ssotopenshiftconfig-list')
#    
#    # Detail view  
#    url = reverse('plugins-api:nautobot_ssot-api:ssotopenshiftconfig-detail', 
#                  args=[config_uuid])
#
# 3. API Client Usage:
#    import requests
#    
#    # List configurations
#    response = requests.get(
#        'https://nautobot.example.com/api/plugins/nautobot-ssot/config/openshift/',
#        headers={'Authorization': 'Token your-api-token'}
#    )
#    
#    # Create configuration
#    response = requests.post(
#        'https://nautobot.example.com/api/plugins/nautobot-ssot/config/openshift/',
#        json={
#            'name': 'Production OpenShift',
#            'openshift_instance': 'external-integration-uuid',
#            'sync_namespaces': True,
#            'workload_types': 'all'
#        },
#        headers={'Authorization': 'Token your-api-token'}
#    )
#
# 4. Adding New Endpoints:
#    To add custom endpoints beyond standard CRUD:
#    
#    # In views.py ViewSet:
#    @action(detail=True, methods=['post'])
#    def sync_now(self, request, pk=None):
#        # Custom action implementation
#        pass
#    
#    # Results in additional endpoint:
#    # POST /config/openshift/{id}/sync_now/
#
# =====================================================================
# INTEGRATION NOTES
# =====================================================================
#
# 1. Parent URL Configuration:
#    This module is included in the main plugin's API urls.py:
#    
#    # In nautobot_ssot/api/urls.py
#    urlpatterns = [
#        path('openshift/', include('nautobot_ssot.integrations.openshift.api.urls')),
#    ]
#
# 2. Nautobot Plugin Integration:
#    The plugin's main urls.py includes API routes:
#    
#    # In nautobot_ssot/urls.py  
#    urlpatterns = [
#        path('api/', include('nautobot_ssot.api.urls')),
#    ]
#
# 3. Authentication Integration:
#    All endpoints automatically inherit:
#    - Session authentication (for web UI)
#    - Token authentication (for API clients)
#    - Permission checking via ViewSet.permission_classes
#
# 4. Content Type Support:
#    DefaultRouter supports multiple content types:
#    - application/json (default)
#    - application/xml
#    - text/html (browsable API)
#    - Custom renderers can be added
#
# 5. Error Handling:
#    Standard HTTP status codes:
#    - 200 OK: Successful GET
#    - 201 Created: Successful POST
#    - 200 OK: Successful PUT/PATCH
#    - 204 No Content: Successful DELETE
#    - 400 Bad Request: Validation errors
#    - 401 Unauthorized: Authentication required
#    - 403 Forbidden: Insufficient permissions
#    - 404 Not Found: Resource doesn't exist
#    - 500 Internal Server Error: Unexpected errors
#
# =====================================================================
