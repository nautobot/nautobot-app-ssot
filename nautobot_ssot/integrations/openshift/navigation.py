"""OpenShift SSoT Navigation.

This module defines the navigation menu items for the OpenShift Single Source of Truth
integration. It integrates with Nautobot's navigation system to provide seamless access
to OpenShift configuration management through the main UI.

Navigation Architecture:
- Integrates with Nautobot's plugin navigation system
- Uses permission-based access control for security
- Follows consistent UI patterns with other SSoT integrations
- Provides direct access to configuration management interface

Design Patterns:
- NavMenuItem: Nautobot's standard navigation component
- Permission-based visibility: Only shows to authorized users
- URL reversal: Uses Django's URL naming for maintainability
- Hierarchical organization: Fits within SSoT plugin structure

User Experience:
- Located under SSoT section in main navigation
- Clear naming convention: "OpenShift Configurations"
- Intuitive access to primary configuration interface
- Consistent with other integration navigation patterns

Integration Points:
- Links to configuration list view (primary entry point)
- Permission checks ensure secure access
- Follows Nautobot's navigation rendering pipeline
- Supports both authenticated and role-based access
"""

from nautobot.apps.ui import NavMenuItem

# Navigation items exported to Nautobot's navigation system
# These items are automatically integrated into the main UI navigation
nav_items = [
    NavMenuItem(
        # Primary navigation link to OpenShift configuration management
        # Uses Django URL reversal for maintainability and consistency
        link="plugins:nautobot_ssot:openshift:config_list",
        
        # User-facing navigation label
        # Follows naming convention: "<Integration> Configurations"
        name="OpenShift Configurations",
        
        # Permission-based access control
        # Users need view permission for SSOTOpenshiftConfig model
        # This ensures secure access to configuration management
        permissions=["nautobot_ssot.view_ssotopenshiftconfig"],
    ),
]

# Navigation Integration Notes for Maintenance:
#
# 1. URL Pattern Dependency:
#    - The link depends on urls.py having 'config_list' named URL
#    - Pattern: "plugins:nautobot_ssot:openshift:config_list"
#    - Must stay synchronized with URL configuration
#
# 2. Permission Model:
#    - Permission string format: "app_label.permission_model"
#    - Uses Django's model-level permissions
#    - Permission created automatically by Django migrations
#    - Can be extended with custom permissions if needed
#
# 3. Navigation Hierarchy:
#    - This appears under the "SSoT" plugin section
#    - Nautobot automatically groups by plugin
#    - Order determined by plugin loading and alphabetical sorting
#
# 4. Extension Points:
#    - Additional NavMenuItem objects can be added to nav_items list
#    - Can include sub-menus for different OpenShift functions
#    - Can add conditional navigation based on configuration state
#
# 5. UI Integration:
#    - Nautobot automatically renders these in the main navigation
#    - Supports responsive design and mobile navigation
#    - Integrates with user's theme and accessibility settings 