"""Container-specific DiffSync models for OpenShift integration.

This module defines DiffSync models for traditional container workloads in OpenShift.
These models represent the standard Kubernetes container orchestration resources
that form the foundation of cloud-native applications.

Container Resource Hierarchy:
- Deployments: Define desired state for application replicas
- Pods: Runtime instances containing one or more containers
- Containers: Individual application processes within pods
- Services: Network endpoints for accessing pods

OpenShift Container Features:
- Enhanced security with Security Context Constraints (SCC)
- Built-in CI/CD integration with BuildConfig and ImageStream
- Route resources for external access (OpenShift-specific)
- Project-based multi-tenancy and resource quotas

Nautobot Mapping Strategy:
- Deployments → Nautobot Application objects (logical apps)
- Services → Nautobot Service objects (network services)
- Pods → Associated with Applications (runtime instances)
- Containers → Components within Applications

DiffSync Design Patterns:
- Namespaced resources use (namespace, name) as identifiers
- Resource specifications separated from runtime status
- Parent-child relationships maintained through references
- Labels and selectors enable resource association
"""

from typing import Optional, List, Dict, Any
from diffsync import DiffSyncModel
from .base import OpenshiftBaseMixin


class OpenshiftPod(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model representing OpenShift pods (container runtime units).
    
    Pods are the smallest deployable units in Kubernetes/OpenShift, containing
    one or more containers that share storage, network, and lifecycle. Each pod
    represents a single instance of an application or component.
    
    Pod Characteristics:
    - Ephemeral by nature - can be created, destroyed, and recreated
    - Share IP address and storage volumes among containers
    - Scheduled as atomic units onto cluster nodes
    - Contain application containers plus optional sidecar containers
    
    OpenShift Pod Extensions:
    - Security Context Constraints (SCC) define security policies
    - OpenShift-specific annotations for build and deployment tracking
    - Integration with OpenShift routing and service mesh
    - Enhanced monitoring and logging capabilities
    
    Container vs VM Detection:
    The is_kubevirt_vm flag is critical for distinguishing between:
    - Regular container pods (normal application workloads)
    - KubeVirt VM pods (virtualization infrastructure)
    
    Nautobot Integration:
    - Pods are associated with Applications through deployments
    - Pod IP addresses may be synchronized as IP addresses
    - Pod labels provide categorization and grouping
    - Node assignment shows physical placement
    
    DiffSync Considerations:
    - Uses (namespace, name) for unique identification within cluster
    - Excludes frequently changing runtime metrics (CPU/memory usage)
    - Includes stable configuration and relationship data
    - Flags KubeVirt pods for special handling
    """
    
    # DiffSync model configuration for namespaced pod resources
    _modelname = "openshift_pod"
    
    # Pods are namespaced resources requiring namespace + name for uniqueness
    _identifiers = ("namespace", "name")
    
    # Attributes to synchronize - focuses on stable configuration data
    # Excludes rapidly changing metrics like current resource usage
    _attributes = (
        "node", "containers", "status", "restart_count",
        "ip_address", "labels", "annotations", "is_kubevirt_vm"
    )
    
    # Pod-specific fields beyond base Kubernetes metadata
    
    # Namespace containing this pod (OpenShift project)
    # Used for multi-tenancy and resource isolation
    # Example: "production", "development", "monitoring"
    namespace: str
    
    # Node name where this pod is scheduled to run
    # Provides physical placement information for capacity planning
    # Example: "worker-01.prod.example.com"
    node: Optional[str] = ""
    
    # List of containers within this pod with their specifications
    # Contains container names, images, resource requirements, and ports
    # Example: [{"name": "web", "image": "nginx:1.20", "ports": [{"containerPort": 80}]}]
    containers: List[Dict[str, Any]] = []
    
    # Current lifecycle status of the pod
    # Values: "Pending", "Running", "Succeeded", "Failed", "Unknown"
    # "Running" means all containers are started and running
    status: str = "Running"
    
    # Total number of container restarts across all containers in pod
    # Indicates stability and potential application issues
    # Used for monitoring and alerting on application health
    restart_count: int = 0
    
    # IP address assigned to the pod by the cluster networking
    # Shared by all containers within the pod
    # Example: "10.244.1.15" (cluster-internal IP)
    ip_address: Optional[str] = ""
    
    # Critical flag to distinguish container pods from KubeVirt VM pods
    # True: This pod is running a KubeVirt virtual machine
    # False: This pod contains regular application containers
    # Used by sync logic to route pods to appropriate processing paths
    is_kubevirt_vm: bool = False


class OpenshiftContainer(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for individual containers within OpenShift pods.
    
    Containers are the actual application processes running within pods. Each
    container runs a single application or service, packaged as a container image
    with defined resource requirements and runtime configuration.
    
    Container Lifecycle:
    - Built from container images (often stored in OpenShift's internal registry)
    - Deployed via deployment configurations or Kubernetes deployments
    - Managed by pod controllers for scaling and healing
    - Monitored for health and resource consumption
    
    OpenShift Container Features:
    - Source-to-Image (S2I) builds for developer productivity
    - Integrated vulnerability scanning and security policies
    - Built-in logging and monitoring integration
    - Advanced networking with service mesh capabilities
    
    Resource Management:
    - Resource requests: Guaranteed minimums for scheduling
    - Resource limits: Maximum allowed consumption
    - Quality of Service (QoS) classes based on request/limit ratios
    - Node selection and affinity rules for placement
    
    Nautobot Integration:
    - Containers are components within Application objects
    - Resource specifications help with capacity planning
    - Port configurations define service endpoints
    - Environment variables may contain configuration data
    
    DiffSync Design:
    - Uses (pod_name, namespace, name) for unique identification
    - Includes resource specifications for planning purposes
    - Excludes runtime metrics that change frequently
    - Focuses on configuration that should be synchronized
    """
    
    # DiffSync model configuration for container resources
    _modelname = "openshift_container"
    
    # Containers are uniquely identified by pod + namespace + container name
    # This three-part key handles cases where multiple pods have containers
    # with the same name in different namespaces or pods
    _identifiers = ("pod_name", "namespace", "name")
    
    # Configuration attributes to synchronize
    # Focuses on resource specifications and network configuration
    # Excludes runtime status that changes frequently
    _attributes = (
        "image", "cpu_request", "memory_request", "cpu_limit",
        "memory_limit", "status", "ports", "environment"
    )
    
    # Container-specific fields for application configuration
    
    # Name of the pod containing this container
    # Used to establish parent-child relationship with pod
    # Example: "web-server-deployment-abc123"
    pod_name: str
    
    # Namespace containing the pod and container
    # Provides multi-tenancy context for the container
    # Example: "production"
    namespace: str
    
    # Container image specification (repository:tag or digest)
    # Defines the application code and runtime environment
    # Example: "registry.redhat.io/ubi8/nginx-120:latest"
    image: str
    
    # CPU resource request in millicores (1000m = 1 CPU core)
    # Guaranteed minimum CPU allocation for container scheduling
    # Example: 250 (0.25 CPU cores)
    cpu_request: Optional[int] = 0
    
    # Memory resource request in megabytes
    # Guaranteed minimum memory allocation for container scheduling
    # Example: 512 (512 MB memory)
    memory_request: Optional[int] = 0
    
    # CPU resource limit in millicores
    # Maximum CPU usage allowed before throttling
    # Example: 1000 (1 CPU core maximum)
    cpu_limit: Optional[int] = 0
    
    # Memory resource limit in megabytes
    # Maximum memory usage before container termination (OOMKilled)
    # Example: 1024 (1 GB maximum memory)
    memory_limit: Optional[int] = 0
    
    # Current runtime status of the container
    # Values: "Waiting", "Running", "Terminated"
    # "Running" indicates container process is active
    status: str = "Running"
    
    # Network ports exposed by the container
    # List of port specifications with protocol and names
    # Example: [{"name": "http", "containerPort": 8080, "protocol": "TCP"}]
    ports: List[Dict[str, Any]] = []
    
    # Environment variables configured for the container
    # Contains application configuration and runtime parameters
    # Example: {"DATABASE_URL": "postgresql://...", "LOG_LEVEL": "INFO"}
    environment: Dict[str, str] = {}


class OpenshiftDeployment(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for OpenShift deployments (application management).
    
    Deployments provide declarative updates for pods and replica sets, managing
    the lifecycle of application instances. They define the desired state for
    applications and ensure the specified number of replicas are running.
    
    Deployment Capabilities:
    - Rolling updates with zero-downtime deployments
    - Rollback to previous versions when issues occur
    - Scaling applications up or down based on demand
    - Pod template management for consistent deployments
    
    OpenShift Deployment Features:
    - DeploymentConfig (OpenShift-specific) vs Deployment (Kubernetes standard)
    - Integrated with OpenShift builds and image streams
    - Automatic triggering on image changes
    - Enhanced deployment strategies (Rolling, Recreate, Custom)
    
    Deployment Strategies:
    - RollingUpdate: Gradual replacement of old pods with new ones
    - Recreate: Terminate all old pods before creating new ones
    - Blue-Green: Switch traffic between two complete environments
    - Canary: Deploy new version to subset of traffic
    
    Nautobot Integration:
    - Deployments map to Nautobot Application objects
    - Replica counts indicate application scaling
    - Selectors define which pods belong to the application
    - Labels provide categorization and grouping
    
    DiffSync Focus:
    - Emphasizes application-level configuration over runtime details
    - Tracks desired vs actual state for monitoring
    - Includes scaling and deployment strategy information
    - Links to pods through label selectors
    """
    
    # DiffSync model configuration for deployment resources
    _modelname = "openshift_deployment"
    
    # Deployments are namespaced resources identified by namespace + name
    _identifiers = ("namespace", "name")
    
    # Application-level attributes focused on configuration and scaling
    # Excludes detailed pod status that changes frequently
    _attributes = (
        "replicas", "available_replicas", "strategy", 
        "selector", "labels", "annotations"
    )
    
    # Deployment-specific fields for application management
    
    # Namespace containing this deployment (OpenShift project)
    # Provides organizational context for the application
    # Example: "production"
    namespace: str
    
    # Desired number of pod replicas for this application
    # Defines the target scale for the application
    # Example: 3 (three instances of the application)
    replicas: int = 1
    
    # Number of replicas currently available and ready
    # Indicates actual vs desired state for monitoring
    # May be less than replicas during deployments or failures
    available_replicas: int = 0
    
    # Deployment strategy for updating the application
    # Values: "RollingUpdate", "Recreate"
    # "RollingUpdate" provides zero-downtime deployments
    strategy: str = "RollingUpdate"
    
    # Label selector that identifies pods belonging to this deployment
    # Used by the deployment controller to manage pod lifecycle
    # Example: {"app": "web-server", "version": "v1.2.3"}
    selector: Dict[str, str] = {}


class OpenshiftService(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for OpenShift services (network abstraction).
    
    Services provide stable network endpoints for accessing pods, abstracting
    away the ephemeral nature of individual pod IP addresses. They enable
    service discovery and load balancing within the cluster.
    
    Service Types:
    - ClusterIP: Internal cluster access only (default)
    - NodePort: External access via static port on each node
    - LoadBalancer: External access via cloud provider load balancer
    - ExternalName: DNS CNAME record for external services
    
    OpenShift Service Features:
    - Routes: OpenShift-specific ingress with host-based routing
    - Service mesh integration for advanced traffic management
    - Network policies for micro-segmentation
    - Integration with OpenShift's DNS and service discovery
    
    Service Discovery:
    - DNS entries created automatically for each service
    - Environment variables injected into pods
    - Service endpoints updated as pods scale up/down
    - Cross-namespace service access with FQDN
    
    Load Balancing:
    - Round-robin distribution by default
    - Session affinity for stateful applications
    - Health checks to exclude unhealthy pods
    - Weighted routing for canary deployments
    
    Nautobot Integration:
    - Services map to Nautobot Service objects
    - Port configurations define network protocols
    - Selectors link services to applications (deployments)
    - IP addresses become network service endpoints
    
    DiffSync Strategy:
    - Focuses on network configuration and endpoints
    - Includes service discovery and routing information
    - Excludes dynamic endpoint lists that change with pod scaling
    - Emphasizes stable network policy and configuration
    """
    
    # DiffSync model configuration for service resources
    _modelname = "openshift_service"
    
    # Services are namespaced resources identified by namespace + name
    _identifiers = ("namespace", "name")
    
    # Network configuration attributes for service endpoints
    # Focuses on stable networking policy and configuration
    _attributes = (
        "type", "cluster_ip", "external_ips", "ports",
        "selector", "labels", "annotations"
    )
    
    # Service-specific fields for network configuration
    
    # Namespace containing this service (OpenShift project)
    # Determines service discovery scope and network policies
    # Example: "production"
    namespace: str
    
    # Service type determining access pattern and IP allocation
    # "ClusterIP": Internal cluster access only
    # "NodePort": External access via node IP + static port
    # "LoadBalancer": External access via cloud load balancer
    type: str = "ClusterIP"
    
    # Cluster-internal IP address assigned to the service
    # Provides stable endpoint for internal service-to-service communication
    # Example: "10.96.45.123" (cluster-internal virtual IP)
    cluster_ip: Optional[str] = ""
    
    # List of external IP addresses for LoadBalancer services
    # Assigned by cloud provider or external load balancer
    # Example: ["203.0.113.10", "203.0.113.11"]
    external_ips: List[str] = []
    
    # Port configurations for the service endpoints
    # Defines protocol, ports, and target port mappings
    # Example: [{"name": "http", "port": 80, "targetPort": 8080, "protocol": "TCP"}]
    ports: List[Dict[str, Any]] = []
    
    # Label selector that identifies target pods for this service
    # Used for service discovery and load balancing
    # Must match labels on pods to route traffic correctly
    # Example: {"app": "web-server", "tier": "frontend"}
    selector: Dict[str, str] = {}

# =====================================================================
# CONTAINER WORKLOAD PATTERNS FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. Pod-Container Relationship:
#    # Pods contain one or more containers
#    pod = OpenshiftPod(namespace="prod", name="web-app-abc123")
#    containers = [
#        OpenshiftContainer(pod_name="web-app-abc123", namespace="prod", name="nginx"),
#        OpenshiftContainer(pod_name="web-app-abc123", namespace="prod", name="sidecar")
#    ]
#
# 2. Deployment-Pod Relationship:
#    # Deployments manage multiple pod replicas
#    deployment = OpenshiftDeployment(
#        namespace="prod", 
#        name="web-app",
#        replicas=3,
#        selector={"app": "web-app"}
#    )
#    # Pods created by deployment have matching labels:
#    pod = OpenshiftPod(
#        namespace="prod", 
#        name="web-app-abc123",
#        labels={"app": "web-app", "pod-template-hash": "abc123"}
#    )
#
# 3. Service-Pod Relationship:
#    # Services route traffic to pods via label selectors
#    service = OpenshiftService(
#        namespace="prod",
#        name="web-app-service", 
#        selector={"app": "web-app"},
#        ports=[{"port": 80, "targetPort": 8080}]
#    )
#    # Traffic routes to any pod with matching labels
#
# 4. Resource Specifications:
#    container = OpenshiftContainer(
#        cpu_request=250,     # 0.25 CPU cores guaranteed
#        cpu_limit=1000,     # 1.0 CPU cores maximum
#        memory_request=512,  # 512 MB guaranteed
#        memory_limit=1024,   # 1 GB maximum
#    )
#
# 5. KubeVirt Detection Pattern:
#    if pod.is_kubevirt_vm:
#        # Route to KubeVirt processing
#        vm_data = extract_vm_from_pod(pod)
#        vm_model = OpenshiftVirtualMachine(**vm_data)
#    else:
#        # Route to container processing
#        container_models = extract_containers_from_pod(pod)
#
# =====================================================================
# NAUTOBOT MAPPING STRATEGIES
# =====================================================================
#
# 1. Application Mapping:
#    OpenShift Deployment → Nautobot Application
#    - deployment.name → application.name
#    - deployment.namespace → application.tenant
#    - deployment.replicas → application instance count
#    - deployment.labels → application.tags
#
# 2. Service Mapping:
#    OpenShift Service → Nautobot Service
#    - service.name → service.name
#    - service.ports → service.ports
#    - service.cluster_ip → service.ip_addresses
#    - service.type → service.protocol/type
#
# 3. Network Mapping:
#    OpenShift Pod IPs → Nautobot IP Addresses
#    - pod.ip_address → ip_address.address
#    - pod.namespace → ip_address.tenant
#    - Associated with applications via deployment relationship
#
# 4. Resource Planning:
#    Container resources → Nautobot custom fields
#    - cpu_request/limit → capacity planning data
#    - memory_request/limit → resource allocation info
#    - Aggregated at application level for planning
#
# =====================================================================
# OPENSHIFT-SPECIFIC CONSIDERATIONS
# =====================================================================
#
# 1. Projects vs Namespaces:
#    # OpenShift projects are namespaces with additional metadata
#    # Projects have display names and descriptions
#    # Use project annotations for richer context
#
# 2. Security Context Constraints:
#    # OpenShift has enhanced security beyond standard Kubernetes
#    # SCCs may affect container capabilities and resource access
#    # Consider security context in container modeling
#
# 3. Build Integration:
#    # OpenShift BuildConfigs create container images
#    # ImageStreams track image versions and triggers
#    # Consider build metadata in container tracking
#
# 4. Route Resources:
#    # OpenShift Routes provide external access beyond services
#    # May want to model routes separately or as service extensions
#    # Routes can provide SSL termination and path-based routing
#
# =====================================================================
