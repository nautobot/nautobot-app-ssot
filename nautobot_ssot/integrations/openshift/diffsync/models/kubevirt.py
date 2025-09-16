# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""KubeVirt-specific DiffSync models for OpenShift integration.

This module defines DiffSync models for KubeVirt virtual machines running on OpenShift.
KubeVirt extends Kubernetes to support traditional virtual machine workloads alongside
containers, providing a unified management platform for hybrid cloud-native environments.

KubeVirt Architecture Overview:
- VirtualMachine (VM): Desired state specification for a virtual machine
- VirtualMachineInstance (VMI): Running instance of a virtual machine
- Pods: VMs run inside special pods with virt-launcher containers
- Custom Resource Definitions (CRDs): Extend Kubernetes API for virtualization

KubeVirt Resource Lifecycle:
1. VirtualMachine defines the desired VM configuration
2. When VM.spec.running=true, a VirtualMachineInstance is created
3. VMI triggers creation of a virt-launcher pod on a node
4. The pod runs QEMU/KVM to provide the virtual machine
5. VM and VMI provide different views: desired state vs runtime state

Hybrid Workload Management:
- Traditional VMs run alongside cloud-native containers
- Shared networking, storage, and security policies
- Kubernetes operators manage VM lifecycle
- Migration capabilities for maintenance and load balancing

Nautobot Integration Strategy:
- VirtualMachines map to Nautobot VirtualMachine objects
- VMIs provide runtime status and network information
- VM specifications define hardware requirements
- Node placement provides physical location context

Key Design Principles:
- Separate desired state (VM) from runtime state (VMI)
- Use VM specifications for capacity planning
- Track VMI status for operational monitoring
- Maintain relationships between VMs, VMIs, and pods
"""

from typing import Optional, List, Dict, Any
from diffsync import DiffSyncModel
from .base import OpenshiftBaseMixin


class OpenshiftVirtualMachine(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for KubeVirt VirtualMachine resources (desired state).
    
    VirtualMachine resources define the desired configuration and state for virtual
    machines in KubeVirt. They specify hardware requirements, boot settings, and
    lifecycle management policies without representing runtime state.
    
    VM vs VMI Distinction:
    - VirtualMachine: Template/specification for what the VM should be
    - VirtualMachineInstance: Actual running instance with runtime status
    - Similar to Deployment vs Pod relationship in container workloads
    
    KubeVirt VM Capabilities:
    - Full virtualization with QEMU/KVM hypervisor
    - Hardware specification (CPU, memory, disks, network)
    - Guest OS support for Windows, Linux, and other operating systems
    - Live migration for maintenance and load balancing
    - Snapshot and cloning capabilities
    
    VM Configuration Areas:
    - Compute: CPU cores, memory allocation, hardware features
    - Storage: Virtual disks, volumes, and persistent storage
    - Networking: Virtual network interfaces and IP allocation
    - Boot: Firmware settings, boot order, and guest agent
    
    OpenShift Integration:
    - VMs benefit from OpenShift's security, networking, and storage
    - Integration with OpenShift monitoring and logging
    - Support for OpenShift's multi-tenancy via projects
    - Access to OpenShift's software-defined networking (SDN)
    
    Nautobot Mapping:
    - Maps to Nautobot VirtualMachine objects
    - Hardware specs define VM capabilities in DCIM
    - Network interfaces create IP address associations
    - Placement on nodes provides location context
    
    Lifecycle Management:
    - VM.spec.running controls desired power state
    - VM controller creates/destroys VMI based on running state
    - VM persists when VMI is stopped (preserves configuration)
    - VM deletion removes both VM and any running VMI
    """
    
    # DiffSync model configuration for VirtualMachine resources
    _modelname = "openshift_virtualmachine"
    
    # VMs are namespaced resources identified by namespace + name
    _identifiers = ("namespace", "name")
    
    # VM specification attributes focused on desired configuration
    # Includes hardware specs and configuration, excludes runtime metrics
    _attributes = (
        "running", "node", "cpu_cores", "memory", "disks",
        "interfaces", "status", "guest_os", "vmi_uid",
        "firmware", "machine_type", "labels", "annotations"
    )
    
    # VirtualMachine-specific fields for VM configuration and state
    
    # Namespace containing this virtual machine (OpenShift project)
    # Provides organizational context and resource isolation
    # Example: "production", "development", "testing"
    namespace: str
    
    # Desired running state of the virtual machine
    # True: VM should be powered on (VMI will be created)
    # False: VM should be powered off (VMI will be destroyed)
    # Controls the VM lifecycle through the VM controller
    running: bool = False
    
    # Node where the VM is currently running (if running)
    # Determined by Kubernetes scheduler and resource availability
    # Example: "worker-03.prod.example.com"
    node: Optional[str] = ""
    
    # Number of virtual CPU cores allocated to the VM
    # Can be fractional (e.g., 0.5) for shared CPU scenarios
    # Example: 2 (two virtual CPU cores)
    cpu_cores: int = 1
    
    # Memory allocation in megabytes
    # Represents guest OS memory available to the VM
    # Example: 4096 (4 GB of memory)
    memory: int = 1024
    
    # Virtual disk configuration for the VM
    # List of disk specifications including storage and boot settings
    # Example: [{"name": "rootdisk", "size": "20Gi", "storageClass": "fast-ssd"}]
    disks: List[Dict[str, Any]] = []
    
    # Virtual network interface configuration
    # Defines VM networking including bridge and IP assignment
    # Example: [{"name": "default", "model": "virtio", "bridge": "br0"}]
    interfaces: List[Dict[str, Any]] = []
    
    # Current operational status of the virtual machine
    # Values include: "Stopped", "Starting", "Running", "Migrating", "Paused"
    # Reflects actual VM state, not just desired state
    status: str = "Stopped"
    
    # Guest operating system information
    # May be detected via guest agent or specified in configuration
    # Example: "Red Hat Enterprise Linux 8.5", "Windows Server 2019"
    guest_os: Optional[str] = ""
    
    # UID of the associated VirtualMachineInstance (if running)
    # Links the VM specification to its runtime instance
    # Empty when VM is stopped (no VMI exists)
    vmi_uid: Optional[str] = ""
    
    # Firmware configuration for the virtual machine
    # Includes BIOS/UEFI settings and boot configuration
    # Example: {"bootloader": {"efi": {"secureBoot": true}}}
    firmware: Optional[Dict[str, Any]] = {}
    
    # QEMU machine type for hardware emulation
    # Determines virtual hardware platform and features
    # Common values: "q35" (modern), "pc" (legacy), "pc-q35-rhel8.4.0"
    machine_type: Optional[str] = "q35"
    
    def is_active(self) -> bool:
        """Check if the virtual machine is actively running.
        
        This method provides a convenient way to determine if the VM is in
        an active operational state, combining the desired running state
        with actual status information.
        
        Returns:
            bool: True if VM is running and operational, False otherwise
            
        Active States:
        - "Running": VM is fully operational
        - "Migrating": VM is being moved between nodes (still operational)
        
        Inactive States:
        - "Stopped": VM is powered off
        - "Starting": VM is booting up
        - "Paused": VM is suspended but not running
        - Any other status indicates transitional or error state
        """
        return self.running and self.status in ["Running", "Migrating"]


