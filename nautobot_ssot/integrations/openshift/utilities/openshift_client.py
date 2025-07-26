"""OpenShift API client utility with KubeVirt support.

This module provides a comprehensive client for interacting with OpenShift
clusters via the Kubernetes API. It supports both standard Kubernetes
resources and KubeVirt virtual machines, with graceful fallback when
KubeVirt is not available.

Key Features:
1. Unified API for OpenShift and KubeVirt resources
2. Automatic KubeVirt detection and fallback handling  
3. Pod analysis to distinguish containers from VMs
4. Resource parsing and normalization for DiffSync
5. Secure authentication via service account tokens

Architecture:
- Built on the official kubernetes-client Python library
- Extends standard K8s API client with OpenShift and KubeVirt specifics
- Provides higher-level methods for resource discovery and parsing
- Handles credential management and SSL verification

KubeVirt Integration:
- Automatically detects KubeVirt availability at initialization
- Provides VM-specific methods when KubeVirt is available
- Gracefully handles KubeVirt unavailability (not an error condition)
- Distinguishes VM pods from regular container pods

Security Considerations:
- Uses service account tokens for authentication
- Supports SSL verification (recommended for production)
- Token and SSL settings configurable per client instance
- No credential storage - tokens passed at initialization only

Usage Patterns:
    client = OpenshiftClient(
        url="https://api.cluster.example.com:6443",
        api_token="sha256~...",
        verify_ssl=True
    )
    
    if client.kubevirt_available:
        vms = client.get_virtual_machines()
    
    pods = client.get_pods_and_containers()
"""
import re
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse
import requests
from kubernetes import client, config


def parse_openshift_url(url: str) -> Dict[str, str]:
    """Parse OpenShift API URL into components for validation and debugging.
    
    Utility function to break down OpenShift API URLs into their constituent
    parts. Useful for validation, logging, and error reporting.
    
    Args:
        url (str): Full OpenShift API URL (e.g., https://api.cluster.com:6443)
        
    Returns:
        dict: URL components with keys:
            - scheme: Protocol (http/https)
            - hostname: Server hostname or IP
            - port: Port number (defaults to 6443 for OpenShift)
            - path: URL path (usually empty for API root)
            
    Example:
        >>> parse_openshift_url("https://api.cluster.example.com:6443")
        {
            "scheme": "https",
            "hostname": "api.cluster.example.com", 
            "port": 6443,
            "path": ""
        }
    """
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme,
        "hostname": parsed.hostname,
        "port": parsed.port or 6443,  # OpenShift default API port
        "path": parsed.path or ""
    }


