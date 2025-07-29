# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""KubeVirt-specific utility functions for OpenShift integration.

This module provides utility functions for working with KubeVirt virtual machines
in OpenShift environments. It handles VM status detection, resource parsing,
network configuration, and guest agent data extraction.

KubeVirt VM Architecture:
- VirtualMachine: Desired state specification
- VirtualMachineInstance: Runtime instance with status
- Guest Agent: In-VM agent providing introspection data
- Domain Specification: QEMU/KVM configuration details

Key Functionality:
- VM operational status detection and validation
- Resource specification parsing (CPU, memory, storage)
- Network interface configuration extraction
- Guest operating system information processing
- Resource unit conversion and normalization

Resource Management:
- CPU allocation parsing from core specifications
- Memory parsing with unit conversion (Ki, Mi, Gi)
- Network interface MAC and IP address extraction
- Guest agent integration for enhanced visibility

Integration Points:
- Used by OpenShift client for data transformation
- Supports DiffSync model population
- Enables Nautobot resource mapping
- Provides consistent data normalization
"""

from typing import Dict, Any, Optional, List


def is_vm_running(vm_status: Dict[str, Any]) -> bool:
    """Check if a virtual machine is in an operational running state.
    
    Determines whether a KubeVirt VM is currently running and operational
    based on its status information. This function handles various VM
    states and provides a unified way to check operational status.
    
    Args:
        vm_status: VM status dictionary from KubeVirt API
        
    Returns:
        bool: True if VM is running or in operational state, False otherwise
        
    VM Status Values:
    - "Running": VM is fully operational and serving workloads
    - "Migrating": VM is being moved between nodes (still operational)
    - "Starting": VM is booting up (transitional state)
    - "Stopped": VM is powered off
    - "Paused": VM is suspended but not running
    - "Failed": VM has encountered an error
    
    Usage Example:
        vm_status = {"printableStatus": "Running"}
        if is_vm_running(vm_status):
            # VM is operational, proceed with data collection
            process_running_vm(vm)
    
    Notes:
    - Uses printableStatus field which provides human-readable status
    - Considers both "running" and "migrating" as operational states
    - Case-insensitive comparison for robustness
    - Returns False for any unknown or error states
    """
    # Extract printable status from VM status object
    printable_status = vm_status.get("printableStatus", "").lower()
    
    # Define operational states where VM is considered running
    operational_states = ["running", "migrating"]
    
    # Check if VM is in any operational state
    return printable_status in operational_states


def extract_vm_os_info(guest_agent_info: Optional[Dict[str, Any]]) -> str:
    """Extract guest operating system information from KubeVirt guest agent.
    
    Processes guest agent data to extract meaningful operating system
    information for display and categorization purposes. The guest agent
    provides introspection data from within the running VM.
    
    Args:
        guest_agent_info: Guest agent data from VMI status
        
    Returns:
        str: Formatted OS information string (e.g., "Red Hat Enterprise Linux 8.5")
        
    Guest Agent Data Structure:
    - os.name: Operating system name (e.g., "rhel", "ubuntu", "windows")
    - os.version: OS version string (e.g., "8.5", "20.04", "Server 2019")
    - os.kernelVersion: Kernel version for Linux systems
    - os.architecture: CPU architecture (x86_64, aarch64)
    
    Formatting Logic:
    - Combines name and version when both are available
    - Returns name only if version is missing
    - Returns empty string if no OS information is available
    - Handles various OS naming conventions consistently
    
    Usage Example:
        guest_info = {
            "os": {
                "name": "Red Hat Enterprise Linux",
                "version": "8.5"
            }
        }
        os_string = extract_vm_os_info(guest_info)
        # Returns: "Red Hat Enterprise Linux 8.5"
    
    Notes:
    - Guest agent must be installed and running in VM
    - Information may be empty for newly created VMs
    - Updates as guest agent reports current state
    - Useful for inventory and compliance reporting
    """
    # Return empty string if no guest agent data available
    if not guest_agent_info:
        return ""
    
    # Extract OS information from guest agent data
    os_info = guest_agent_info.get("os", {})
    
    # Get OS name and version components
    name = os_info.get("name", "")
    version = os_info.get("version", "")
    
    # Format OS information based on available data
    if name and version:
        return f"{name} {version}"
    elif name:
        return name
    else:
        return ""


def get_vm_network_interfaces(vmi_status: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract network interface configuration from VirtualMachineInstance status.
    
    Processes VMI status to extract detailed network interface information
    including MAC addresses, IP assignments, and interface names. This data
    is essential for network management and connectivity tracking.
    
    Args:
        vmi_status: VMI status dictionary containing interface information
        
    Returns:
        List[Dict]: List of interface dictionaries with network details
        
    Interface Data Structure:
    Each interface dictionary contains:
    - name: Interface name (e.g., "default", "eth0", "multus-net1")
    - mac: MAC address for the interface
    - ip: Primary IP address (for backward compatibility)
    - ips: List of all IP addresses assigned to interface
    
    Network Configuration:
    - Pod Network: Default cluster network interface
    - Multus Networks: Additional network attachments
    - SR-IOV: High-performance networking interfaces
    - Bridge Networks: Traditional bridged networking
    
    Usage Example:
        vmi_status = {
            "interfaces": [
                {
                    "name": "default",
                    "mac": "02:42:0a:f4:01:2d",
                    "ipAddress": "10.244.1.45",
                    "ipAddresses": ["10.244.1.45"]
                }
            ]
        }
        interfaces = get_vm_network_interfaces(vmi_status)
    
    Notes:
    - VMI must be running to have interface status
    - Interface data updates as network configuration changes
    - Multiple IP addresses supported per interface
    - MAC addresses are generated by KubeVirt or specified in VM config
    """
    # Initialize empty interface list
    interfaces = []
    
    # Process each interface from VMI status
    for iface in vmi_status.get("interfaces", []):
        # Extract interface information with defaults
        interface_info = {
            "name": iface.get("name", ""),
            "mac": iface.get("mac", ""),
            "ip": iface.get("ipAddress", ""),  # Primary IP for compatibility
            "ips": iface.get("ipAddresses", []),  # All assigned IPs
        }
        
        # Add interface to collection
        interfaces.append(interface_info)
    
    return interfaces


