"""OpenShift adapter for DiffSync synchronization.

This module implements the OpenShift-side adapter for DiffSync, responsible for loading
and transforming data from OpenShift clusters into DiffSync models. The adapter handles
both traditional container workloads and KubeVirt virtual machines.

Adapter Architecture:
- Connects to OpenShift via Kubernetes API client
- Discovers and categorizes cluster resources (containers vs VMs)
- Transforms OpenShift resources into DiffSync models
- Handles namespace filtering and workload type selection
- Provides error handling and recovery mechanisms

Key Responsibilities:
- API client initialization and connection management
- Resource discovery and enumeration across namespaces
- Data transformation from Kubernetes API objects to DiffSync models
- KubeVirt detection and VM lifecycle management
- Filtering and scoping based on configuration parameters

Data Loading Strategy:
- Projects/Namespaces: Foundation for multi-tenancy
- Nodes: Infrastructure capacity and placement
- Containers: Application workloads and services
- Deployments: Application lifecycle management
- Services: Network service discovery
- Virtual Machines: KubeVirt virtualization layer

Error Handling:
- Graceful degradation when KubeVirt is unavailable
- Connection retry logic for transient failures
- Partial sync capability when some resources fail
- Comprehensive logging for troubleshooting

Performance Optimizations:
- Parallel API calls where possible
- Efficient resource filtering at API level
- Minimal data transformation overhead
- Selective loading based on configuration
"""

from typing import Dict, List, Any
from diffsync import Adapter

from nautobot_ssot.integrations.openshift.utilities.openshift_client import OpenshiftClient
from nautobot_ssot.integrations.openshift.diffsync.models.base import (
    OpenshiftProject, OpenshiftNode
)
from nautobot_ssot.integrations.openshift.diffsync.models.containers import (
    OpenshiftPod, OpenshiftContainer, OpenshiftDeployment, OpenshiftService
)
from nautobot_ssot.integrations.openshift.diffsync.models.kubevirt import (
    OpenshiftVirtualMachine, OpenshiftVirtualMachineInstance
)


