# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""Base DiffSync models for OpenShift integration.

This module defines the foundational DiffSync models for OpenShift resource
synchronization. It provides base classes and mixins that establish common
patterns for representing OpenShift resources in the DiffSync framework.

DiffSync Architecture Overview:
- DiffSync uses models to represent data from both source and target systems
- Models define identifiers (unique keys) and attributes (synchronized fields)
- The DiffSync engine compares models to calculate differences
- Adapters implement create/update/delete operations based on differences

OpenShift Resource Modeling:
- All OpenShift resources share common Kubernetes metadata (name, UUID, labels, annotations)
- Resources have hierarchical relationships (namespaces contain pods, etc.)
- Resource status and specifications are separated in Kubernetes API
- Custom Resource Definitions (CRDs) extend the base Kubernetes object model

Key Design Patterns:
1. Mixin Pattern: OpenshiftBaseMixin provides common Kubernetes metadata
2. Inheritance: Specific resources inherit from both mixin and DiffSyncModel
3. Type Hints: Full typing support for IDE assistance and validation
4. Identifier Strategy: Uses meaningful business keys rather than UUIDs
5. Attribute Separation: Clear distinction between identifiers and synchronized data

Maintenance Notes:
- Keep _identifiers and _attributes in sync with actual model fields
- Use Optional types for fields that may not be present in all OpenShift versions
- Consider backward compatibility when adding new fields
- Follow Kubernetes API conventions for field naming
"""

import uuid
from typing import Optional, List, Dict, Any
from diffsync import DiffSyncModel


class OpenshiftBaseMixin:
    """Base mixin providing common Kubernetes metadata for OpenShift resources.
    
    This mixin implements the standard Kubernetes object metadata pattern that
    is shared across all resources in the OpenShift/Kubernetes ecosystem. It
    provides the foundational fields that every Kubernetes object contains.
    
    Kubernetes Object Structure:
    - metadata.name: Human-readable identifier within namespace
    - metadata.uid: System-generated unique identifier (UUID)
    - metadata.labels: Key-value pairs for organization and selection
    - metadata.annotations: Key-value pairs for arbitrary metadata
    
    DiffSync Integration:
    - Provides common field definitions for consistency
    - Implements utility methods for identifier creation
    - Ensures all OpenShift models follow Kubernetes conventions
    - Supports both namespaced and cluster-scoped resources
    
    Usage Pattern:
        class MyResource(OpenshiftBaseMixin, DiffSyncModel):
            _modelname = "my_resource"
            _identifiers = ("name",)  # Use name as primary identifier
            _attributes = ("labels", "annotations", "custom_field")
            
            custom_field: str = ""
    """
    
    # Core Kubernetes metadata fields present on all resources
    # These fields follow the standard Kubernetes object metadata schema
    
    # Human-readable name, unique within namespace (for namespaced resources)
    # or unique within cluster (for cluster-scoped resources)
    # Examples: "web-server-pod", "production-namespace", "worker-node-01"
    name: str
    
    # System-generated unique identifier (UUID) assigned by Kubernetes
    # Immutable and globally unique across the entire cluster
    # Used for internal references and ensuring object identity
    uuid: uuid.UUID
    
    # Labels: Key-value pairs used for organization, selection, and querying
    # Examples: {"app": "web", "env": "prod", "version": "v1.2.3"}
    # Used by selectors, services, and operational tooling
    labels: Optional[Dict[str, str]] = {}
    
    # Annotations: Key-value pairs for arbitrary metadata storage
    # Examples: {"deployment.kubernetes.io/revision": "3", "description": "Web frontend"}
    # Used for documentation, tooling metadata, and configuration
    annotations: Optional[Dict[str, str]] = {}
    
    @classmethod
    def create_unique_id(cls, **kwargs) -> str:
        """Create a unique identifier for DiffSync model instances.
        
        This method generates a consistent unique identifier for model instances
        based on available data. It follows a fallback strategy to handle cases
        where some identifier fields may not be available.
        
        Identifier Strategy:
        1. Prefer UUID if available (most unique and stable)
        2. Fall back to name if UUID not available
        3. Return empty string if neither available (should be rare)
        
        Args:
            **kwargs: Model field values for identifier creation
            
        Returns:
            str: Unique identifier string for the model instance
            
        Usage:
            # In adapter loading logic:
            unique_id = OpenshiftProject.create_unique_id(
                uuid="550e8400-e29b-41d4-a716-446655440000",
                name="production"
            )
            # Returns: "550e8400-e29b-41d4-a716-446655440000"
        """
        # Try UUID first as it's globally unique and immutable
        if "uuid" in kwargs and kwargs["uuid"]:
            return str(kwargs["uuid"])
        
        # Fall back to name as secondary identifier
        if "name" in kwargs and kwargs["name"]:
            return str(kwargs["name"])
        
        # Last resort - should rarely happen in practice
        return ""


class OpenshiftProject(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model representing OpenShift projects (Kubernetes namespaces).
    
    Projects in OpenShift are an extension of Kubernetes namespaces that provide
    additional organizational and security features. They serve as the primary
    isolation boundary for resources and provide multi-tenancy within clusters.
    
    OpenShift Project Features:
    - Extends Kubernetes namespaces with additional metadata
    - Provides display names and descriptions for human readability
    - Supports resource quotas and limits for capacity management
    - Integrates with OpenShift's RBAC and security model
    
    Nautobot Mapping:
    - Projects map to Nautobot Tenant objects
    - Provides organizational hierarchy for other synchronized resources
    - Display names become tenant names in Nautobot
    - Descriptions and labels provide additional context
    
    DiffSync Configuration:
    - Uses project name as unique identifier (unique within cluster)
    - Synchronizes display metadata and organizational information
    - Excludes runtime status that changes frequently
    """
    
    # DiffSync model configuration
    _modelname = "openshift_project"
    
    # Use name as the primary identifier since project names are unique cluster-wide
    _identifiers = ("name",)
    
    # Fields to synchronize between OpenShift and Nautobot
    # Excludes runtime fields like pod counts that change frequently
    _attributes = ("display_name", "description", "status", "labels", "annotations")
    
    # OpenShift-specific project fields beyond base Kubernetes metadata
    
    # Human-readable display name from openshift.io/display-name annotation
    # Falls back to metadata.name if annotation not present
    # Example: "Production Web Services" vs name "prod-web-svc"
    display_name: Optional[str] = ""
    
    # Project description from openshift.io/description annotation
    # Provides business context and purpose documentation
    # Example: "Production environment for customer-facing web applications"
    description: Optional[str] = ""
    
    # Project status indicating lifecycle state
    # Values: "Active", "Terminating" 
    # "Active" means project is operational and can contain resources
    status: str = "Active"
    
    # Resource quotas and limits applied to the project
    # Dictionary containing quota specifications and current usage
    # Used for capacity planning and resource management
    # Example: {"cpu": "10", "memory": "20Gi", "pods": "50"}
    resource_quota: Optional[Dict[str, Any]] = {}
    
    @classmethod
    def get_or_create(cls, adapter, **kwargs):
        """Get existing project or create new one via adapter.
        
        This is a convenience method for adapter implementations to handle
        the common pattern of checking for existing objects before creation.
        
        Args:
            adapter: DiffSync adapter instance handling the operation
            **kwargs: Model field values for get/create operation
            
        Returns:
            Model instance (either existing or newly created)
            
        Note:
            This method delegates to the adapter's get_or_create implementation
            which handles the actual interaction with the target system.
        """
        return adapter.get_or_create(cls, **kwargs)


