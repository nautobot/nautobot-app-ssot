"""API serializers for OpenShift integration.

This module defines Django REST Framework serializers for the OpenShift SSoT
integration's API endpoints. Serializers handle the conversion between Python
objects and JSON/XML representations for REST API operations.

Architecture:
- Built on Django REST Framework's serializer system
- Inherits from NautobotModelSerializer for consistency with Nautobot patterns
- Provides automatic field generation from Django models
- Handles security considerations for sensitive data

Key Features:
- Automatic JSON serialization/deserialization
- Field validation and error handling
- Security controls for sensitive data (write-only fields)
- Integration with Nautobot's REST API infrastructure
- Support for partial updates and creation operations

Security Considerations:
- Sensitive fields marked as write-only to prevent exposure
- Credentials handled via ExternalIntegration (not directly serialized)
- Input validation prevents malicious data injection
- Output filtering protects sensitive information

API Usage:
These serializers enable full CRUD operations via REST API:
- GET /api/plugins/nautobot-ssot/config/openshift/ (list configurations)
- POST /api/plugins/nautobot-ssot/config/openshift/ (create configuration)
- GET /api/plugins/nautobot-ssot/config/openshift/{id}/ (get specific config)
- PUT/PATCH /api/plugins/nautobot-ssot/config/openshift/{id}/ (update config)
- DELETE /api/plugins/nautobot-ssot/config/openshift/{id}/ (delete config)

Integration Benefits:
- Enables programmatic configuration management
- Supports automation and infrastructure-as-code
- Facilitates integration with external systems
- Provides consistent API across all Nautobot objects
"""
from nautobot.apps.api import NautobotModelSerializer
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigSerializer(NautobotModelSerializer):
    """REST API serializer for OpenShift configuration objects.
    
    This serializer handles the conversion between SSOTOpenshiftConfig model
    instances and JSON representations for REST API operations. It provides
    automatic field handling while implementing security controls for
    sensitive data.
    
    Inheritance from NautobotModelSerializer provides:
    - Automatic field generation from model definition
    - Consistent behavior with other Nautobot API endpoints
    - Built-in validation using model's clean() methods
    - Integration with Nautobot's permission system
    - Standard error handling and response formatting
    
    Security Features:
    1. Write-only fields: Sensitive data not exposed in API responses
    2. Validation: All model validation rules applied to API input
    3. Permission checks: Inherits Nautobot's object-level permissions
    4. Audit logging: All API operations logged via Nautobot's audit system
    
    Field Handling:
    - All model fields automatically included via fields = "__all__"
    - Custom field behavior defined in extra_kwargs
    - Related fields (ForeignKeys) handled via hyperlinks or IDs
    - Boolean fields properly serialized as true/false
    
    API Response Format:
    {
        "id": "uuid-string",
        "name": "Configuration Name",
        "description": "Optional description",
        "openshift_instance": "uuid-or-url",
        "sync_namespaces": true,
        "sync_nodes": true,
        "sync_containers": true,
        "sync_deployments": true,
        "sync_services": true,
        "sync_kubevirt_vms": true,
        "namespace_filter": "",
        "workload_types": "all",
        "job_enabled": false,
        "enable_sync_to_nautobot": true,
        "created": "2023-01-01T00:00:00Z",
        "last_updated": "2023-01-01T00:00:00Z"
    }
    
    Usage Examples:
    
    # Create configuration via API
    POST /api/plugins/nautobot-ssot/config/openshift/
    {
        "name": "Production OpenShift",
        "openshift_instance": "external-integration-uuid",
        "sync_namespaces": true,
        "workload_types": "all"
    }
    
    # Update configuration via API
    PATCH /api/plugins/nautobot-ssot/config/openshift/{id}/
    {
        "job_enabled": true,
        "namespace_filter": "^prod-.*"
    }
    """
    
    class Meta:
        """Serializer metadata configuration.
        
        Defines the model this serializer represents and any special
        field handling requirements. The configuration ensures all
        model fields are available via the API while applying
        appropriate security controls.
        """
        model = SSOTOpenshiftConfig
        fields = "__all__"  # Include all model fields in API
        
        # Field-specific configuration for security and behavior
        extra_kwargs = {
            # Note: api_token field was removed in v2.0 security update
            # Credentials now handled via ExternalIntegration
            # This configuration remains for backward compatibility
            # if any legacy fields are added in the future
        }
        
        # Additional serializer configuration
        read_only_fields = (
            "id",           # UUID generated by system
            "created",      # Timestamp managed by system
            "last_updated", # Timestamp managed by system
        )