def calculate_vm_resources(domain_spec: Dict[str, Any]) -> Dict[str, int]:
    """Calculate VM resource requirements from KubeVirt domain specification.
    
    Parses the domain specification from a KubeVirt VirtualMachine to extract
    CPU and memory resource requirements. Handles unit conversion and provides
    normalized resource values for capacity planning and resource tracking.
    
    Args:
        domain_spec: Domain specification from VM template spec
        
    Returns:
        Dict[str, int]: Normalized resource requirements
        
    Resource Specification:
    - cpu_cores: Number of virtual CPU cores (integer)
    - memory_mb: Memory allocation in megabytes (integer)
    
    CPU Configuration:
    - cores: Number of CPU cores
    - threads: Number of threads per core (optional)
    - sockets: Number of CPU sockets (optional)
    - model: CPU model specification (optional)
    
    Memory Configuration:
    - requests.memory: Memory allocation with units (e.g., "4Gi", "2048Mi")
    - limits.memory: Maximum memory allowed (optional)
    - hugepages: Huge page configuration (optional)
    
    Unit Conversion:
    - Gi (Gibibytes): Converted to MB (1 Gi = 1024 MB)
    - Mi (Mebibytes): Direct conversion to MB
    - Ki (Kibibytes): Converted to MB (1024 Ki = 1 MB)
    - Bytes: Converted to MB (1,048,576 bytes = 1 MB)
    
    Usage Example:
        domain_spec = {
            "cpu": {"cores": 4},
            "resources": {
                "requests": {"memory": "8Gi"}
            }
        }
        resources = calculate_vm_resources(domain_spec)
        # Returns: {"cpu_cores": 4, "memory_mb": 8192}
    
    Notes:
    - Provides sensible defaults for missing specifications
    - Handles various memory unit formats consistently
    - CPU cores default to 1 if not specified
    - Memory defaults to 1024 MB if not specified
    - Used for Nautobot VM resource field population
    """
    # Initialize default resource allocations
    resources = {
        "cpu_cores": 1,      # Default to single CPU core
        "memory_mb": 1024,   # Default to 1 GB memory
    }
    
    # Extract CPU specification from domain configuration
    cpu_spec = domain_spec.get("cpu", {})
    
    # Get CPU core count (default to 1 if not specified)
    resources["cpu_cores"] = cpu_spec.get("cores", 1)
    
    # Extract memory specification from resource requests
    resource_spec = domain_spec.get("resources", {})
    memory_request = resource_spec.get("requests", {}).get("memory", "1Gi")
    
    # Parse memory string and convert to megabytes
    if isinstance(memory_request, str):
        # Handle Gibibytes (Gi) - binary gigabytes
        if memory_request.endswith("Gi"):
            memory_value = int(memory_request[:-2])
            resources["memory_mb"] = memory_value * 1024  # 1 Gi = 1024 MB
        
        # Handle Mebibytes (Mi) - binary megabytes  
        elif memory_request.endswith("Mi"):
            resources["memory_mb"] = int(memory_request[:-2])  # Direct conversion
        
        # Handle Kibibytes (Ki) - binary kilobytes
        elif memory_request.endswith("Ki"):
            memory_value = int(memory_request[:-2])
            resources["memory_mb"] = memory_value // 1024  # 1024 Ki = 1 MB
        
        # Handle raw bytes (less common but possible)
        elif memory_request.endswith("B"):
            memory_value = int(memory_request[:-1])
            resources["memory_mb"] = memory_value // (1024 * 1024)  # Bytes to MB
        
        # Handle decimal units (G, M, K) - less common in Kubernetes
        elif memory_request.endswith("G"):
            memory_value = int(memory_request[:-1])
            resources["memory_mb"] = memory_value * 1000  # 1 G = 1000 MB
        elif memory_request.endswith("M"):
            resources["memory_mb"] = int(memory_request[:-1])
        elif memory_request.endswith("K"):
            memory_value = int(memory_request[:-1])
            resources["memory_mb"] = memory_value // 1000
    
    # Handle numeric memory values (assume MB)
    elif isinstance(memory_request, (int, float)):
        resources["memory_mb"] = int(memory_request)
    
    return resources


