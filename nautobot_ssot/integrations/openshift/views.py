"""Views for OpenShift integration.

This module defines Django views for the OpenShift SSoT integration's web UI.
It follows Nautobot's modern ViewSet pattern and provides a full CRUD interface
for managing OpenShift configurations.

Architecture Overview:
- Uses NautobotUIViewSet pattern for consistent UI behavior
- Provides all standard operations: Create, Read, Update, Delete, List
- Includes changelog and notes functionality for audit trails
- Custom template naming for integration-specific styling

View Patterns:
- SSOTOpenshiftConfigUIViewSet: Main ViewSet with all CRUD operations
- SSOTOpenshiftConfigChangeLogView: Audit trail for configuration changes
- SSOTOpenshiftConfigNotesView: User notes and documentation

Key Features:
- Bootstrap styling via inherited templates
- Permission-based access control
- Integration with Nautobot's filtering system
- Custom template locations for branded UI
- REST API serialization support

Template Architecture:
- Custom template naming: nautobot_ssot_openshift/model_action.html
- Inherits from Nautobot base templates for consistency
- Supports action-specific layouts (list, detail, form)
- Change log and notes use detail template as base
"""
from nautobot.apps.views import (
    ObjectChangeLogViewMixin,
    ObjectDestroyViewMixin, 
    ObjectDetailViewMixin,
    ObjectEditViewMixin,
    ObjectListViewMixin,
    ObjectNotesViewMixin,
)
from nautobot.extras.views import ObjectChangeLogView, ObjectNotesView

from .api.serializers import SSOTOpenshiftConfigSerializer
from .filters import SSOTOpenshiftConfigFilterSet
from .forms import SSOTOpenshiftConfigFilterForm, SSOTOpenshiftConfigForm
from .models import SSOTOpenshiftConfig
from .tables import SSOTOpenshiftConfigTable


