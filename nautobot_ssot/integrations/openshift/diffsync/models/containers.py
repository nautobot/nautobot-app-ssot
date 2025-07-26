"""Container-specific DiffSync models for OpenShift integration."""
from typing import Optional, List, Dict, Any
from diffsync import DiffSyncModel
from .base import OpenshiftBaseMixin


class OpenshiftPod(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for OpenShift pods."""
    
    _modelname = "openshift_pod"
    _identifiers = ("namespace", "name")
    _attributes = (
        "node", "containers", "status", "restart_count",
        "ip_address", "labels", "annotations", "is_kubevirt_vm"
    )
    
    # Pod specific fields
    namespace: str
    node: Optional[str] = ""
    containers: List[Dict[str, Any]] = []
    status: str = "Running"
    restart_count: int = 0
    ip_address: Optional[str] = ""
    is_kubevirt_vm: bool = False  # Flag to identify KubeVirt VMs


class OpenshiftContainer(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for containers within pods."""
    
    _modelname = "openshift_container"
    _identifiers = ("pod_name", "namespace", "name")
    _attributes = (
        "image", "cpu_request", "memory_request", "cpu_limit",
        "memory_limit", "status", "ports", "environment"
    )
    
    # Container specific fields
    pod_name: str
    namespace: str
    image: str
    cpu_request: Optional[int] = 0  # In millicores
    memory_request: Optional[int] = 0  # In MB
    cpu_limit: Optional[int] = 0
    memory_limit: Optional[int] = 0
    status: str = "Running"
    ports: List[Dict[str, Any]] = []
    environment: Dict[str, str] = {}


class OpenshiftDeployment(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for OpenShift deployments."""
    
    _modelname = "openshift_deployment"
    _identifiers = ("namespace", "name")
    _attributes = (
        "replicas", "available_replicas", "strategy", 
        "selector", "labels", "annotations"
    )
    
    # Deployment specific fields
    namespace: str
    replicas: int = 1
    available_replicas: int = 0
    strategy: str = "RollingUpdate"
    selector: Dict[str, str] = {}


class OpenshiftService(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for OpenShift services."""
    
    _modelname = "openshift_service"
    _identifiers = ("namespace", "name")
    _attributes = (
        "type", "cluster_ip", "external_ips", "ports",
        "selector", "labels", "annotations"
    )
    
    # Service specific fields
    namespace: str
    type: str = "ClusterIP"
    cluster_ip: Optional[str] = ""
    external_ips: List[str] = []
    ports: List[Dict[str, Any]] = []
    selector: Dict[str, str] = {}