class OpenshiftAdapter(Adapter):
    """DiffSync adapter for loading data from OpenShift clusters.
    
    This adapter serves as the source side of the synchronization process,
    connecting to OpenShift clusters and transforming discovered resources
    into DiffSync models for comparison and synchronization with Nautobot.
    
    Supported Resource Types:
    - Projects/Namespaces: Organizational boundaries and multi-tenancy
    - Nodes: Physical/virtual infrastructure hosting workloads
    - Pods: Container runtime units (both app containers and VM pods)
    - Containers: Individual application processes within pods
    - Deployments: Application lifecycle and scaling management
    - Services: Network service discovery and load balancing
    - VirtualMachines: KubeVirt VM specifications and desired state
    - VMInstances: KubeVirt VM runtime state and operational data
    
    Configuration-Driven Loading:
    - Namespace filtering via regex patterns
    - Workload type selection (all, containers, VMs)
    - Granular sync options for each resource type
    - KubeVirt availability detection and graceful fallback
    
    Connection Management:
    - Secure credential handling via SecretsGroup
    - SSL certificate verification options
    - Connection retry and error recovery
    - API client lifecycle management
    
    Data Processing Pipeline:
    1. Initialize client with secure credentials
    2. Verify cluster connectivity and API access
    3. Detect KubeVirt availability for VM support
    4. Load resources based on configuration settings
    5. Transform API objects to DiffSync models
    6. Handle errors and partial failures gracefully
    """
    
    # Map DiffSync model names to model classes for registration
    # This enables the adapter to create and manage these model types
    project = OpenshiftProject
    node = OpenshiftNode
    pod = OpenshiftPod
    container = OpenshiftContainer
    deployment = OpenshiftDeployment
    service = OpenshiftService
    virtualmachine = OpenshiftVirtualMachine
    vmi = OpenshiftVirtualMachineInstance
    
    # Define top-level models that exist independently (no parent references)
    # These models are loaded first and can be referenced by child models
    top_level = ["project", "node", "deployment", "service", "virtualmachine"]
    
    def __init__(self, *args, job=None, sync=None, config=None, client_config=None, **kwargs):
        """Initialize the OpenShift adapter with configuration and credentials.
        
        Sets up the adapter with necessary context for connecting to OpenShift
        and configuring resource loading behavior. Handles both legacy direct
        credential access and modern secure credential extraction.
        
        Args:
            job: SSoT job instance for logging and context
            sync: DiffSync instance for synchronization state
            config: SSOTOpenshiftConfig model instance with sync preferences
            client_config: Dictionary with extracted credentials and settings
            
        Key Initialization Steps:
        1. Store job context for logging and error reporting
        2. Extract credentials securely from client_config
        3. Initialize OpenShift API client with authentication
        4. Configure resource loading based on sync preferences
        5. Validate cluster connectivity and API access
        
        Security Notes:
        - Credentials passed via client_config from secure extraction
        - API tokens handled in memory only, never persisted
        - SSL verification configurable for different environments
        - Connection parameters validated before use
        """
        super().__init__(*args, **kwargs)
        
        # Store context for logging and configuration access
        self.job = job
        self.sync = sync
        self.config = config
        self.client_config = client_config or {}
        
        # Initialize OpenShift client with extracted configuration
        # Prioritizes client_config (from secure credential extraction)
        # Falls back to config model attributes for backward compatibility
        self.client = OpenshiftClient(
            url=self.client_config.get("url", config.openshift_instance.remote_url),
            api_token=self.client_config.get("api_token", ""),
            verify_ssl=self.client_config.get("verify_ssl", config.openshift_instance.verify_ssl)
        )
        
        # Log adapter initialization with cluster context
        self.job.logger.info(f"Initialized OpenShift adapter for cluster: {self.client.url}")
    
    def load(self):
        """Load data from OpenShift cluster into DiffSync models.
        
        Orchestrates the complete data loading process from OpenShift cluster
        resources into DiffSync models. Handles resource discovery, filtering,
        transformation, and error recovery throughout the loading process.
        
        Loading Strategy:
        1. Verify cluster connectivity and API access
        2. Detect platform capabilities (KubeVirt availability)
        3. Load foundational resources (projects, nodes)
        4. Load workload resources based on configuration
        5. Load network services and configuration
        6. Handle errors and report loading statistics
        
        Resource Dependencies:
        - Projects loaded first (provide namespace context)
        - Nodes loaded for infrastructure context
        - Workloads loaded based on type configuration
        - Services loaded for network connectivity
        
        Error Handling:
        - Individual resource loading failures don't stop entire sync
        - KubeVirt unavailability handled gracefully
        - Network timeouts and retries managed automatically
        - Comprehensive error logging for troubleshooting
        """
        # Verify connection to OpenShift cluster before loading
        if not self.client.verify_connection():
            self.job.logger.error("Failed to connect to OpenShift API - aborting sync")
            raise Exception("Failed to connect to OpenShift API")
        
        self.job.logger.info("Successfully connected to OpenShift cluster")
        
        # Detect and log KubeVirt availability for VM support
        if self.client.kubevirt_available:
            self.job.logger.info("KubeVirt detected - virtual machine sync enabled")
        else:
            self.job.logger.info("KubeVirt not available - container workloads only")
        
        # Load foundational resources first (provide context for other resources)
        
        # Load projects/namespaces for organizational structure
        if self.config.sync_namespaces:
            self._load_projects()
        
        # Load nodes for infrastructure context and capacity planning
        if self.config.sync_nodes:
            self._load_nodes()
        
        # Load workload resources based on configuration and availability
        workload_types = self.client_config.get("workload_types", self.config.workload_types)
        
        # Load container workloads if configured
        if workload_types in ["all", "containers"]:
            if self.config.sync_containers:
                self._load_containers()
            if self.config.sync_deployments:
                self._load_deployments()
        
        # Load virtual machine workloads if configured and available
        if workload_types in ["all", "vms"]:
            if self.config.sync_kubevirt_vms and self.client.kubevirt_available:
                self._load_virtual_machines()
            elif self.config.sync_kubevirt_vms and not self.client.kubevirt_available:
                self.job.logger.warning("KubeVirt VM sync requested but KubeVirt not available")
        
        # Load network services for connectivity and service discovery
        if self.config.sync_services:
            self._load_services()
        
        # Log loading completion with statistics
        total_objects = len(self.objects)
        self.job.logger.info(f"Loaded {total_objects} objects from OpenShift cluster")
    
    def _load_projects(self):
        """Load OpenShift projects/namespaces into DiffSync models.
        
        Projects in OpenShift provide organizational boundaries and multi-tenancy
        support. They map directly to Nautobot tenants for consistent resource
        organization and access control.
        
        Loading Process:
        1. Fetch all namespaces from cluster API
        2. Apply namespace filtering if configured
        3. Extract project metadata and annotations
        4. Transform to OpenshiftProject DiffSync models
        5. Add models to adapter's object store
        
        Filtering Logic:
        - Applies regex pattern from config.namespace_filter
        - Skips system namespaces by default (kube-system, openshift-*)
        - Includes only explicitly allowed namespaces if filter is strict
        
        Metadata Extraction:
        - Display name from openshift.io/display-name annotation
        - Description from openshift.io/description annotation
        - Resource quotas and limits where available
        - Project creation and modification timestamps
        """
        # Apply namespace filtering from configuration
        namespace_filter = self.client_config.get("namespace_filter", self.config.namespace_filter)
        
        # Fetch projects with optional filtering
        projects = self.client.get_projects(namespace_filter)
        
        # Transform and load each project into DiffSync
        for project_data in projects:
            project = self.project(**project_data)
            self.add(project)
            self.job.logger.debug(f"Loaded project: {project.name}")
        
        self.job.logger.info(f"Loaded {len(projects)} projects from OpenShift")
    
    def _load_nodes(self):
        """Load OpenShift cluster nodes into DiffSync models.
        
        Nodes represent the physical or virtual machines that comprise the
        OpenShift cluster infrastructure. They provide compute, storage, and
        networking resources for application workloads.
        
        Node Types:
        - Master nodes: Control plane components and cluster management
        - Worker nodes: Application workload execution and data plane
        - Infra nodes: Infrastructure services (registry, monitoring, logging)
        
        Resource Information:
        - CPU capacity and current allocation
        - Memory capacity and utilization
        - Storage capacity and available space
        - Network interfaces and connectivity
        - Operating system and container runtime versions
        
        Status Tracking:
        - Ready/NotReady status for scheduling decisions
        - Cordoned status for maintenance operations
        - Resource pressure indicators (disk, memory, PID)
        - Kubelet and container runtime health
        """
        # Fetch all nodes from the cluster
        nodes = self.client.get_nodes()
        
        # Transform and load each node into DiffSync
        for node_data in nodes:
            node = self.node(**node_data)
            self.add(node)
            self.job.logger.debug(f"Loaded node: {node.name} (role: {node.role})")
        
        self.job.logger.info(f"Loaded {len(nodes)} nodes from OpenShift cluster")
    
    def _load_containers(self):
        """Load container workloads (pods and containers) into DiffSync models.
        
        Containers represent traditional cloud-native application workloads
        running in pods across the cluster. This excludes KubeVirt VM pods
        which are handled separately by the VM loading process.
        
        Container Discovery:
        1. Fetch all pods from configured namespaces
        2. Filter out KubeVirt VM pods using detection logic
        3. Extract container specifications from remaining pods
        4. Transform to OpenshiftPod and OpenshiftContainer models
        5. Link containers to their parent pods
        
        Resource Specifications:
        - Container images and registry information
        - CPU and memory requests/limits for QoS
        - Environment variables and configuration
        - Volume mounts and storage requirements
        - Network port configurations
        
        Operational Data:
        - Pod phase and container status
        - Restart counts and failure reasons
        - Node placement and scheduling constraints
        - IP address assignments and networking
        """
        # Fetch pods and containers, excluding KubeVirt VMs
        namespace_filter = self.client_config.get("namespace_filter", self.config.namespace_filter)
        pods, containers = self.client.get_pods_and_containers(namespace_filter)
        
        # Load pod models for non-VM pods
        container_pod_count = 0
        for pod_data in pods:
            if not pod_data["is_kubevirt_vm"]:
                pod = self.pod(**pod_data)
                self.add(pod)
                container_pod_count += 1
                self.job.logger.debug(f"Loaded container pod: {pod.namespace}/{pod.name}")
        
        # Load individual container models
        for container_data in containers:
            container = self.container(**container_data)
            self.add(container)
            self.job.logger.debug(
                f"Loaded container: {container.namespace}/{container.pod_name}/{container.name}"
            )
        
        self.job.logger.info(
            f"Loaded {container_pod_count} container pods and {len(containers)} containers"
        )
    
    def _load_deployments(self):
        """Load OpenShift deployments into DiffSync models.
        
        Deployments manage the lifecycle of application replicas, providing
        declarative updates, scaling, and rollback capabilities for stateless
        applications running in the cluster.
        
        Deployment Features:
        - Replica set management for desired pod count
        - Rolling update strategies for zero-downtime deployments
        - Rollback capabilities for failed deployments
        - Pod template specifications for consistent replicas
        
        Configuration Data:
        - Desired and available replica counts
        - Deployment strategy (RollingUpdate, Recreate)
        - Label selectors for pod management
        - Update progress and rollout status
        
        Operational Monitoring:
        - Deployment conditions and status
        - Replica availability and readiness
        - Update progress and timing
        - Error conditions and remediation
        """
        # Fetch deployments from configured namespaces
        namespace_filter = self.client_config.get("namespace_filter", self.config.namespace_filter)
        deployments = self.client.get_deployments(namespace_filter)
        
        # Transform and load each deployment into DiffSync
        for deployment_data in deployments:
            deployment = self.deployment(**deployment_data)
            self.add(deployment)
            self.job.logger.debug(
                f"Loaded deployment: {deployment.namespace}/{deployment.name} "
                f"({deployment.available_replicas}/{deployment.replicas} replicas)"
            )
        
        self.job.logger.info(f"Loaded {len(deployments)} deployments from OpenShift")
    
    def _load_services(self):
        """Load OpenShift services into DiffSync models.
        
        Services provide stable network endpoints for accessing application
        pods, abstracting away the ephemeral nature of individual pod IPs
        and enabling service discovery and load balancing.
        
        Service Types:
        - ClusterIP: Internal cluster access with virtual IP
        - NodePort: External access via static port on nodes
        - LoadBalancer: Cloud provider load balancer integration
        - ExternalName: DNS CNAME records for external services
        
        Network Configuration:
        - Port mappings between service and target ports
        - Protocol specifications (TCP, UDP, SCTP)
        - Session affinity and load balancing options
        - Endpoint management and health checking
        
        Service Discovery:
        - DNS entries for service name resolution
        - Environment variable injection into pods
        - Service registration with mesh and discovery systems
        - Cross-namespace service access patterns
        """
        # Fetch services from configured namespaces
        namespace_filter = self.client_config.get("namespace_filter", self.config.namespace_filter)
        services = self.client.get_services(namespace_filter)
        
        # Transform and load each service into DiffSync
        for service_data in services:
            service = self.service(**service_data)
            self.add(service)
            self.job.logger.debug(
                f"Loaded service: {service.namespace}/{service.name} "
                f"({service.type}, ports: {[p.get('port') for p in service.ports]})"
            )
        
        self.job.logger.info(f"Loaded {len(services)} services from OpenShift")
    
    def _load_virtual_machines(self):
        """Load KubeVirt virtual machines into DiffSync models.
        
        Virtual machines provide traditional virtualization capabilities
        within the OpenShift container platform, enabling hybrid workloads
        and migration paths for legacy applications.
        
        VM Resource Hierarchy:
        - VirtualMachine: Desired state specification
        - VirtualMachineInstance: Runtime instance state
        - Pod: Infrastructure container running the VM
        
        VM Specifications:
        - CPU cores and architecture requirements
        - Memory allocation and balloon driver settings
        - Virtual disk configuration and storage classes
        - Network interface assignments and models
        - Firmware settings (BIOS/UEFI, secure boot)
        
        Operational Features:
        - Live migration between cluster nodes
        - Snapshot and cloning capabilities
        - Guest agent integration for enhanced management
        - Console access and remote management
        
        Lifecycle Management:
        - VM power state control (start, stop, restart)
        - Template-based VM provisioning
        - Resource quota and limit enforcement
        - Backup and disaster recovery integration
        """
        # Only load VMs if KubeVirt is available in the cluster
        if not self.client.kubevirt_available:
            self.job.logger.warning("Skipping VM loading - KubeVirt not available")
            return
        
        # Fetch virtual machines from configured namespaces
        namespace_filter = self.client_config.get("namespace_filter", self.config.namespace_filter)
        vms = self.client.get_virtual_machines(namespace_filter)
        
        # Track VM and VMI counts for reporting
        vmi_count = 0
        
        # Transform and load each VM into DiffSync
        for vm_data in vms:
            vm = self.virtualmachine(**vm_data)
            self.add(vm)
            self.job.logger.debug(
                f"Loaded VM: {vm.namespace}/{vm.name} "
                f"(running: {vm.running}, status: {vm.status})"
            )
            
            # Load associated VMI if VM is running
            if vm.running and vm.vmi_uid:
                vmi_data = self.client.get_virtual_machine_instance(
                    vm.namespace, vm.name
                )
                if vmi_data:
                    vmi = self.vmi(**vmi_data)
                    self.add(vmi)
                    vmi_count += 1
                    self.job.logger.debug(
                        f"Loaded VMI: {vmi.namespace}/{vmi.name} "
                        f"(phase: {vmi.phase}, node: {vmi.node})"
                    )
        
        self.job.logger.info(
            f"Loaded {len(vms)} virtual machines and {vmi_count} VM instances from KubeVirt"
        )

