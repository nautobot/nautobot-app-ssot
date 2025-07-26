"""Forms for OpenShift integration.

This module defines Django forms for creating, editing, and filtering OpenShift
SSoT configurations. The forms follow Nautobot's UI patterns and include proper
validation, help text, and Bootstrap styling.

Security Notes:
- Credentials are handled via ExternalIntegration, not directly in these forms
- Form validation works with model validation to ensure data integrity
- Bootstrap styling provides consistent UI/UX with other Nautobot forms

Form Architecture:
- SSOTOpenshiftConfigForm: Main configuration form for create/edit operations
- SSOTOpenshiftConfigFilterForm: Search and filtering form for list views

Key Features:
- Bootstrap integration for consistent styling
- Model-based validation with custom clean methods
- Help text and field organization for user guidance
- Integration with Django's form handling framework
"""
from django import forms
from nautobot.core.forms import BootstrapMixin
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigForm(BootstrapMixin, forms.ModelForm):
    """Form for creating and editing OpenShift SSoT configurations.
    
    This form provides the user interface for configuring OpenShift
    synchronization settings. It inherits from BootstrapMixin to ensure
    consistent styling with other Nautobot forms.
    
    Key Design Decisions:
    1. Uses ModelForm for automatic field generation from model
    2. Bootstrap styling for consistent UI appearance
    3. Custom widgets for better user experience (textarea for description)
    4. All model fields included - granular control over sync options
    
    Security Considerations:
    - Credentials handled via ExternalIntegration field (foreign key)
    - No direct credential fields in this form
    - Form validation delegates to model's clean() method
    
    User Experience Features:
    - Multi-line description field for detailed explanations
    - Help text from model fields guides user input
    - Logical field grouping via model field organization
    - Bootstrap styling for professional appearance
    
    Usage:
        # In views.py
        form = SSOTOpenshiftConfigForm(request.POST or None, instance=config)
        if form.is_valid():
            config = form.save()
    """
    
    class Meta:
        """Form metadata configuration.
        
        Defines which model this form represents and how fields should
        be rendered. Uses "__all__" to include all model fields automatically,
        ensuring the form stays in sync with model changes.
        """
        model = SSOTOpenshiftConfig
        fields = "__all__"  # Include all model fields automatically
        
        # Custom widgets for improved user experience
        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 3,  # Multi-line description field
                "placeholder": "Optional description of this configuration's purpose...",
            }),
            "namespace_filter": forms.TextInput(attrs={
                "placeholder": "^prod-.*|^staging-.* (regex pattern, leave empty for all)",
            }),
        }
        
        # Field ordering for logical grouping in the UI
        # Groups related fields together for better user experience
        field_order = [
            # Basic identification
            "name",
            "description", 
            
            # Connection configuration
            "openshift_instance",
            
            # Sync options - what to synchronize
            "sync_namespaces",
            "sync_nodes", 
            "sync_containers",
            "sync_deployments",
            "sync_services",
            "sync_kubevirt_vms",
            
            # Filtering and workload type options
            "namespace_filter",
            "workload_types",
            
            # Job control flags
            "job_enabled",
            "enable_sync_to_nautobot",
        ]
    
    def __init__(self, *args, **kwargs):
        """Initialize the form with enhanced field configuration.
        
        Customize field behavior beyond what's possible in Meta class.
        Add dynamic help text, conditional field enabling, and other
        runtime form modifications.
        
        Args:
            *args: Positional arguments passed to parent form
            **kwargs: Keyword arguments passed to parent form
        """
        super().__init__(*args, **kwargs)
        
        # Enhance field help text with dynamic information
        if "openshift_instance" in self.fields:
            self.fields["openshift_instance"].help_text = (
                "Select the External Integration containing OpenShift connection details. "
                "The integration must have a SecretsGroup with REST credentials configured. "
                "Create a new External Integration if none exist for your OpenShift cluster."
            )
        
        # Add CSS classes for enhanced styling
        if "namespace_filter" in self.fields:
            self.fields["namespace_filter"].widget.attrs.update({
                "class": "form-control font-monospace",  # Monospace for regex patterns
            })
    
    def clean(self):
        """Perform form-level validation.
        
        This method provides additional validation beyond individual field
        validation. It can check field combinations and business logic
        that spans multiple fields.
        
        Returns:
            dict: Cleaned form data
            
        Raises:
            ValidationError: If form data violates business rules
        """
        cleaned_data = super().clean()
        
        # Example: Could add form-level validation here
        # For now, model's clean() method handles all validation
        
        return cleaned_data


class SSOTOpenshiftConfigFilterForm(BootstrapMixin, forms.Form):
    """Filter form for OpenShift configuration list views.
    
    This form provides search and filtering capabilities for the list view
    of OpenShift configurations. It allows users to quickly find specific
    configurations in environments with many defined integrations.
    
    Features:
    - Text search across multiple fields
    - Specific field filters for targeted searching
    - Bootstrap styling for consistency
    - Lightweight design for responsive filtering
    
    Filter Capabilities:
    - q: General search across name and description
    - name: Exact or partial name matching
    
    Usage:
        # In views.py
        filter_form = SSOTOpenshiftConfigFilterForm(request.GET)
        if filter_form.is_valid():
            queryset = apply_filters(queryset, filter_form.cleaned_data)
    """
    
    # General search field - searches across multiple model fields
    q = forms.CharField(
        required=False, 
        label="Search",
        widget=forms.TextInput(attrs={
            "placeholder": "Search configurations...",
            "class": "form-control",
        }),
        help_text="Search across configuration names and descriptions"
    )
    
    # Specific field filters for targeted searching
    name = forms.CharField(
        required=False,
        label="Configuration Name",
        widget=forms.TextInput(attrs={
            "placeholder": "Filter by name...",
            "class": "form-control",
        }),
        help_text="Filter by configuration name (partial matches supported)"
    )
    
    def __init__(self, *args, **kwargs):
        """Initialize the filter form.
        
        Set up any dynamic behavior or field modifications needed
        for the filtering interface.
        
        Args:
            *args: Positional arguments passed to parent form
            **kwargs: Keyword arguments passed to parent form
        """
        super().__init__(*args, **kwargs)
        
        # All filter fields are optional - provide clear UX
        for field in self.fields.values():
            field.required = False
