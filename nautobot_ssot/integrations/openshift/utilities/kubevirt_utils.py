"""KubeVirt-specific utility functions for OpenShift integration."""
from typing import Dict, Any, Optional


def is_vm_running(vm_status: Dict[str, Any]) -> bool:
    """Check if a virtual machine is running based on its status."""
    return vm_status.get("printableStatus", "").lower() in ["running", "migrating"]


def extract_vm_os_info(guest_agent_info: Optional[Dict[str, Any]]) -> str:
    """Extract OS information from guest agent data."""
    if not guest_agent_info:
        return ""
    
    os_info = guest_agent_info.get("os", {})
    name = os_info.get("name", "")
    version = os_info.get("version", "")
    
    if name and version:
        return f"{name} {version}"
    return name or ""


def get_vm_network_interfaces(vmi_status: Dict[str, Any]) -> list:
    """Extract network interface information from VMI status."""
    interfaces = []
    for iface in vmi_status.get("interfaces", []):
        interface_info = {
            "name": iface.get("name", ""),
            "mac": iface.get("mac", ""),
            "ip": iface.get("ipAddress", ""),
            "ips": iface.get("ipAddresses", []),
        }
        interfaces.append(interface_info)
    return interfaces


def calculate_vm_resources(domain_spec: Dict[str, Any]) -> Dict[str, int]:
    """Calculate VM resource requirements from domain specification."""
    resources = {
        "cpu_cores": 1,
        "memory_mb": 1024,
    }
    
    # Extract CPU cores
    cpu_spec = domain_spec.get("cpu", {})
    resources["cpu_cores"] = cpu_spec.get("cores", 1)
    
    # Extract memory (convert to MB if needed)
    resource_spec = domain_spec.get("resources", {})
    memory_request = resource_spec.get("requests", {}).get("memory", "1Gi")
    
    # Parse memory string to MB
    if isinstance(memory_request, str):
        if memory_request.endswith("Gi"):
            resources["memory_mb"] = int(memory_request[:-2]) * 1024
        elif memory_request.endswith("Mi"):
            resources["memory_mb"] = int(memory_request[:-2])
        elif memory_request.endswith("Ki"):
            resources["memory_mb"] = int(memory_request[:-2]) // 1024
    
    return resources