class OpenshiftNode(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model representing OpenShift cluster nodes.
    
    Nodes are the physical or virtual machines that provide compute resources
    for the OpenShift cluster. They run the container runtime, kubelet, and
    other system components necessary for cluster operation.
    
    Node Categories:
    - Master/Control Plane: Run cluster control components (API server, etcd, scheduler)
    - Worker: Run application workloads and user containers
    - Infra: Run cluster infrastructure services (monitoring, logging, routing)
    
    Node Information Sources:
    - Hardware specifications from kubelet node status
    - Operating system details from node info
    - Capacity and allocatable resources
    - Node conditions and readiness status
    
    Nautobot Mapping:
    - Nodes map to Nautobot Device objects
    - Node roles determine device roles in Nautobot
    - Capacity information provides hardware specifications
    - Network addresses become management interfaces
    
    DiffSync Configuration:
    - Uses node name as unique identifier (unique within cluster)
    - Synchronizes hardware specifications and status information
    - Includes capacity for resource planning and management
    """
    
    # DiffSync model configuration
    _modelname = "openshift_node"
    
    # Use node name as primary identifier (unique within cluster)
    _identifiers = ("name",)
    
    # Node attributes to synchronize
    # Focuses on relatively stable hardware and configuration data
    # Excludes frequently changing metrics like CPU usage
    _attributes = (
        "hostname", "ip_address", "os_version", "container_runtime",
        "cpu_capacity", "memory_capacity", "storage_capacity", 
        "status", "role", "labels", "annotations"
    )
    
    # Node-specific fields beyond base Kubernetes metadata
    
    # System hostname of the node (may differ from Kubernetes node name)
    # Usually the FQDN or short hostname of the underlying machine
    # Example: "worker-01.prod.example.com"
    hostname: str
    
    # Primary IP address for node communication
    # Usually the internal cluster IP address
    # Example: "10.0.1.10"
    ip_address: Optional[str] = ""
    
    # Operating system version string from node status
    # Includes OS name, version, and sometimes kernel information
    # Example: "Red Hat Enterprise Linux CoreOS 4.10.3"
    os_version: Optional[str] = ""
    
    # Container runtime version information
    # OpenShift uses CRI-O by default, but could be Docker or others
    # Example: "cri-o://1.23.1-2.rhaos4.10.git7ac5d6c.el8"
    container_runtime: Optional[str] = "cri-o"
    
    # CPU capacity in cores (may be fractional for shared systems)
    # Represents total CPU cores available on the node
    # Example: 8 for an 8-core system
    cpu_capacity: Optional[int] = 0
    
    # Memory capacity in megabytes
    # Represents total system memory available for containers
    # Example: 32768 for 32GB system memory
    memory_capacity: Optional[int] = 0
    
    # Storage capacity in gigabytes
    # Represents ephemeral storage available for container images and logs
    # Example: 100 for 100GB available storage
    storage_capacity: Optional[int] = 0
    
    # Node readiness status
    # "Ready" means node is operational and can accept workloads
    # "NotReady" indicates node issues or maintenance mode
    status: str = "Ready"
    
    # Node role within the cluster
    # Determined by node labels like node-role.kubernetes.io/master
    # Values: "master" (control plane), "worker" (application nodes)
    role: str = "worker"

# =====================================================================
# USAGE PATTERNS FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. Creating New Resource Models:
#    class OpenshiftMyResource(OpenshiftBaseMixin, DiffSyncModel):
#        _modelname = "openshift_myresource"
#        _identifiers = ("namespace", "name")  # Namespaced resource
#        _attributes = ("labels", "annotations", "spec_field")
#        
#        namespace: str  # Required for namespaced resources
#        spec_field: str = ""  # Resource-specific field
#
# 2. Adding Fields to Existing Models:
#    # Always add as Optional with default to maintain compatibility
#    new_field: Optional[str] = ""
#    
#    # Update _attributes tuple to include new field
#    _attributes = (..., "new_field")
#
# 3. Handling Namespaced vs Cluster-scoped Resources:
#    # Namespaced: Include namespace in identifiers
#    _identifiers = ("namespace", "name")
#    
#    # Cluster-scoped: Use only name (if globally unique)
#    _identifiers = ("name",)
#
# 4. Field Naming Conventions:
#    # Follow Kubernetes API conventions
#    # Use snake_case for Python, not camelCase
#    # Use descriptive names: "cpu_capacity" not "cpu"
#    # Include units in names: "memory_mb", "storage_gb"
#
# 5. Type Hints Best Practices:
#    # Use Optional for fields that may not be present
#    # Use specific types: Dict[str, str] not Dict
#    # Use Union types for multiple possible types if needed
#    # Import types: from typing import Optional, Dict, List
#
# =====================================================================
# DIFFSYNC INTEGRATION NOTES
# =====================================================================
#
# 1. Model Lifecycle:
#    Source Adapter → Load Data → Create Models → DiffSync Engine
#    DiffSync Engine → Calculate Differences → Target Adapter → Apply Changes
#
# 2. Identifier Strategy:
#    - Must uniquely identify object instances
#    - Should be stable across API calls
#    - Prefer business keys over system-generated IDs
#    - For namespaced resources: ("namespace", "name")
#
# 3. Attribute Selection:
#    - Include fields that should be synchronized
#    - Exclude frequently changing runtime data
#    - Exclude fields controlled by target system
#    - Consider performance impact of large attributes
#
# 4. Relationship Handling:
#    - Use foreign key fields to reference related objects
#    - Ensure parent objects are loaded before children
#    - Handle cascade operations carefully
#    - Consider circular dependency issues
#
# =====================================================================
