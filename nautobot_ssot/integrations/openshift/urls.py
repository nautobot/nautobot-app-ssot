# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""URL patterns for OpenShift integration.

This module defines Django URL routing for the OpenShift SSoT integration's
web interface. It uses Nautobot's modern ViewSet router pattern to automatically
generate all necessary CRUD URLs from a single ViewSet registration.

Architecture:
- Uses NautobotUIViewSetRouter for automatic URL generation
- Follows RESTful URL conventions for predictable routing
- Integrates with Nautobot's navigation and permission systems
- Provides all standard CRUD operations via ViewSet patterns

URL Pattern Generation:
The router automatically creates the following URL patterns:
- /plugins/nautobot-ssot/config/openshift/           (list view)
- /plugins/nautobot-ssot/config/openshift/add/       (create view)
- /plugins/nautobot-ssot/config/openshift/<uuid>/    (detail view)
- /plugins/nautobot-ssot/config/openshift/<uuid>/edit/     (update view)
- /plugins/nautobot-ssot/config/openshift/<uuid>/delete/   (delete view)
- /plugins/nautobot-ssot/config/openshift/<uuid>/changelog/ (audit trail)
- /plugins/nautobot-ssot/config/openshift/<uuid>/notes/    (user notes)

Benefits of ViewSet Router Pattern:
1. Consistent URL structure across all Nautobot integrations
2. Automatic generation reduces boilerplate code
3. Built-in support for standard REST operations
4. Integration with Nautobot's permission decorators
5. Automatic handling of HTTP method routing (GET, POST, PUT, DELETE)

Security Considerations:
- All URLs inherit Nautobot's authentication requirements
- Permission checking handled at the ViewSet level
- CSRF protection enabled for state-changing operations
- Integration with Nautobot's audit logging system

Navigation Integration:
- URLs are accessible via Nautobot's plugin navigation
- Breadcrumb generation follows standard patterns
- Back-button and browser history work correctly
- Deep linking supported for bookmarking
"""
from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views

# Initialize Nautobot's ViewSet router for automatic URL generation
# This router understands Nautobot's patterns and creates all necessary URLs
router = NautobotUIViewSetRouter()

# Register the OpenShift configuration ViewSet with the router
# URL Pattern: /plugins/nautobot-ssot/config/openshift/
# The router will generate all CRUD URLs from this single registration:
#
# Generated URLs:
# - GET  /config/openshift/           -> List all configurations
# - GET  /config/openshift/add/       -> Show create form
# - POST /config/openshift/add/       -> Process create form
# - GET  /config/openshift/<uuid>/    -> Show configuration details
# - GET  /config/openshift/<uuid>/edit/ -> Show edit form
# - POST /config/openshift/<uuid>/edit/ -> Process edit form
# - GET  /config/openshift/<uuid>/delete/ -> Show delete confirmation
# - POST /config/openshift/<uuid>/delete/ -> Process deletion
# - GET  /config/openshift/<uuid>/changelog/ -> Show change history
# - GET  /config/openshift/<uuid>/notes/ -> Show/edit user notes
router.register(
    "config/openshift",  # Base URL pattern within the plugin
    viewset=views.SSOTOpenshiftConfigUIViewSet  # ViewSet providing all operations
)

# Export the generated URL patterns for inclusion in parent URLconf
# These URLs will be included by the main SSoT plugin URL configuration
urlpatterns = router.urls
