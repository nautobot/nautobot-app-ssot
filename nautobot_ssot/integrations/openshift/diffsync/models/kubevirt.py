"""KubeVirt-specific DiffSync models for OpenShift integration."""
from typing import Optional, List, Dict, Any
from diffsync import DiffSyncModel
from .base import OpenshiftBaseMixin


class OpenshiftVirtualMachine(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for KubeVirt VirtualMachines."""
    
    _modelname = "openshift_virtualmachine"
    _identifiers = ("namespace", "name")
    _attributes = (
        "running", "node", "cpu_cores", "memory", "disks",
        "interfaces", "status", "guest_os", "vmi_uid",
        "firmware", "machine_type", "labels", "annotations"
    )
    
    # VM specific fields
    namespace: str
    running: bool = False
    node: Optional[str] = ""
    cpu_cores: int = 1
    memory: int = 1024  # In MB
    disks: List[Dict[str, Any]] = []
    interfaces: List[Dict[str, Any]] = []
    status: str = "Stopped"
    guest_os: Optional[str] = ""
    vmi_uid: Optional[str] = ""
    firmware: Optional[Dict[str, Any]] = {}
    machine_type: Optional[str] = "q35"
    
    def is_active(self) -> bool:
        """Check if VM is active."""
        return self.running and self.status in ["Running", "Migrating"]


class OpenshiftVirtualMachineInstance(OpenshiftBaseMixin, DiffSyncModel):
    """DiffSync model for KubeVirt VirtualMachineInstances."""
    
    _modelname = "openshift_vmi"
    _identifiers = ("namespace", "name")
    _attributes = (
        "vm_name", "phase", "node", "ip_address", "ready",
        "live_migratable", "conditions", "guest_agent_info"
    )
    
    # VMI specific fields
    namespace: str
    vm_name: str
    phase: str = "Pending"  # Pending, Scheduling, Scheduled, Running, Succeeded, Failed
    node: Optional[str] = ""
    ip_address: Optional[str] = ""
    ready: bool = False
    live_migratable: bool = False
    conditions: List[Dict[str, Any]] = []
    guest_agent_info: Optional[Dict[str, Any]] = {}