def parse_vm_disk_specifications(domain_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse virtual disk specifications from KubeVirt domain configuration.
    
    Extracts disk configuration details from the VM domain specification,
    providing information about virtual storage devices attached to the VM.
    This data is useful for storage capacity planning and management.
    
    Args:
        domain_spec: Domain specification containing disk configurations
        
    Returns:
        List[Dict]: List of disk specification dictionaries
        
    Disk Specification Fields:
    - name: Disk identifier within the VM
    - bus: Storage bus type (virtio, sata, scsi)
    - bootOrder: Boot priority for this disk (optional)
    - disk: Disk-specific configuration
    - cdrom: CD-ROM specific configuration (if applicable)
    
    Storage Bus Types:
    - virtio: High-performance paravirtualized storage
    - sata: SATA storage interface
    - scsi: SCSI storage interface
    - ide: Legacy IDE interface
    
    Usage Example:
        domain_spec = {
            "devices": {
                "disks": [
                    {
                        "name": "rootdisk",
                        "disk": {"bus": "virtio"},
                        "bootOrder": 1
                    }
                ]
            }
        }
        disks = parse_vm_disk_specifications(domain_spec)
    
    Notes:
    - Disk size information stored separately in volume specifications
    - Boot order determines VM boot sequence
    - Bus type affects performance and compatibility
    - Multiple disks supported per VM
    """
    disks = []
    
    # Extract disk devices from domain specification
    devices = domain_spec.get("devices", {})
    disk_devices = devices.get("disks", [])
    
    # Process each disk configuration
    for disk in disk_devices:
        disk_info = {
            "name": disk.get("name", ""),
            "bus": "",
            "boot_order": disk.get("bootOrder"),
            "type": "disk"  # Default type
        }
        
        # Determine disk type and bus configuration
        if "disk" in disk:
            disk_info["bus"] = disk["disk"].get("bus", "virtio")
            disk_info["type"] = "disk"
        elif "cdrom" in disk:
            disk_info["bus"] = disk["cdrom"].get("bus", "sata")
            disk_info["type"] = "cdrom"
        elif "lun" in disk:
            disk_info["bus"] = disk["lun"].get("bus", "scsi")
            disk_info["type"] = "lun"
        
        disks.append(disk_info)
    
    return disks


def extract_vm_conditions(vmi_status: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract operational conditions from VirtualMachineInstance status.
    
    Processes VMI status to extract condition information that describes
    the operational state and health of the virtual machine. Conditions
    provide detailed status information for monitoring and troubleshooting.
    
    Args:
        vmi_status: VMI status containing condition information
        
    Returns:
        List[Dict]: List of condition dictionaries with status details
        
    Condition Types:
    - Ready: VM is ready to serve traffic
    - LiveMigratable: VM can be live migrated
    - AgentConnected: Guest agent is connected and responding
    - Synchronized: VM configuration is synchronized
    - Paused: VM is in paused state
    
    Condition Fields:
    - type: Condition type identifier
    - status: Boolean status (True/False)
    - lastTransitionTime: When condition last changed
    - reason: Short reason for current status
    - message: Human-readable description
    
    Usage Example:
        vmi_status = {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "True",
                    "lastTransitionTime": "2023-10-15T10:30:00Z"
                }
            ]
        }
        conditions = extract_vm_conditions(vmi_status)
    
    Notes:
    - Conditions change as VM state evolves
    - Useful for automated monitoring and alerting
    - Provides detailed operational status beyond simple running/stopped
    - Critical for determining VM health and readiness
    """
    conditions = []
    
    # Extract conditions from VMI status
    condition_list = vmi_status.get("conditions", [])
    
    # Process each condition entry
    for condition in condition_list:
        condition_info = {
            "type": condition.get("type", ""),
            "status": condition.get("status", ""),
            "last_transition_time": condition.get("lastTransitionTime", ""),
            "reason": condition.get("reason", ""),
            "message": condition.get("message", ""),
        }
        
        conditions.append(condition_info)
    
    return conditions

# =====================================================================
# KUBEVIRT UTILITY PATTERNS FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. VM Status Checking Patterns:
#    def check_vm_operational_status(vm, vmi):
#        # Check VM desired state
#        if not vm.get("spec", {}).get("running", False):
#            return "Stopped"
#        
#        # Check VMI runtime status
#        if vmi and is_vm_running(vmi.get("status", {})):
#            return "Running"
#        elif vmi:
#            return vmi.get("status", {}).get("phase", "Unknown")
#        else:
#            return "Starting"
#
# 2. Resource Parsing with Validation:
#    def parse_resources_safely(domain_spec):
#        try:
#            resources = calculate_vm_resources(domain_spec)
#            
#            # Validate resource limits
#            if resources["cpu_cores"] > 64:
#                logger.warning(f"High CPU allocation: {resources['cpu_cores']} cores")
#            
#            if resources["memory_mb"] > 512000:  # 500 GB
#                logger.warning(f"High memory allocation: {resources['memory_mb']} MB")
#            
#            return resources
#        except (ValueError, KeyError) as e:
#            logger.error(f"Failed to parse VM resources: {e}")
#            return {"cpu_cores": 1, "memory_mb": 1024}  # Safe defaults
#
# 3. Network Interface Processing:
#    def process_vm_networking(vmi_status):
#        interfaces = get_vm_network_interfaces(vmi_status)
#        
#        network_info = {
#            "primary_ip": None,
#            "all_ips": [],
#            "mac_addresses": [],
#            "interface_count": len(interfaces)
#        }
#        
#        for iface in interfaces:
#            # Collect MAC addresses
#            if iface["mac"]:
#                network_info["mac_addresses"].append(iface["mac"])
#            
#            # Collect IP addresses
#            network_info["all_ips"].extend(iface["ips"])
#            
#            # Set primary IP (first interface with IP)
#            if iface["ip"] and not network_info["primary_ip"]:
#                network_info["primary_ip"] = iface["ip"]
#        
#        return network_info
#
# 4. Guest Agent Data Processing:
#    def process_guest_agent_data(guest_agent_info):
#        if not guest_agent_info:
#            return {"available": False}
#        
#        # Extract OS information
#        os_info = extract_vm_os_info(guest_agent_info)
#        
#        # Extract additional guest data
#        guest_data = {
#            "available": True,
#            "os_info": os_info,
#            "hostname": guest_agent_info.get("hostname", ""),
#            "timezone": guest_agent_info.get("timezone", ""),
#            "users": guest_agent_info.get("userList", []),
#            "filesystems": guest_agent_info.get("fsInfo", {}).get("filesystems", [])
#        }
#        
#        return guest_data
#
# 5. Comprehensive VM Data Extraction:
#    def extract_complete_vm_data(vm, vmi):
#        # Basic VM information
#        vm_data = {
#            "name": vm["metadata"]["name"],
#            "namespace": vm["metadata"]["namespace"],
#            "uid": vm["metadata"]["uid"],
#            "running": vm.get("spec", {}).get("running", False)
#        }
#        
#        # Extract domain specification
#        domain_spec = vm.get("spec", {}).get("template", {}).get("spec", {}).get("domain", {})
#        
#        # Calculate resources
#        vm_data.update(calculate_vm_resources(domain_spec))
#        
#        # Extract disk information
#        vm_data["disks"] = parse_vm_disk_specifications(domain_spec)
#        
#        # Extract runtime information from VMI
#        if vmi:
#            vmi_status = vmi.get("status", {})
#            
#            # Network information
#            vm_data["interfaces"] = get_vm_network_interfaces(vmi_status)
#            
#            # Operational status
#            vm_data["phase"] = vmi_status.get("phase", "")
#            vm_data["node"] = vmi_status.get("nodeName", "")
#            
#            # Conditions
#            vm_data["conditions"] = extract_vm_conditions(vmi_status)
#            
#            # Guest agent information
#            guest_info = vmi_status.get("guestOSInfo", {})
#            vm_data["guest_os"] = extract_vm_os_info(guest_info)
#        
#        return vm_data
#
# =====================================================================
# ERROR HANDLING AND VALIDATION PATTERNS
# =====================================================================
#
# 1. Safe Resource Parsing:
#    def safe_parse_memory(memory_string):
#        try:
#            return parse_memory_string(memory_string)
#        except (ValueError, AttributeError) as e:
#            logger.warning(f"Failed to parse memory '{memory_string}': {e}")
#            return 1024  # Default to 1 GB
#
# 2. Network Interface Validation:
#    def validate_interface_data(interface):
#        # Validate MAC address format
#        mac = interface.get("mac", "")
#        if mac and not re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', mac):
#            logger.warning(f"Invalid MAC address format: {mac}")
#        
#        # Validate IP addresses
#        for ip in interface.get("ips", []):
#            try:
#                ipaddress.ip_address(ip)
#            except ValueError:
#                logger.warning(f"Invalid IP address: {ip}")
#
# 3. Condition Processing with Defaults:
#    def process_conditions_safely(vmi_status):
#        try:
#            conditions = extract_vm_conditions(vmi_status)
#            
#            # Build condition summary
#            condition_summary = {}
#            for condition in conditions:
#                condition_type = condition.get("type", "")
#                condition_status = condition.get("status", "").lower() == "true"
#                condition_summary[condition_type] = condition_status
#            
#            return condition_summary
#        except Exception as e:
#            logger.error(f"Failed to process VM conditions: {e}")
#            return {}
#
# =====================================================================