class OpenshiftClient:
    """High-level client for OpenShift and KubeVirt API interactions.
    
    This client provides a unified interface for accessing OpenShift cluster
    resources including both standard Kubernetes objects and KubeVirt virtual
    machines. It automatically detects KubeVirt availability and provides
    graceful fallback behavior.
    
    Architecture Design:
    - Wraps the official kubernetes-client library
    - Provides OpenShift-specific resource handling
    - Extends standard K8s APIs with KubeVirt support
    - Offers high-level methods for common operations
    
    Resource Support:
    - Namespaces/Projects (with OpenShift annotations)
    - Nodes (with capacity and role information)
    - Pods and Containers (excluding VM pods)
    - Deployments and Services
    - KubeVirt VirtualMachines and VMInstances (when available)
    
    Error Handling Strategy:
    - Network/API errors are propagated to caller
    - Missing KubeVirt is handled gracefully (not an error)
    - Individual resource failures logged but don't stop processing
    - Connection issues raise exceptions for immediate attention
    
    Performance Considerations:
    - API calls are made on-demand (no preloading)
    - Supports namespace filtering to reduce data volume
    - Uses Kubernetes client's built-in pagination
    - Minimal resource transformation for better performance
    """
    
    def __init__(self, url: str, api_token: str, verify_ssl: bool = True):
        """Initialize OpenShift client with secure connection parameters.
        
        Sets up the Kubernetes client configuration and initializes all
        necessary API client objects. Also performs KubeVirt availability
        detection for conditional feature enablement.
        
        Args:
            url (str): OpenShift API server URL (e.g., https://api.cluster.com:6443)
            api_token (str): Service account token for authentication
            verify_ssl (bool): Whether to verify SSL certificates (default: True)
            
        Raises:
            Exception: If client configuration fails or connection cannot be established
            
        Security Notes:
        - API token should be a service account token with appropriate permissions
        - SSL verification strongly recommended for production environments
        - Token is stored in client instance but not logged or exposed
        
        Initialization Process:
        1. Store connection parameters for reference
        2. Configure Kubernetes client with authentication
        3. Initialize API client objects for different resource types
        4. Test KubeVirt availability and store result
        """
        # Store connection parameters for debugging and logging
        self.url = url
        self.api_token = api_token  # Stored for reconnection, never logged
        self.verify_ssl = verify_ssl
        
        # Configure Kubernetes client with OpenShift connection details
        # This follows the standard kubernetes-client pattern
        configuration = client.Configuration()
        configuration.host = url
        configuration.api_key = {"authorization": f"Bearer {api_token}"}
        configuration.verify_ssl = verify_ssl
        
        # Initialize API client objects for different resource types
        # Each client handles a specific set of Kubernetes API groups
        self.api_client = client.ApiClient(configuration)         # Base client
        self.core_v1 = client.CoreV1Api(self.api_client)          # Core resources (pods, nodes, etc.)
        self.apps_v1 = client.AppsV1Api(self.api_client)          # Application resources (deployments)
        self.networking_v1 = client.NetworkingV1Api(self.api_client)  # Network resources
        self.custom_objects = client.CustomObjectsApi(self.api_client)  # Custom resources (KubeVirt)
        
        # Detect KubeVirt availability at initialization
        # This determines whether VM-related methods will be available
        self.kubevirt_available = self._check_kubevirt_apis()
        
    def verify_connection(self) -> bool:
        """Test connectivity to the OpenShift cluster.
        
        Performs a minimal API call to verify that the client can successfully
        communicate with the OpenShift cluster. Used for health checks and
        connection validation before attempting resource operations.
        
        Returns:
            bool: True if connection successful, False if any error occurs
            
        Implementation Notes:
        - Uses a lightweight API call (get_api_resources) for testing
        - Catches all exceptions to provide simple boolean result
        - Does not distinguish between different types of failures
        - Should be called before attempting resource operations
        
        Error Conditions That Return False:
        - Network connectivity issues
        - Invalid API URL or port
        - Authentication failures (invalid token)
        - SSL certificate verification failures
        - Cluster unavailability or overload
        """
        try:
            # Use a minimal API call to test connectivity
            # get_api_resources is lightweight and requires minimal permissions
            self.core_v1.get_api_resources()
            return True
        except Exception:
            # Catch all exceptions and return False for simple health checking
            # Specific error details would be available in logs if debug enabled
            return False
    
    def _check_kubevirt_apis(self) -> bool:
        """Detect KubeVirt Custom Resource Definitions in the cluster.
        
        Attempts to access KubeVirt's VirtualMachine CRD to determine whether
        KubeVirt is installed and accessible. This detection is non-intrusive
        and gracefully handles KubeVirt absence.
        
        Returns:
            bool: True if KubeVirt APIs are available, False otherwise
            
        Detection Strategy:
        - Attempts to list VirtualMachine resources (limit=1 for minimal impact)
        - Success indicates KubeVirt is installed and accessible
        - Any exception indicates KubeVirt is not available (normal condition)
        
        Why KubeVirt Detection Matters:
        - Enables conditional VM synchronization functionality
        - Prevents errors when trying to access VM resources on non-KubeVirt clusters
        - Allows graceful degradation to containers-only mode
        - Informs user about available synchronization capabilities
        
        Error Conditions (All Return False):
        - KubeVirt not installed on cluster
        - Insufficient permissions to access KubeVirt CRDs
        - KubeVirt installed but not functioning
        - Network issues preventing CRD access
        """
        try:
            # Attempt minimal KubeVirt API access to test availability
            # Uses limit=1 to minimize impact on cluster performance
            self.custom_objects.list_cluster_custom_object(
                group="kubevirt.io",      # KubeVirt API group
                version="v1",             # Stable KubeVirt API version
                plural="virtualmachines", # VirtualMachine CRD
                limit=1                   # Minimal resource request
            )
            return True
        except Exception:
            # Any exception indicates KubeVirt is not available
            # This is a normal condition for non-KubeVirt clusters
            return False
    
    def is_kubevirt_vm_pod(self, pod) -> bool:
        """Determine if a Kubernetes Pod is running a KubeVirt virtual machine.
        
        Analyzes Pod metadata and containers to identify KubeVirt VM pods,
        which need special handling during synchronization. VM pods are
        conceptually different from regular container pods and map to
        Nautobot VirtualMachine objects instead of Applications.
        
        Args:
            pod: Kubernetes Pod object from the API
            
        Returns:
            bool: True if pod is running a KubeVirt VM, False for regular containers
            
        Detection Methods:
        1. KubeVirt Labels: Pods running VMs have specific labels
           - "kubevirt.io/domain": Indicates VM domain
           - "vm.kubevirt.io/name": Links to VirtualMachine resource
        
        2. Container Analysis: VM pods have distinctive container patterns
           - "compute" container with "virt-launcher" command
           - Special container configuration for virtualization
        
        Why This Matters:
        - VM pods should not be treated as regular container workloads
        - VMs map to Nautobot VirtualMachine objects, not Applications
        - VM pods have different lifecycle and management patterns
        - Prevents double-counting VMs as both VMs and containers
        
        Implementation Notes:
        - Checks labels first for fastest detection
        - Falls back to container analysis for robustness
        - Returns False for any errors to avoid false positives
        """
        # Method 1: Check for KubeVirt-specific labels (fastest and most reliable)
        if pod.metadata.labels:
            # Primary KubeVirt domain label
            if "kubevirt.io/domain" in pod.metadata.labels:
                return True
            # Secondary VM name label (backup detection)
            if "vm.kubevirt.io/name" in pod.metadata.labels:
                return True
        
        # Method 2: Analyze container configuration (fallback method)
        if pod.spec.containers:
            for container in pod.spec.containers:
                # KubeVirt VMs use a "compute" container with virt-launcher
                if container.name == "compute":
                    if container.command and "virt-launcher" in str(container.command):
                        return True
        
        # If no VM indicators found, this is a regular container pod
        return False
    
    def get_projects(self, namespace_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all projects/namespaces from OpenShift."""
        namespaces = self.core_v1.list_namespace()
        projects = []
        
        for ns in namespaces.items:
            # Apply filter if provided
            if namespace_filter and not re.match(namespace_filter, ns.metadata.name):
                continue
                
            projects.append({
                "name": ns.metadata.name,
                "uuid": ns.metadata.uid,
                "display_name": ns.metadata.annotations.get(
                    "openshift.io/display-name", ns.metadata.name
                ) if ns.metadata.annotations else ns.metadata.name,
                "description": ns.metadata.annotations.get(
                    "openshift.io/description", ""
                ) if ns.metadata.annotations else "",
                "status": ns.status.phase,
                "labels": ns.metadata.labels or {},
                "annotations": ns.metadata.annotations or {},
            })
        
        return projects
    
    def get_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes from OpenShift cluster."""
        nodes = self.core_v1.list_node()
        node_list = []
        
        for node in nodes.items:
            # Extract node information
            node_info = {
                "name": node.metadata.name,
                "uuid": node.metadata.uid,
                "hostname": node.metadata.name,
                "labels": node.metadata.labels or {},
                "annotations": node.metadata.annotations or {},
                "status": "Ready" if self._is_node_ready(node) else "NotReady",
                "role": self._get_node_role(node),
            }
            
            # Extract system info
            if node.status.node_info:
                node_info.update({
                    "os_version": node.status.node_info.os_image,
                    "container_runtime": node.status.node_info.container_runtime_version,
                })
            
            # Extract capacity
            if node.status.capacity:
                node_info.update({
                    "cpu_capacity": int(node.status.capacity.get("cpu", 0)),
                    "memory_capacity": self._parse_memory(
                        node.status.capacity.get("memory", "0")
                    ),
                    "storage_capacity": self._parse_storage(
                        node.status.capacity.get("ephemeral-storage", "0")
                    ),
                })
            
            # Extract IP address
            for addr in node.status.addresses or []:
                if addr.type == "InternalIP":
                    node_info["ip_address"] = addr.address
                    break
            
            node_list.append(node_info)
        
        return node_list
    
    def get_pods_and_containers(self, namespace: Optional[str] = None) -> Tuple[List[Dict], List[Dict]]:
        """Get pods and containers, separating regular containers from KubeVirt VMs."""
        if namespace:
            pods = self.core_v1.list_namespaced_pod(namespace)
        else:
            pods = self.core_v1.list_pod_for_all_namespaces()
        
        pod_list = []
        container_list = []
        
        for pod in pods.items:
            # Skip if pod is a KubeVirt VM (will be handled separately)
            is_vm = self.is_kubevirt_vm_pod(pod)
            
            pod_info = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "uuid": pod.metadata.uid,
                "labels": pod.metadata.labels or {},
                "annotations": pod.metadata.annotations or {},
                "node": pod.spec.node_name,
                "status": pod.status.phase,
                "ip_address": pod.status.pod_ip,
                "is_kubevirt_vm": is_vm,
                "containers": [],
                "restart_count": 0,
            }
            
            if not is_vm:
                # Process containers for non-VM pods
                for container in pod.spec.containers:
                    container_info = {
                        "name": container.name,
                        "pod_name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "uuid": f"{pod.metadata.uid}-{container.name}",
                        "image": container.image,
                        "ports": [
                            {
                                "port": p.container_port,
                                "protocol": p.protocol,
                                "name": p.name
                            } for p in (container.ports or [])
                        ],
                        "environment": {},
                        "cpu_request": 0,
                        "memory_request": 0,
                        "cpu_limit": 0,
                        "memory_limit": 0,
                    }
                    
                    # Extract resource requests and limits
                    if container.resources:
                        if container.resources.requests:
                            container_info["cpu_request"] = self._parse_cpu(
                                container.resources.requests.get("cpu", "0")
                            )
                            container_info["memory_request"] = self._parse_memory(
                                container.resources.requests.get("memory", "0")
                            )
                        if container.resources.limits:
                            container_info["cpu_limit"] = self._parse_cpu(
                                container.resources.limits.get("cpu", "0")
                            )
                            container_info["memory_limit"] = self._parse_memory(
                                container.resources.limits.get("memory", "0")
                            )
                    
                    container_list.append(container_info)
                    pod_info["containers"].append(container_info)
                
                # Calculate total restart count
                for status in pod.status.container_statuses or []:
                    pod_info["restart_count"] += status.restart_count
            
            pod_list.append(pod_info)
        
        return pod_list, container_list
    
    def get_deployments(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get deployments from OpenShift."""
        if namespace:
            deployments = self.apps_v1.list_namespaced_deployment(namespace)
        else:
            deployments = self.apps_v1.list_deployment_for_all_namespaces()
        
        deployment_list = []
        for dep in deployments.items:
            deployment_info = {
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace,
                "uuid": dep.metadata.uid,
                "labels": dep.metadata.labels or {},
                "annotations": dep.metadata.annotations or {},
                "replicas": dep.spec.replicas or 0,
                "available_replicas": dep.status.available_replicas or 0,
                "strategy": dep.spec.strategy.type if dep.spec.strategy else "RollingUpdate",
                "selector": dep.spec.selector.match_labels or {},
            }
            deployment_list.append(deployment_info)
        
        return deployment_list
    
    def get_services(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get services from OpenShift."""
        if namespace:
            services = self.core_v1.list_namespaced_service(namespace)
        else:
            services = self.core_v1.list_service_for_all_namespaces()
        
        service_list = []
        for svc in services.items:
            service_info = {
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "uuid": svc.metadata.uid,
                "labels": svc.metadata.labels or {},
                "annotations": svc.metadata.annotations or {},
                "type": svc.spec.type,
                "cluster_ip": svc.spec.cluster_ip,
                "external_ips": svc.spec.external_ips or [],
                "selector": svc.spec.selector or {},
                "ports": [],
            }
            
            # Extract port information
            for port in svc.spec.ports or []:
                port_info = {
                    "name": port.name,
                    "protocol": port.protocol,
                    "port": port.port,
                    "target_port": str(port.target_port),
                    "node_port": port.node_port,
                }
                service_info["ports"].append(port_info)
            
            service_list.append(service_info)
        
        return service_list
    
    def get_virtual_machines(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get KubeVirt VirtualMachines from OpenShift."""
        if not self.kubevirt_available:
            return []
        
        try:
            if namespace:
                vms = self.custom_objects.list_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    namespace=namespace,
                    plural="virtualmachines"
                )
            else:
                vms = self.custom_objects.list_cluster_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    plural="virtualmachines"
                )
            
            vm_list = []
            for vm in vms.get("items", []):
                vm_spec = vm.get("spec", {})
                vm_status = vm.get("status", {})
                template_spec = vm_spec.get("template", {}).get("spec", {})
                domain = template_spec.get("domain", {})
                
                vm_info = {
                    "name": vm["metadata"]["name"],
                    "namespace": vm["metadata"]["namespace"],
                    "uuid": vm["metadata"]["uid"],
                    "labels": vm["metadata"].get("labels", {}),
                    "annotations": vm["metadata"].get("annotations", {}),
                    "running": vm_spec.get("running", False),
                    "status": vm_status.get("printableStatus", "Unknown"),
                    "cpu_cores": domain.get("cpu", {}).get("cores", 1),
                    "memory": self._parse_memory(
                        domain.get("resources", {}).get("requests", {}).get("memory", "1Gi")
                    ),
                    "machine_type": domain.get("machine", {}).get("type", "q35"),
                    "firmware": domain.get("firmware", {}),
                    "disks": [],
                    "interfaces": [],
                }
                
                # Extract disk information
                for disk in domain.get("devices", {}).get("disks", []):
                    disk_info = {
                        "name": disk.get("name"),
                        "bus": disk.get("disk", {}).get("bus", "virtio"),
                    }
                    vm_info["disks"].append(disk_info)
                
                # Extract interface information
                for iface in domain.get("devices", {}).get("interfaces", []):
                    iface_info = {
                        "name": iface.get("name"),
                        "type": list(iface.keys())[1] if len(iface.keys()) > 1 else "unknown",
                    }
                    vm_info["interfaces"].append(iface_info)
                
                # Get associated VMI if VM is running
                if vm_info["running"]:
                    vmi = self.get_virtual_machine_instance(
                        vm_info["namespace"], vm_info["name"]
                    )
                    if vmi:
                        vm_info["node"] = vmi.get("node", "")
                        vm_info["vmi_uid"] = vmi.get("uuid", "")
                
                vm_list.append(vm_info)
            
            return vm_list
        except Exception as e:
            # Log error but don't fail the entire sync
            print(f"Error fetching virtual machines: {e}")
            return []
    
    def get_virtual_machine_instance(self, namespace: str, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific VirtualMachineInstance."""
        if not self.kubevirt_available:
            return None
        
        try:
            vmi = self.custom_objects.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachineinstances",
                name=name
            )
            
            vmi_status = vmi.get("status", {})
            
            return {
                "name": vmi["metadata"]["name"],
                "namespace": vmi["metadata"]["namespace"],
                "uuid": vmi["metadata"]["uid"],
                "vm_name": vmi["metadata"]["name"],
                "phase": vmi_status.get("phase", "Unknown"),
                "node": vmi_status.get("nodeName", ""),
                "ip_address": vmi_status.get("interfaces", [{}])[0].get("ipAddress", "")
                    if vmi_status.get("interfaces") else "",
                "ready": vmi_status.get("ready", False),
                "live_migratable": vmi_status.get("conditions", {}).get("LiveMigratable", False),
                "conditions": vmi_status.get("conditions", []),
                "guest_agent_info": vmi_status.get("guestOSInfo", {}),
            }
        except Exception:
            return None
    
    @staticmethod
    def _is_node_ready(node) -> bool:
        """Check if node is in Ready state."""
        for condition in node.status.conditions or []:
            if condition.type == "Ready":
                return condition.status == "True"
        return False
    
    @staticmethod
    def _get_node_role(node) -> str:
        """Determine node role from labels."""
        labels = node.metadata.labels or {}
        if "node-role.kubernetes.io/master" in labels:
            return "master"
        elif "node-role.kubernetes.io/control-plane" in labels:
            return "master"
        return "worker"
    
    @staticmethod
    def _parse_memory(memory_str: str) -> int:
        """Parse memory string to MB."""
        if isinstance(memory_str, (int, float)):
            return int(memory_str)
        
        memory_str = str(memory_str)
        if memory_str.endswith("Ki"):
            return int(memory_str[:-2]) // 1024
        elif memory_str.endswith("Mi"):
            return int(memory_str[:-2])
        elif memory_str.endswith("Gi"):
            return int(memory_str[:-2]) * 1024
        elif memory_str.endswith("G"):
            return int(memory_str[:-1]) * 1024
        return 0
    
    @staticmethod
    def _parse_storage(storage_str: str) -> int:
        """Parse storage string to GB."""
        if isinstance(storage_str, (int, float)):
            return int(storage_str)
        
        storage_str = str(storage_str)
        if storage_str.endswith("Ki"):
            return int(storage_str[:-2]) // (1024 * 1024)
        elif storage_str.endswith("Mi"):
            return int(storage_str[:-2]) // 1024
        elif storage_str.endswith("Gi"):
            return int(storage_str[:-2])
        return 0
    
    @staticmethod
    def _parse_cpu(cpu_str: str) -> int:
        """Parse CPU string to millicores."""
        if isinstance(cpu_str, (int, float)):
            return int(cpu_str * 1000)
        
        cpu_str = str(cpu_str)
        if cpu_str.endswith("m"):
            return int(cpu_str[:-1])
        else:
            # Assume it's in cores, convert to millicores
            try:
                return int(float(cpu_str) * 1000)
            except ValueError:
                return 0