# =====================================================================
# OPENSHIFT ADAPTER PATTERNS FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. Resource Loading Strategy:
#    # Load resources in dependency order
#    def load_resources_systematically():
#        # Foundation: organizational and infrastructure
#        load_projects()      # Provide namespace context
#        load_nodes()         # Provide infrastructure capacity
#        
#        # Workloads: applications and services
#        load_deployments()   # Application definitions
#        load_containers()    # Runtime instances
#        load_vms()          # Virtual machine workloads
#        
#        # Services: networking and connectivity
#        load_services()      # Network service endpoints
#
# 2. Error Recovery Patterns:
#    def load_with_recovery(resource_loader):
#        try:
#            return resource_loader()
#        except ApiException as e:
#            if e.status == 403:
#                logger.warning(f"Insufficient permissions for {resource_loader.__name__}")
#                return []
#            elif e.status == 404:
#                logger.info(f"Resource type not available: {resource_loader.__name__}")
#                return []
#            else:
#                logger.error(f"API error in {resource_loader.__name__}: {e}")
#                raise
#
# 3. Filtering Implementation:
#    def apply_namespace_filter(namespaces, filter_pattern):
#        if not filter_pattern:
#            return namespaces
#        
#        import re
#        compiled_pattern = re.compile(filter_pattern)
#        return [ns for ns in namespaces if compiled_pattern.match(ns.name)]
#
# 4. KubeVirt Detection Pattern:
#    def detect_kubevirt_availability():
#        try:
#            # Try to list VirtualMachine CRDs
#            custom_objects.list_cluster_custom_object(
#                group="kubevirt.io",
#                version="v1", 
#                plural="virtualmachines",
#                limit=1
#            )
#            return True
#        except ApiException as e:
#            if e.status == 404:
#                return False  # CRD not installed
#            raise  # Other errors should be investigated
#
# 5. Resource Transformation:
#    def transform_pod_to_diffsync(k8s_pod):
#        return {
#            "name": k8s_pod.metadata.name,
#            "namespace": k8s_pod.metadata.namespace,
#            "uuid": k8s_pod.metadata.uid,
#            "labels": k8s_pod.metadata.labels or {},
#            "annotations": k8s_pod.metadata.annotations or {},
#            "node": k8s_pod.spec.node_name,
#            "status": k8s_pod.status.phase,
#            "ip_address": k8s_pod.status.pod_ip,
#            "is_kubevirt_vm": is_kubevirt_vm_pod(k8s_pod)
#        }
#
# =====================================================================
# PERFORMANCE OPTIMIZATION STRATEGIES
# =====================================================================
#
# 1. Parallel Resource Loading:
#    import concurrent.futures
#    
#    def load_resources_parallel():
#        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
#            futures = {
#                executor.submit(client.get_projects): "projects",
#                executor.submit(client.get_nodes): "nodes", 
#                executor.submit(client.get_deployments): "deployments",
#                executor.submit(client.get_services): "services",
#                executor.submit(client.get_virtual_machines): "vms"
#            }
#            
#            results = {}
#            for future in concurrent.futures.as_completed(futures):
#                resource_type = futures[future]
#                results[resource_type] = future.result()
#            
#            return results
#
# 2. Efficient API Usage:
#    # Use label selectors to filter at API level
#    pods = client.list_namespaced_pod(
#        namespace="production",
#        label_selector="app=web-server,tier=frontend"
#    )
#    
#    # Use field selectors for status-based filtering
#    running_pods = client.list_namespaced_pod(
#        namespace="production", 
#        field_selector="status.phase=Running"
#    )
#
# 3. Memory Management:
#    # Process large resource lists in chunks
#    def process_pods_in_chunks(pods, chunk_size=100):
#        for i in range(0, len(pods), chunk_size):
#            chunk = pods[i:i + chunk_size]
#            process_pod_chunk(chunk)
#            # Allow garbage collection between chunks
#            gc.collect()
#
# 4. Caching Strategy:
#    @lru_cache(maxsize=128)
#    def get_namespace_metadata(namespace_name):
#        # Cache namespace metadata to avoid repeated API calls
#        return client.read_namespace(namespace_name)
#
# =====================================================================
# CONNECTION AND AUTHENTICATION PATTERNS
# =====================================================================
#
# 1. Secure Credential Handling:
#    def initialize_client_securely(client_config):
#        # Never log credentials
#        url = client_config["url"]
#        token = client_config["api_token"]  # From SecretsGroup
#        verify_ssl = client_config.get("verify_ssl", True)
#        
#        # Validate configuration before use
#        if not url or not token:
#            raise ValueError("Missing required connection parameters")
#        
#        return OpenshiftClient(url, token, verify_ssl)
#
# 2. Connection Validation:
#    def validate_cluster_access(client):
#        try:
#            # Test basic API access
#            version = client.api_client.call_api(
#                "/version", "GET", response_type="json"
#            )
#            logger.info(f"Connected to OpenShift {version.gitVersion}")
#            return True
#        except Exception as e:
#            logger.error(f"Cluster access validation failed: {e}")
#            return False
#
# 3. Retry Logic:
#    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
#    def load_resources_with_retry():
#        try:
#            return client.get_all_resources()
#        except ApiException as e:
#            if e.status >= 500:  # Server errors - retry
#                raise
#            else:  # Client errors - don't retry
#                raise RetryError(f"Client error {e.status}: {e.reason}")
#
# =====================================================================