class SSOTOpenshiftConfigUIViewSet(
    ObjectDestroyViewMixin,      # DELETE operations
    ObjectDetailViewMixin,       # READ operations (individual objects)
    ObjectListViewMixin,         # READ operations (object lists)
    ObjectEditViewMixin,         # CREATE and UPDATE operations
    ObjectChangeLogViewMixin,    # Change history functionality
    ObjectNotesViewMixin,        # User notes functionality
):
    """Main ViewSet for OpenShift configuration CRUD operations.
    
    This ViewSet provides a complete web interface for managing OpenShift
    SSoT configurations. It follows Nautobot's modern ViewSet pattern and
    includes all standard functionality expected by users.
    
    Inheritance Pattern:
    Each mixin provides specific functionality:
    - ObjectDestroyViewMixin: Delete confirmations and bulk delete
    - ObjectDetailViewMixin: Individual object display
    - ObjectListViewMixin: Paginated lists with filtering
    - ObjectEditViewMixin: Create and edit forms
    - ObjectChangeLogViewMixin: Audit trail integration
    - ObjectNotesViewMixin: User documentation support
    
    Key Configuration:
    - queryset: Base dataset for all operations
    - table_class: Controls list view presentation
    - filterset_class: Enables filtering functionality
    - form_class: Defines create/edit interface
    - serializer_class: Enables REST API support
    
    Security:
    - Inherits Nautobot's permission system
    - Users need appropriate model permissions
    - ExternalIntegration access controlled separately
    
    User Experience:
    - Consistent with other Nautobot objects
    - Standard keyboard shortcuts and navigation
    - Context-sensitive action buttons
    - Responsive design for mobile devices
    """
    
    # =====================================================================
    # CORE CONFIGURATION - Defines the ViewSet's behavior
    # =====================================================================
    
    queryset = SSOTOpenshiftConfig.objects.all()  # Base dataset for all operations
    
    # UI Components - Define how data is presented and manipulated
    table_class = SSOTOpenshiftConfigTable                  # List view presentation
    filterset_class = SSOTOpenshiftConfigFilterSet          # Search and filtering
    filterset_form_class = SSOTOpenshiftConfigFilterForm    # Filter form UI
    form_class = SSOTOpenshiftConfigForm                    # Create/edit forms
    serializer_class = SSOTOpenshiftConfigSerializer        # REST API serialization
    
    # ViewSet behavior configuration
    lookup_field = "pk"              # Use primary key for object lookups
    action_buttons = ("add",)        # Show "Add" button in list view
    
    def get_template_name(self):
        """Determine template name based on current action.
        
        This method overrides the default template naming to use our custom
        template directory structure. It enables branded templates while
        maintaining Nautobot's template inheritance for consistency.
        
        Template Naming Convention:
        - List view: nautobot_ssot_openshift/ssotopenshiftconfig_list.html
        - Detail view: nautobot_ssot_openshift/ssotopenshiftconfig_retrieve.html  
        - Create/Edit: nautobot_ssot_openshift/ssotopenshiftconfig_update.html
        
        Benefits:
        - Custom styling and branding for OpenShift integration
        - Consistent look with other SSoT integrations
        - Ability to add integration-specific help text
        - Maintains inheritance from Nautobot base templates
        
        Returns:
            str: Template file path for current action
            
        Template Context:
        Each template receives standard Nautobot context plus:
        - object: Current configuration instance (detail/edit views)
        - object_list: Filtered configuration list (list view) 
        - form: Form instance for create/edit operations
        - filter: Filter form for search functionality
        """
        action = self.action
        app_label = "nautobot_ssot_openshift"  # Custom template directory
        model_opts = self.queryset.model._meta
        
        # Action-specific template selection
        if action in ["create", "update"]:
            # Both create and update use the same form template
            template_name = f"{app_label}/{model_opts.model_name}_update.html"
        elif action == "retrieve":
            # Individual object detail view
            template_name = f"{app_label}/{model_opts.model_name}_retrieve.html"
        elif action == "list":
            # Paginated list with filtering
            template_name = f"{app_label}/{model_opts.model_name}_list.html"
        else:
            # Fallback to parent class for any unexpected actions
            template_name = super().get_template_name()

        return template_name
    
    def get_extra_context(self, request, instance=None):
        """Add extra context variables to template rendering.
        
        This method allows injection of additional context variables
        that templates can use for enhanced functionality or display.
        
        Args:
            request: Current HTTP request object
            instance: Current object instance (None for list views)
            
        Returns:
            dict: Additional context variables for templates
            
        Potential Context Additions:
        - Integration status information
        - Related object counts
        - External links and documentation
        - Feature availability flags
        """
        context = super().get_extra_context(request, instance)
        
        # Add OpenShift-specific context for templates
        if instance:
            # For detail views, add related information
            context.update({
                "sync_jobs_url": "/plugins/nautobot-ssot/jobs/",
                "openshift_docs_url": "https://docs.openshift.com/",
                "has_external_integration": bool(instance.openshift_instance),
                "sync_options_enabled": instance.get_enabled_sync_options(),
                "is_ready_for_sync": instance.is_ready_for_sync(),
            })
        
        return context


class SSOTOpenshiftConfigChangeLogView(ObjectChangeLogView):
    """Change log view for OpenShift configurations.
    
    This view provides audit trail functionality, showing all changes made
    to OpenShift configurations over time. It's essential for compliance
    and troubleshooting configuration issues.
    
    Features:
    - Complete change history with timestamps
    - User attribution for all changes
    - Before/after value comparisons
    - Integration with Nautobot's audit system
    
    Template Integration:
    Uses the detail view template as a base to provide consistent
    navigation and layout while adding change-specific content.
    
    Usage:
    Accessible from configuration detail pages via "Change Log" button.
    Provides chronological view of all modifications to the configuration.
    """
    
    # Use detail template as base for consistent layout and navigation
    base_template = "nautobot_ssot_openshift/ssotopenshiftconfig_retrieve.html"


class SSOTOpenshiftConfigNotesView(ObjectNotesView):
    """Notes view for OpenShift configurations.
    
    This view allows users to add documentation, troubleshooting notes,
    and other information to OpenShift configurations. It's valuable for
    team collaboration and knowledge sharing.
    
    Features:
    - Markdown support for rich text formatting
    - User attribution and timestamps
    - Version history for note changes
    - Search functionality across all notes
    
    Template Integration:
    Uses the detail view template as a base to provide consistent
    navigation while adding note-specific functionality.
    
    Usage:
    Accessible from configuration detail pages via "Notes" button.
    Supports collaborative documentation and troubleshooting information.
    """
    
    # Use detail template as base for consistent layout and navigation
    base_template = "nautobot_ssot_openshift/ssotopenshiftconfig_retrieve.html"