class OpenshiftVirtualMachineInstance(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for KubeVirt VirtualMachineInstance resources (runtime state).
    
    VirtualMachineInstance represents the running instance of a virtual machine,
    providing runtime status, resource allocation, and operational metrics. VMIs
    are created automatically when a VirtualMachine's running field is set to true.
    
    VMI Runtime Characteristics:
    - Ephemeral: Created/destroyed as VMs start/stop
    - Runtime Status: Provides actual operational state
    - Resource Allocation: Shows scheduled resources and placement
    - Network State: IP addresses and connectivity information
    
    VMI Lifecycle Phases:
    - Pending: VMI created but not yet scheduled
    - Scheduling: Kubernetes scheduler finding suitable node
    - Scheduled: Node selected, pod creation in progress
    - Running: VM is active and operational
    - Succeeded: VM completed successfully (rare for VMs)
    - Failed: VM failed to start or crashed
    
    Live Migration Support:
    - VMIs can be migrated between nodes for maintenance
    - Migration preserves VM state and network connectivity
    - Live migration requires shared storage and network
    - Migration policies control automated migration behavior
    
    Guest Agent Integration:
    - KubeVirt guest agent provides VM introspection
    - Reports guest OS information and resource usage
    - Enables graceful shutdown and restart operations
    - Provides guest-level networking and filesystem data
    
    Monitoring and Observability:
    - VMI status provides operational health information
    - Conditions array details specific operational states
    - Integration with OpenShift monitoring and alerting
    - Resource usage metrics for capacity planning
    
    Nautobot Integration:
    - VMI provides runtime data to update VM objects
    - IP addresses create network address associations
    - Node placement shows current physical location
    - Operational status drives VM state in Nautobot
    
    Relationship to Pods:
    - Each VMI has a corresponding virt-launcher pod
    - Pod provides container infrastructure for VM process
    - Pod resources (CPU, memory) allocated for VM needs
    - Pod placement determines VM node assignment
    """
    
    # DiffSync model configuration for VirtualMachineInstance resources
    _modelname = "openshift_vmi"
    
    # VMIs are namespaced resources identified by namespace + name
    # VMI name typically matches the parent VirtualMachine name
    _identifiers = ("namespace", "name")
    
    # Runtime attributes providing operational status and placement
    # Focuses on current state rather than desired configuration
    _attributes = (
        "vm_name", "phase", "node", "ip_address", "ready",
        "live_migratable", "conditions", "guest_agent_info"
    )
    
    # VirtualMachineInstance-specific fields for runtime state
    
    # Namespace containing this VMI (OpenShift project)
    # Must match the namespace of the parent VirtualMachine
    # Example: "production"
    namespace: str
    
    # Name of the parent VirtualMachine that created this VMI
    # Links the runtime instance back to its specification
    # Usually matches the VMI name but provides explicit relationship
    vm_name: str
    
    # Current lifecycle phase of the VMI
    # Reflects the Kubernetes pod lifecycle for the virt-launcher
    # "Pending": VMI created but not yet scheduled to a node
    # "Scheduling": Kubernetes scheduler evaluating node placement
    # "Scheduled": Node selected, pod creation in progress
    # "Running": VM is active and operational on the assigned node
    # "Succeeded": VM completed successfully (rare for long-running VMs)
    # "Failed": VM failed to start or crashed during operation
    phase: str = "Pending"
    
    # Node where this VMI is currently running
    # Assigned by Kubernetes scheduler based on resource requirements
    # Example: "worker-02.prod.example.com"
    node: Optional[str] = ""
    
    # IP address assigned to the VM's network interface
    # Allocated by the cluster's networking solution (CNI)
    # Example: "10.244.2.45" (cluster-internal IP)
    ip_address: Optional[str] = ""
    
    # Overall readiness status of the virtual machine
    # True: VM is fully operational and ready to serve traffic
    # False: VM is starting, failing, or not yet ready
    # Used by services and load balancers for traffic routing
    ready: bool = False
    
    # Whether the VM supports live migration between nodes
    # True: VM can be migrated without downtime
    # False: VM migration requires shutdown/restart
    # Depends on storage, networking, and VM configuration
    live_migratable: bool = False
    
    # Detailed condition information about VMI operational state
    # Array of condition objects with type, status, and reason
    # Example: [{"type": "Ready", "status": "True", "lastTransitionTime": "..."}]
    # Provides granular status for troubleshooting and monitoring
    conditions: List[Dict[str, Any]] = []
    
    # Information reported by the guest agent running inside the VM
    # Includes guest OS details, installed software, and resource usage
    # Example: {"guestOSInfo": {"name": "rhel", "version": "8.5", "kernel": "..."}}
    # Requires guest agent installation and configuration
    guest_agent_info: Optional[Dict[str, Any]] = {}

# =====================================================================
# KUBEVIRT INTEGRATION PATTERNS FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. VM-VMI Relationship Pattern:
#    # VirtualMachine defines desired state
#    vm = OpenshiftVirtualMachine(
#        namespace="prod",
#        name="web-server-vm",
#        running=True,
#        cpu_cores=2,
#        memory=4096
#    )
#    
#    # When running=True, VMI is created automatically
#    vmi = OpenshiftVirtualMachineInstance(
#        namespace="prod",
#        name="web-server-vm",  # Same name as VM
#        vm_name="web-server-vm",
#        phase="Running",
#        node="worker-01"
#    )
#
# 2. Lifecycle State Tracking:
#    def get_vm_operational_state(vm, vmi):
#        if not vm.running:
#            return "Stopped"
#        elif vmi and vmi.phase == "Running" and vmi.ready:
#            return "Running"
#        elif vmi and vmi.phase in ["Pending", "Scheduling", "Scheduled"]:
#            return "Starting"
#        else:
#            return "Unknown"
#
# 3. Resource Specification Patterns:
#    vm_config = {
#        "cpu_cores": 4,
#        "memory": 8192,  # 8 GB
#        "disks": [
#            {
#                "name": "rootdisk",
#                "size": "50Gi",
#                "storageClass": "fast-ssd",
#                "bus": "virtio"
#            }
#        ],
#        "interfaces": [
#            {
#                "name": "default",
#                "model": "virtio",
#                "bridge": "br0"
#            }
#        ]
#    }
#
# 4. Migration Status Detection:
#    def is_migrating(vm, vmi):
#        return (vm.status == "Migrating" or 
#                (vmi and any(c.get("type") == "LiveMigratable" 
#                           for c in vmi.conditions)))
#
# 5. Guest Agent Data Processing:
#    def extract_guest_info(vmi):
#        if not vmi.guest_agent_info:
#            return None
#        
#        guest_os_info = vmi.guest_agent_info.get("guestOSInfo", {})
#        return {
#            "os_name": guest_os_info.get("name"),
#            "os_version": guest_os_info.get("version"),
#            "kernel_version": guest_os_info.get("kernelVersion"),
#            "hostname": guest_os_info.get("hostname")
#        }
#
# =====================================================================
# NAUTOBOT MAPPING STRATEGIES FOR KUBEVIRT VMS
# =====================================================================
#
# 1. VirtualMachine Mapping:
#    KubeVirt VM → Nautobot VirtualMachine
#    - vm.name → virtualmachine.name
#    - vm.namespace → virtualmachine.tenant (via project mapping)
#    - vm.cpu_cores → virtualmachine.vcpus
#    - vm.memory → virtualmachine.memory (convert MB to GB)
#    - vm.node → virtualmachine.cluster (node to cluster mapping)
#    - vm.status → virtualmachine.status
#
# 2. Network Interface Mapping:
#    VMI IP Address → Nautobot IP Address
#    - vmi.ip_address → ipaddress.address
#    - vmi.namespace → ipaddress.tenant
#    - Associated with VirtualMachine via VMInterface
#
# 3. Hardware Specification:
#    VM Disks → Nautobot VirtualDisk
#    - disk.name → virtualdisk.name
#    - disk.size → virtualdisk.size
#    - disk.storageClass → custom field for storage type
#
# 4. Operational Status:
#    VM/VMI Status → Nautobot Status
#    - Running VM + Ready VMI → "Active" status
#    - Stopped VM → "Offline" status
#    - Starting/Migrating → "Staging" status
#    - Failed VM/VMI → "Failed" status
#
# =====================================================================
# KUBEVIRT-SPECIFIC CONSIDERATIONS
# =====================================================================
#
# 1. Storage Requirements:
#    # VMs require persistent storage for disks
#    # OpenShift Container Storage (OCS) or external storage
#    # Storage classes define performance and availability
#    # Consider backup and snapshot capabilities
#
# 2. Networking Models:
#    # Pod networking: VM gets cluster IP like containers
#    # Multus: Additional network interfaces for VMs
#    # SR-IOV: High-performance networking for VMs
#    # LoadBalancer services for external VM access
#
# 3. Security Considerations:
#    # VMs run with elevated privileges (KVM access)
#    # Security Context Constraints (SCC) for virt-launcher pods
#    # VM isolation through namespace and network policies
#    # Guest agent security and update management
#
# 4. Performance Optimization:
#    # CPU pinning for performance-critical VMs
#    # NUMA topology awareness for large VMs
#    # Huge pages for memory-intensive workloads
#    # Storage optimization with provisioning modes
#
# 5. Monitoring Integration:
#    # VM metrics via node_exporter in guest
#    # Host metrics via OpenShift monitoring
#    # Custom dashboards for VM operational status
#    # Alerting on VM availability and performance
#
# =====================================================================
# MIGRATION AND LIFECYCLE MANAGEMENT
# =====================================================================
#
# 1. Live Migration Workflow:
#    # Migration triggered manually or by policies
#    # VM memory and state transferred between nodes
#    # Network connectivity maintained during migration
#    # Storage must be accessible from both nodes
#
# 2. VM Lifecycle States:
#    VM.running=false → VMI deleted → VM specification preserved
#    VM.running=true → VMI created → Pod scheduled → VM starts
#    VM deleted → VMI deleted → Pod deleted → All resources cleaned
#
# 3. Backup and Recovery:
#    # VM snapshots capture disk and memory state
#    # Volume snapshots for data protection
#    # VM export/import for disaster recovery
#    # Integration with backup operators
#
# 4. Scaling Considerations:
#    # VMs are stateful and don't auto-scale like containers
#    # Load balancing via services and routes
#    # Horizontal scaling through multiple VM instances
#    # Vertical scaling by adjusting VM resource specs
#
# =====================================================================
