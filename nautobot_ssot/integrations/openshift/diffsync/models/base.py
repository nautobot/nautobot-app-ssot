"""Base DiffSync models for OpenShift integration."""
import uuid
from typing import Optional, List, Dict, Any
from diffsync import DiffSyncModel


class OpenshiftBaseMixin:
    """Base mixin for OpenShift models."""
    
    # Common fields across OpenShift resources
    name: str
    uuid: uuid.UUID
    labels: Optional[Dict[str, str]] = {}
    annotations: Optional[Dict[str, str]] = {}
    
    @classmethod
    def create_unique_id(cls, **kwargs) -> str:
        """Create unique identifier for the model."""
        return str(kwargs.get("uuid", kwargs.get("name", "")))


class OpenshiftProject(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for OpenShift projects/namespaces."""
    
    _modelname = "openshift_project"
    _identifiers = ("name",)
    _attributes = ("display_name", "description", "status", "labels", "annotations")
    
    # OpenShift specific fields
    display_name: Optional[str] = ""
    description: Optional[str] = ""
    status: str = "Active"
    resource_quota: Optional[Dict[str, Any]] = {}
    
    @classmethod
    def get_or_create(cls, adapter, **kwargs):
        """Get or create the project."""
        return adapter.get_or_create(cls, **kwargs)


class OpenshiftNode(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for OpenShift nodes."""
    
    _modelname = "openshift_node"
    _identifiers = ("name",)
    _attributes = (
        "hostname", "ip_address", "os_version", "container_runtime",
        "cpu_capacity", "memory_capacity", "storage_capacity", 
        "status", "role", "labels", "annotations"
    )
    
    # Node specific fields
    hostname: str
    ip_address: Optional[str] = ""
    os_version: Optional[str] = ""
    container_runtime: Optional[str] = "cri-o"
    cpu_capacity: Optional[int] = 0
    memory_capacity: Optional[int] = 0  # In MB
    storage_capacity: Optional[int] = 0  # In GB
    status: str = "Ready"
    role: str = "worker"  # master or worker
