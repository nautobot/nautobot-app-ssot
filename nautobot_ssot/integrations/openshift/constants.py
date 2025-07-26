"""Constants for OpenShift integration.

This module defines all constants used throughout the OpenShift Single Source of Truth
integration. Constants are organized by functional area and provide standardized
values for API interactions, resource identification, and system configuration.

Architecture Benefits:
- Centralized constant management for maintainability
- Type safety and consistency across the integration
- Easy updates when OpenShift/KubeVirt APIs change
- Clear documentation of expected values

Usage Patterns:
- Import specific constants where needed
- Use for API client configuration
- Reference in DiffSync model validation
- Apply in resource parsing and transformation logic

Maintenance Notes:
- Update KubeVirt constants when API versions change
- Verify OpenShift annotation constants with cluster versions
- Test default values with various cluster configurations
- Document any version-specific behavior
"""

# =====================================================================
# KUBEVIRT API CONSTANTS
# =====================================================================
# These constants define the KubeVirt Custom Resource Definition (CRD)
# API endpoints used for virtual machine discovery and management.
# KubeVirt extends Kubernetes with virtualization capabilities.

# KubeVirt API group identifier
# Used in Kubernetes API calls to identify KubeVirt resources
# Format: group/version for CRD access
KUBEVIRT_GROUP = "kubevirt.io"

# KubeVirt API version for VirtualMachine and VirtualMachineInstance resources
# This is the stable API version supported across KubeVirt releases
# Must match the CRD version installed on the target OpenShift cluster
KUBEVIRT_VERSION = "v1"

# KubeVirt VirtualMachine resource plural name
# Used in Kubernetes API endpoints: /apis/kubevirt.io/v1/virtualmachines
# Represents the desired state of virtual machines
KUBEVIRT_VM_PLURAL = "virtualmachines"

# KubeVirt VirtualMachineInstance resource plural name  
# Used in Kubernetes API endpoints: /apis/kubevirt.io/v1/virtualmachineinstances
# Represents the running instances of virtual machines
KUBEVIRT_VMI_PLURAL = "virtualmachineinstances"

# =====================================================================
# OPENSHIFT ANNOTATION CONSTANTS
# =====================================================================
# OpenShift uses annotations to store metadata that enhances the base
# Kubernetes object model. These annotations provide business context
# and organizational information not available in standard K8s resources.

# OpenShift display name annotation key
# Contains human-readable names for projects/namespaces
# Example: "Production Web Services" vs namespace name "prod-web-svc"
OPENSHIFT_DISPLAY_NAME_ANNOTATION = "openshift.io/display-name"

# OpenShift description annotation key
# Contains detailed descriptions of projects/namespaces
# Provides business context and purpose documentation
OPENSHIFT_DESCRIPTION_ANNOTATION = "openshift.io/description"

# =====================================================================
# NODE ROLE CONSTANTS
# =====================================================================
# OpenShift nodes have specific roles that determine their function
# within the cluster. These constants standardize role identification
# across different OpenShift versions and configurations.

# Master/Control plane node role
# Nodes that run the control plane components (API server, etcd, scheduler)
# Identified by node labels: node-role.kubernetes.io/master or node-role.kubernetes.io/control-plane
NODE_ROLE_MASTER = "master"

# Worker node role  
# Nodes that run application workloads and user pods
# Default role for nodes without master/control-plane labels
NODE_ROLE_WORKER = "worker"

# =====================================================================
# VIRTUAL MACHINE STATE CONSTANTS
# =====================================================================
# KubeVirt virtual machines have specific lifecycle states that indicate
# their current operational status. These constants provide standardized
# state values for VM management and monitoring.

# VM is actively running
# Corresponds to VirtualMachineInstance in "Running" phase
# Indicates VM is operational and consuming resources
VM_STATE_RUNNING = "Running"

# VM is stopped/powered off
# VirtualMachine exists but no VirtualMachineInstance is running
# VM definition is preserved but not consuming compute resources
VM_STATE_STOPPED = "Stopped"

# VM is being migrated to another node
# Occurs during live migration operations
# Temporary state during node maintenance or load balancing
VM_STATE_MIGRATING = "Migrating"

# =====================================================================
# DEFAULT VALUES FOR RESOURCE SPECIFICATIONS
# =====================================================================
# These defaults are used when OpenShift/KubeVirt resource specifications
# are incomplete or missing. They provide sensible fallback values that
# ensure the integration can function even with partial data.

# Default CPU core count for VMs when not specified
# Conservative default that works across most VM configurations
# Can be overridden by actual VM resource specifications
DEFAULT_CPU_CORES = 1

# Default memory allocation in megabytes
# 1GB is a reasonable minimum for most VM workloads
# Actual values should come from VM resource requests/limits
DEFAULT_MEMORY_MB = 1024

# Default KubeVirt machine type
# q35 is the modern QEMU machine type supporting advanced features
# Provides good compatibility and performance for most workloads
DEFAULT_MACHINE_TYPE = "q35"

# =====================================================================
# USAGE PATTERNS FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. API Client Usage:
#    from .constants import KUBEVIRT_GROUP, KUBEVIRT_VERSION
#    api_response = custom_objects_api.list_cluster_custom_object(
#        group=KUBEVIRT_GROUP,
#        version=KUBEVIRT_VERSION,
#        plural=KUBEVIRT_VM_PLURAL
#    )
#
# 2. Resource Parsing:
#    from .constants import OPENSHIFT_DISPLAY_NAME_ANNOTATION
#    display_name = namespace.metadata.annotations.get(
#        OPENSHIFT_DISPLAY_NAME_ANNOTATION,
#        namespace.metadata.name
#    )
#
# 3. Default Value Assignment:
#    from .constants import DEFAULT_CPU_CORES, DEFAULT_MEMORY_MB
#    vm_spec = {
#        "cpu_cores": vm_data.get("cpu", DEFAULT_CPU_CORES),
#        "memory_mb": vm_data.get("memory", DEFAULT_MEMORY_MB)
#    }
#
# 4. State Comparison:
#    from .constants import VM_STATE_RUNNING
#    if vm.status == VM_STATE_RUNNING:
#        # Handle running VM logic
#
# 5. Node Role Detection:
#    from .constants import NODE_ROLE_MASTER, NODE_ROLE_WORKER
#    role = NODE_ROLE_MASTER if is_control_plane(node) else NODE_ROLE_WORKER
#
# =====================================================================
# VERSION COMPATIBILITY NOTES
# =====================================================================
#
# KubeVirt API Versions:
# - v1: Stable API, recommended for production use
# - v1alpha3: Deprecated, use v1 instead
# - v1beta1: Deprecated, use v1 instead
#
# OpenShift Versions:
# - 4.x: Current supported versions with these annotations
# - 3.x: Legacy versions may have different annotation schemes
#
# Kubernetes Versions:
# - 1.20+: Full support for all constants
# - 1.19-: Some node role labels may differ
#
# =====================================================================
